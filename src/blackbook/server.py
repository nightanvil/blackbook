"""FastAPI application serving the API and the browser UI."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import xml.etree.ElementTree as ET
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import audioedit, builder, padparams, patchedit, projectseq, sampleupdate, settings, updater
from .backup import Backup
from .card import Card, browse, parse_xml
from .carddetect import find_cards
from .cardpath import INVALID_NAME_CHARS, join_reference, resolve_sample_reference, validate_name
from .eject import EjectError, eject
from .mapping import Zone, assign_key_ranges, automap, note_name
from .patchindex import FACTORY_TAGS
from .references import find_references
from .snapshot import CONFIG_NAME, MIRROR, SnapshotError, SnapshotRepo, default_target, git_executable
from .wav import WavError, read_audio, read_info

STATIC_DIR = Path(__file__).parent / "static"

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

DAMAGED_XML = (
    "{name} is empty or damaged. This happens when the card is removed before a save has reached it."
    " An older version can be restored from the backup."
)


def flush_to_disk() -> None:
    """Write cached data to all drives so the card can be removed safely."""
    if hasattr(os, "sync"):
        os.sync()


class Sources:
    """Named roots for sample browsing: the card, the local inbox and optional libraries."""

    def __init__(self, card: Card, libraries: list[Path], inbox: Path):
        inbox.mkdir(parents=True, exist_ok=True)
        self.roots: dict[str, Path] = {"card": card.root, "inbox": inbox.resolve()}
        for i, lib in enumerate(libraries, start=1):
            self.roots[f"lib{i}"] = lib.resolve()

    def resolve(self, source_id: str) -> Path:
        root_id, _, rel = source_id.partition(":")
        base = self.roots.get(root_id)
        if base is None:
            raise HTTPException(404, f"unknown source root: {root_id}")
        path = (base / rel.strip("/")).resolve()
        if path != base and not path.is_relative_to(base):
            raise HTTPException(403, "path outside of source root")
        return path


class ImportPrepareIn(BaseModel):
    root: str
    path: str = ""


def import_name(name: str) -> str:
    """File name that is valid on FAT32/exFAT and ends with .wav."""
    base = Path(name.replace("\\", "/")).name
    stem = Path(base).stem if base.lower().endswith(".wav") else base
    stem = "".join("_" if c in INVALID_NAME_CHARS or ord(c) < 32 else c for c in stem).rstrip(" .") or "sample"
    return stem + ".wav"


class PadIn(BaseModel):
    slot: int
    # None keeps the pad of the base patch untouched
    source: str | None
    gain: float = 0.0
    pitch: float = 0.0
    pan: int = 0
    choke_group: int = 0
    reverse: bool = False
    loop_mode: int = 0
    params: dict[str, int] = Field(default_factory=dict)
    start: int | None = None
    length: int | None = None


class EditOpenIn(BaseModel):
    source: str


class TrackChangeIn(BaseModel):
    index: int
    midiinchan: int | None = None
    midioutchan: int | None = None
    sequences: list[dict] = Field(default_factory=list)
    # None leaves the pads untouched; a list is the complete new pad set of a one-shot track
    pads: list[PadIn] | None = None


class ProjectChangeIn(BaseModel):
    name: str
    tracks: list[TrackChangeIn]


class RenameIn(BaseModel):
    source: str
    name: str
    apply: bool = False


class EditWriteIn(BaseModel):
    mode: str  # new or overwrite


class EditOpIn(BaseModel):
    op: str
    start: int
    end: int
    value: float = 0.0


class ZoneIn(BaseModel):
    source: str
    root: int
    key_low: int
    key_high: int
    vel_low: int = 0
    vel_high: int = 127
    vel_root: int = 64


class BuildIn(BaseModel):
    type: str
    name: str
    tags: list[str] = Field(default_factory=list)
    track_gain: float = 0.0
    gain: float = 0.0
    pads: list[PadIn] = Field(default_factory=list)
    zones: list[ZoneIn] = Field(default_factory=list)
    # Existing patch as starting point: mode 'edit' changes it in place, 'copy' saves a new patch
    base_ref: str | None = None
    mode: str = "new"


class AutomapIn(BaseModel):
    sources: list[str]
    gap_rule: str = "split"


class RemapIn(BaseModel):
    zones: list[ZoneIn]
    gap_rule: str = "split"


class BackupTargetIn(BaseModel):
    path: str


class MkdirIn(BaseModel):
    path: str
    name: str


class SnapshotIn(BaseModel):
    message: str = ""


class RestoreIn(BaseModel):
    commit: str
    path: str = ""


class ConfigIn(BaseModel):
    text: str


class TagsIn(BaseModel):
    ref: str
    tags: list[str]


def zone_out(zone: Zone) -> dict:
    data = asdict(zone)
    data["root_name"] = note_name(zone.root)
    return data


class SnapshotService:
    """Holds the configured backup repository and watches for card connection."""

    def __init__(self, card: Card, target: Path | None, on_card_found=None):
        self.card = card
        self.repo = SnapshotRepo(target) if target else None
        # Called with the path of a card found by detection; None keeps the configured path
        self.on_card_found = on_card_found
        self.events: deque[dict] = deque(maxlen=20)
        self._stop = threading.Event()

    def require(self) -> SnapshotRepo:
        if self.repo is None:
            raise HTTPException(409, "no backup folder configured")
        return self.repo

    def card_present(self) -> bool:
        # While the card is being unmounted or remounted the mount point can refuse access
        try:
            return (self.card.root / "bb2-stng.mml").is_file() or (self.card.root / "Projects").is_dir()
        except OSError:
            return False

    def auto_snapshot(self, reason: str, setting: str) -> None:
        repo = self.repo
        if repo is None or not repo.initialized or not self.card_present():
            return
        if not getattr(repo.config(), setting):
            return
        try:
            commit = repo.snapshot(self.card.root, reason, automatic=True)
            self.record(reason, commit)
        except (SnapshotError, OSError) as exc:
            self.event(f"{reason} failed: {exc}")

    def event(self, text: str) -> None:
        self.events.appendleft({"time": time.strftime("%H:%M:%S"), "text": text})

    def record(self, reason: str, commit) -> None:
        if commit:
            self.event(f"Snapshot created ({commit.subject})")
        else:
            self.event(f"{reason}: no changes since the last snapshot, no snapshot created")

    def before_write(self, what: str) -> None:
        repo = self.repo
        if repo is None or not repo.initialized:
            return
        if repo.config().snapshot_before_write:
            # A failing snapshot blocks the write
            reason = f"Before {what}"
            self.record(reason, repo.snapshot(self.card.root, reason, automatic=True))

    def after_write(self, what: str) -> None:
        repo = self.repo
        if repo is None or not repo.initialized or not repo.config().snapshot_after_write:
            return
        try:
            reason = f"After {what}"
            self.record(reason, repo.snapshot(self.card.root, reason, automatic=True))
        except (SnapshotError, OSError) as exc:
            # The card is already written, a failing snapshot only gets reported
            self.event(f"After {what} failed: {exc}")

    def watch(self) -> None:
        present = False
        last_claim = 0.0
        while not self._stop.is_set():
            try:
                repo = self.repo
                if repo is not None and repo.initialized and time.time() - last_claim > 60:
                    repo.claim()
                    last_claim = time.time()
                now = self.card_present()
                if not now and self.on_card_found is not None:
                    cards = find_cards()
                    if cards:
                        self.on_card_found(cards[0])
                        self.event(f"Card found at {cards[0]}")
                        now = self.card_present()
                if now and not present:
                    self.auto_snapshot("Card connected", "snapshot_on_connect")
                present = now
            except Exception as exc:  # noqa: BLE001 - the watcher must survive any error
                self.event(f"Card watcher error: {exc}")
            self._stop.wait(5)

    def stop(self) -> None:
        self._stop.set()
        if self.repo is not None:
            self.repo.release()


PROGRAM_FOLDER_MESSAGE = (
    "the backup folder must not be inside the blackbook folder: an update or a new installation "
    "could delete it. Choose a folder outside, for example in your documents folder."
)


def inside_program(path: Path) -> bool:
    """True when path is the blackbook installation folder or inside it."""
    resolved = path.expanduser().resolve()
    program = settings.REPO_DIR.resolve()
    return resolved == program or resolved.is_relative_to(program)


def code_commit() -> str:
    """Short commit id of the blackbook checkout, empty outside a git checkout."""
    try:
        result = subprocess.run(
            [git_executable() or "git", "-C", str(settings.REPO_DIR), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def create_app(
    card_root: Path,
    libraries: list[Path],
    backup_dir: Path,
    snapshot_target: Path | None = None,
    inbox_dir: Path | None = None,
    detect_card: bool = False,
) -> FastAPI:
    started_commit = code_commit()
    started_at = time.time()
    card = Card(card_root)
    sources = Sources(card, libraries, inbox_dir or settings.REPO_DIR / ".blackbook" / "inbox")
    backup = Backup(backup_dir, card.root)
    target = snapshot_target or (Path(settings.get("backup_target")) if settings.get("backup_target") else None)

    def use_card(path: Path) -> None:
        """Point everything at a card that was found after the start."""
        card.root = path.resolve()
        sources.roots["card"] = card.root
        backup.card_root = card.root
        settings.set_value("card_path", str(card.root))

    snapshots = SnapshotService(card, target, use_card if detect_card else None)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        watcher = threading.Thread(target=snapshots.watch, name="card-watcher", daemon=True)
        watcher.start()
        yield
        snapshots.stop()

    app = FastAPI(title="blackbook", lifespan=lifespan)
    app.state.restart_requested = False

    @app.middleware("http")
    async def revalidate_ui(request: Request, call_next):
        response = await call_next(request)
        # The browser asks again for the page and its scripts each time (cheap with the ETag), so an
        # update or a new version on disk is never hidden behind a cached copy
        path = request.url.path
        if path == "/" or path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.middleware("http")
    async def flush_after_write(request: Request, call_next):
        response = await call_next(request)
        # Audio edit sessions live in memory until saved to the local inbox or written to the card
        path = request.url.path
        in_memory = path.startswith("/api/audio-edit/") and not path.endswith("/write")
        if request.method in WRITE_METHODS and not in_memory:
            await run_in_threadpool(flush_to_disk)
        return response

    @app.exception_handler(ET.ParseError)
    async def damaged_xml(_request: Request, _exc: ET.ParseError) -> JSONResponse:
        return JSONResponse({"detail": DAMAGED_XML.format(name="The XML file")}, status_code=422)

    def make_base(body: BuildIn) -> builder.Base | None:
        if not body.base_ref or body.mode == "new":
            return None
        if body.mode not in ("edit", "copy"):
            raise HTTPException(400, f"unknown mode: {body.mode}")
        try:
            base = builder.Base.load(card.patch_dir(body.base_ref), body.mode)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        if not base.text.strip():
            raise HTTPException(422, DAMAGED_XML.format(name="patch.xml"))
        return base

    def make_plan(body: BuildIn) -> builder.Plan:
        base = make_base(body)
        if body.type == "oneshot":
            pads = {
                p.slot: builder.Pad(
                    source=sources.resolve(p.source) if p.source else None,
                    gain=p.gain,
                    pitch=p.pitch,
                    pan=p.pan,
                    choke_group=p.choke_group,
                    reverse=p.reverse,
                    loop_mode=p.loop_mode,
                    params=p.params,
                    start=p.start,
                    length=p.length,
                )
                for p in body.pads
            }
            spec = builder.OneShotSpec(body.name.strip(), body.tags, pads, body.track_gain)
            return builder.plan_oneshot(card, spec, base)
        if body.type == "multisample":
            zones = [
                builder.MultisampleZone(
                    source=sources.resolve(z.source),
                    zone=Zone(
                        source=z.source,
                        root=z.root,
                        key_low=z.key_low,
                        key_high=z.key_high,
                        vel_low=z.vel_low,
                        vel_high=z.vel_high,
                        vel_root=z.vel_root,
                    ),
                )
                for z in body.zones
            ]
            spec = builder.MultisampleSpec(body.name.strip(), body.tags, zones, body.track_gain, body.gain)
            return builder.plan_multisample(card, spec, base)
        raise HTTPException(400, f"unknown patch type: {body.type}")

    # ---------- import of files dropped from outside the browser ----------

    def import_folder(root: str, path: str) -> Path:
        if root not in ("card", "inbox"):
            raise HTTPException(403, "files can only be imported into the card or the inbox")
        if root == "card":
            if not snapshots.card_present():
                raise HTTPException(409, "card not connected")
            first = path.strip("/").split("/")[0].casefold()
            if first in ("patches", ""):
                raise HTTPException(403, "choose a folder on the card first, factory patches are read only")
        folder = sources.resolve(f"{root}:{path}")
        return folder

    @app.post("/api/import/prepare")
    def import_prepare(body: ImportPrepareIn) -> dict:
        folder = import_folder(body.root, body.path)
        if body.root == "card":
            snapshots.before_write(f"importing into {body.path.strip('/')}")
        return {"folder": str(folder)}

    @app.post("/api/import")
    async def import_file(request: Request, root: str, name: str, path: str = "") -> dict:
        folder = import_folder(root, path)
        data = await request.body()
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            raise HTTPException(400, f"{name} is not a WAV file")
        folder.mkdir(parents=True, exist_ok=True)

        filename = import_name(name)
        target = folder / filename
        n = 2
        while target.exists():
            if target.read_bytes() == data:
                break
            target = folder / f"{Path(filename).stem}_{n}.wav"
            n += 1
        if not target.exists():
            target.write_bytes(data)
            try:
                read_info(target)
            except (WavError, OSError) as exc:
                target.unlink()
                raise HTTPException(400, f"{name}: {exc}") from exc
            if root == "card":
                backup.record_created(target)

        rel = target.relative_to(sources.roots[root]).as_posix()
        return {"source": f"{root}:{rel}", "name": target.name}

    @app.get("/api/card/status")
    def card_status() -> dict:
        return {"present": snapshots.card_present()}

    @app.post("/api/card/eject")
    def card_eject() -> dict:
        if not snapshots.card_present():
            raise HTTPException(409, "no card connected")
        try:
            eject(card.root)
        except EjectError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(500, f"eject failed: {exc}") from exc
        snapshots.event("Card ejected")
        return {"ejected": str(card.root)}

    @app.get("/api/info")
    def info() -> dict:
        return {
            "card": str(card.root),
            "roots": [{"id": k, "path": str(v)} for k, v in sources.roots.items()],
            "backup": str(backup.dir),
            "commit": started_commit,
            "backup_ready": bool(snapshots.repo and snapshots.repo.initialized),
            "first_start": not settings.get("welcome_done", False),
            "version": updater.__version__,
            "dev_checkout": updater.is_git_checkout(),
            "git_available": git_executable() is not None,
            "suggested_backup": str(default_target()),
            "current_commit": code_commit(),
            "pid": os.getpid(),
            "started_at": started_at,
        }

    @app.get("/api/patches")
    def patches() -> list[dict]:
        return [asdict(p) | {"is_user": p.is_user} for p in card.patches()]

    @app.get("/api/tags")
    def tags() -> list[str]:
        used = card.load_index("Patches").all_tags() | card.load_index("UserPatches").all_tags()
        return sorted(set(FACTORY_TAGS) | used, key=str.casefold)

    @app.get("/api/patch")
    def patch(ref: str) -> dict:
        try:
            track_type, samples = card.patch_samples(ref)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ET.ParseError as exc:
            raise HTTPException(422, DAMAGED_XML.format(name="patch.xml")) from exc
        patch_dir = card.patch_dir(ref)
        preview = patch_dir / "preview.wav"
        root = ref.replace("/", "\\").split("\\")[0]
        return {
            "ref": ref,
            "track_type": track_type,
            "tags": card.load_index(root).tags_for(ref),
            "preview": "card:" + card.relative(preview) if preview.is_file() else None,
            "samples": [
                {
                    "filename": s.filename,
                    "source": "card:" + s.resolved if s.resolved else None,
                    "samlen": s.samlen,
                    "slot": s.slot,
                    "root": int(s.attrs.get("rootnote", 0)),
                    "root_name": note_name(int(s.attrs.get("rootnote", 0))),
                    "key_low": int(s.attrs.get("keyrangebottom", 0)),
                    "key_high": int(s.attrs.get("keyrangetop", 0)),
                    "vel_low": int(s.attrs.get("velrangebottom", 0)),
                    "vel_high": int(s.attrs.get("velrangetop", 0)),
                }
                for s in samples
            ],
        }

    editor = audioedit.Editor()

    def edit_session(session_id: str) -> audioedit.Session:
        try:
            return editor.get(session_id)
        except audioedit.EditError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/pcm")
    def pcm(src: str) -> Response:
        """Audio of a WAV as interleaved float32 for the waveform view."""
        path = sources.resolve(src)
        try:
            info = read_info(path)
            data, rate = read_audio(path, info)
        except (WavError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        headers = {"X-Sample-Rate": str(rate), "X-Channels": str(data.shape[1])}
        return Response(audioedit.pcm_bytes(data), media_type="application/octet-stream", headers=headers)

    @app.post("/api/audio-edit/open")
    def audio_edit_open(body: EditOpenIn) -> dict:
        try:
            return editor.open(sources.resolve(body.source), body.source).state()
        except audioedit.EditError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/audio-edit/{session_id}/pcm")
    def audio_edit_pcm(session_id: str) -> Response:
        session = edit_session(session_id)
        return Response(audioedit.pcm_bytes(session.data), media_type="application/octet-stream")

    @app.post("/api/audio-edit/{session_id}/op")
    def audio_edit_op(session_id: str, body: EditOpIn) -> dict:
        session = edit_session(session_id)
        try:
            editor.apply(session, body.op, body.start, body.end, body.value)
        except audioedit.EditError as exc:
            raise HTTPException(400, str(exc)) from exc
        return session.state()

    @app.post("/api/audio-edit/{session_id}/undo")
    def audio_edit_undo(session_id: str) -> dict:
        session = edit_session(session_id)
        editor.undo(session)
        return session.state()

    @app.post("/api/audio-edit/{session_id}/redo")
    def audio_edit_redo(session_id: str) -> dict:
        session = edit_session(session_id)
        editor.redo(session)
        return session.state()

    @app.post("/api/audio-edit/{session_id}/save")
    def audio_edit_save(session_id: str) -> dict:
        """Store the edited audio in the inbox; a patch save copies it into the patch folder."""
        session = edit_session(session_id)
        folder = sources.roots["inbox"] / "edits"
        folder.mkdir(parents=True, exist_ok=True)
        stem = Path(session.name).stem
        if not stem.endswith("_edit"):
            stem += "_edit"
        target = audioedit.free_name(folder, stem)
        try:
            audioedit.write_wav(target, session.data, session.sample_rate, session.bits, session.is_float)
        except (audioedit.EditError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        editor.close(session_id)
        rel = target.relative_to(sources.roots["inbox"]).as_posix()
        return {"source": f"inbox:{rel}", "name": target.name, "frames": len(session.data)}

    def card_target(session: audioedit.Session) -> tuple[Path, str]:
        """Path on the card and card relative path of the WAV a session was opened from."""
        root_id = session.source.partition(":")[0]
        if root_id != "card":
            raise HTTPException(400, "only samples on the card can be written back to the card")
        if not snapshots.card_present():
            raise HTTPException(409, "card not connected")
        path = sources.resolve(session.source)
        return path, card.relative(path)

    def overwrite_block(rel: str) -> str:
        if rel.split("/")[0].casefold() == "patches":
            return "Factory samples are never changed. Save the edit as a new file instead."
        return ""

    def reference_changes(rel: str, session: audioedit.Session) -> list[dict]:
        result: list[dict] = []
        frames = len(session.data)
        for ref in find_references(card.root, rel):
            raw = (card.root / ref.xml).read_bytes()
            text = raw.decode("utf-8-sig", errors="replace")
            _new, changes = sampleupdate.adjust_text(text, ref.xml, rel, frames, session.map_position)
            if any(r["xml"] == ref.xml for r in result):
                continue
            result.append({
                "xml": ref.xml,
                "kind": ref.kind,
                "changes": [sampleupdate.describe(c) for c in changes],
            })
        return result

    def edited_name_target(path: Path, rel: str) -> Path:
        folder = path.parent
        if overwrite_block(rel):
            folder = card.root / "Samples" / "Edited"
        stem = path.stem if path.stem.endswith("_edit") else path.stem + "_edit"
        return audioedit.free_name(folder, stem)

    @app.get("/api/audio-edit/{session_id}/impact")
    def audio_edit_impact(session_id: str) -> dict:
        """What saving to the card would do: target of a new file, or the files an overwrite adjusts."""
        session = edit_session(session_id)
        path, rel = card_target(session)
        block = overwrite_block(rel)
        try:
            frames_before = read_info(path).frames
        except (WavError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "path": rel,
            "new_file": card.relative(edited_name_target(path, rel)),
            "can_overwrite": not block,
            "reason": block,
            "frames_before": frames_before,
            "frames_after": len(session.data),
            "references": [] if block else reference_changes(rel, session),
            "cache": path.with_name(path.name + ".pk").is_file(),
        }

    @app.post("/api/audio-edit/{session_id}/write")
    def audio_edit_write(session_id: str, body: EditWriteIn) -> dict:
        """Write the edit to the card, as a new file next to the original or over the original."""
        session = edit_session(session_id)
        path, rel = card_target(session)
        if body.mode == "new":
            target = edited_name_target(path, rel)
            what = f"saving edited sample {card.relative(target.parent)}/{target.name}"
            snapshots.before_write(what)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                audioedit.write_wav(target, session.data, session.sample_rate, session.bits, session.is_float)
            except (audioedit.EditError, OSError) as exc:
                raise HTTPException(400, str(exc)) from exc
            backup.record_created(target)
            snapshots.after_write(what)
            editor.close(session_id)
            new_rel = card.relative(target)
            return {"source": f"card:{new_rel}", "path": new_rel, "name": target.name, "adjusted": []}
        if body.mode != "overwrite":
            raise HTTPException(400, f"unknown mode: {body.mode}")
        block = overwrite_block(rel)
        if block:
            raise HTTPException(403, block)
        what = f"overwriting {rel}"
        snapshots.before_write(what)
        frames = len(session.data)
        adjusted: list[str] = []
        try:
            updates: list[tuple[Path, bytes]] = []
            for ref in find_references(card.root, rel):
                xml_path = card.root / ref.xml
                if any(p == xml_path for p, _ in updates):
                    continue
                raw = xml_path.read_bytes()
                bom = raw.startswith(b"\xef\xbb\xbf")
                text = raw.decode("utf-8-sig")
                new_text, _changes = sampleupdate.adjust_text(text, ref.xml, rel, frames, session.map_position)
                if new_text != text:
                    updates.append((xml_path, (b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8")))
            backup.save(path)
            audioedit.rewrite_wav(path, session)
            for xml_path, data in updates:
                backup.save(xml_path)
                tmp = xml_path.with_name(xml_path.name + ".blackbook-tmp")
                tmp.write_bytes(data)
                tmp.replace(xml_path)
                adjusted.append(card.relative(xml_path))
            cache = path.with_name(path.name + ".pk")
            if cache.is_file():
                cache.unlink()
        except (audioedit.EditError, OSError, UnicodeDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        snapshots.after_write(what)
        editor.close(session_id)
        return {"source": session.source, "path": rel, "name": path.name, "adjusted": adjusted}

    @app.post("/api/sample/rename")
    def sample_rename(body: RenameIn) -> dict:
        """Rename a WAV on the card and every reference to it. Without apply only lists what would change."""
        if body.source.partition(":")[0] != "card":
            raise HTTPException(400, "only samples on the card can be renamed here")
        if not snapshots.card_present():
            raise HTTPException(409, "card not connected")
        path = sources.resolve(body.source)
        if not path.is_file() or path.suffix.lower() != ".wav":
            raise HTTPException(404, "WAV file not found")
        rel = card.relative(path)
        block = overwrite_block(rel)
        if block:
            raise HTTPException(403, "Factory samples are never renamed.")
        new_name = body.name.strip()
        if not new_name.lower().endswith(".wav"):
            new_name += ".wav"
        errors, warnings = validate_name(new_name, 64)
        if new_name.casefold() == "preview.wav":
            errors.append("preview.wav is reserved for the patch preview")
        if new_name == path.name:
            errors.append("the name is unchanged")
        clash = [p for p in path.parent.iterdir() if p.name.casefold() == new_name.casefold() and p != path]
        if clash:
            errors.append(f"{clash[0].name} already exists in this folder")
        if errors:
            raise HTTPException(400, "; ".join(errors))
        target = path.with_name(new_name)
        updates: list[tuple[Path, bytes, int, str]] = []
        for ref in find_references(card.root, rel):
            xml_path = card.root / ref.xml
            if any(u[0] == xml_path for u in updates):
                continue
            raw = xml_path.read_bytes()
            bom = raw.startswith(b"\xef\xbb\xbf")
            text = raw.decode("utf-8-sig")
            new_text, count = sampleupdate.rename_in_text(text, ref.xml, rel, new_name)
            if count:
                updates.append((xml_path, (b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8"), count, ref.kind))
        cache = path.with_name(path.name + ".pk")
        summary = {
            "path": rel,
            "new_path": card.relative(target.parent) + "/" + new_name,
            "warnings": warnings,
            "references": [{"xml": card.relative(u[0]), "kind": u[3], "count": u[2]} for u in updates],
            "cache": cache.is_file(),
        }
        if not body.apply:
            return summary
        what = f"renaming {rel} to {new_name}"
        snapshots.before_write(what)
        try:
            for xml_path, _data, _count, _kind in updates:
                backup.save(xml_path)
            backup.save(path)
            # Through a temporary name, so a change of upper and lower case works on FAT32 and exFAT
            temp = path.with_name(path.name + ".blackbook-rename")
            path.rename(temp)
            temp.rename(target)
            backup.record_created(target)
            for xml_path, data, _count, _kind in updates:
                tmp = xml_path.with_name(xml_path.name + ".blackbook-tmp")
                tmp.write_bytes(data)
                tmp.replace(xml_path)
            if cache.is_file():
                cache.unlink()
        except OSError as exc:
            raise HTTPException(400, f"renaming failed: {exc}") from exc
        snapshots.after_write(what)
        new_source = "card:" + card.relative(target)
        for session in editor.sessions.values():
            if session.source == body.source:
                session.source = new_source
                session.name = new_name
        return {**summary, "source": new_source, "name": new_name}

    @app.delete("/api/audio-edit/{session_id}")
    def audio_edit_close(session_id: str) -> dict:
        editor.close(session_id)
        return {"ok": True}

    @app.get("/api/padparams")
    def pad_params() -> list[dict]:
        return padparams.describe()

    def wav_frames(source: str | None) -> int | None:
        if source is None:
            return None
        try:
            return read_info(sources.resolve(source)).frames
        except (WavError, OSError):
            return None

    def window_within(attrs: dict[str, str], frames: int | None, slot: int, adjusted: list[str]) -> dict:
        """Playback window of a pad, shortened when the file on the card is shorter than the patch says."""
        start = int(attrs.get("samstart", 0) or 0)
        length = int(attrs.get("samlen", 0) or 0)
        if frames is not None and start + length > frames:
            start = min(start, max(0, frames - 1))
            length = frames - start
            adjusted.append(f"pad {builder.pad_number(slot)}")
        return {"start": start, "length": length, "frames": frames}

    @app.get("/api/patch/load")
    def patch_load(ref: str) -> dict:
        """Builder state of an existing one-shot or multisample patch."""
        try:
            patch_dir = card.patch_dir(ref)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        text = (patch_dir / "patch.xml").read_bytes().decode("utf-8-sig")
        if not text.strip():
            raise HTTPException(422, DAMAGED_XML.format(name="patch.xml"))
        all_cells = patchedit.cells(text)
        track = re.search(r'<track type="(\w+)"', text)
        track_type = track.group(1) if track else ""
        root = ref.replace("/", "\\").split("\\")[0]

        def source_of(filename: str) -> str | None:
            if not filename:
                return None
            path = resolve_sample_reference(card.root, filename, patch_dir)
            return "card:" + card.relative(path) if path and path.is_file() else None

        def milli_to(value: str | None) -> float:
            return round(int(value or 0) / 1000, 3)

        result: dict = {
            "ref": ref,
            "name": patch_dir.name,
            "is_user": root == "UserPatches",
            "tags": card.load_index(root).tags_for(ref),
        }
        if track_type == "samtrack":
            pads = []
            missing = []
            adjusted: list[str] = []
            for i, cell in enumerate(all_cells):
                if cell.type != "saminst" or "celldisppos" not in cell.attrs:
                    continue
                nxt = all_cells[i + 1] if i + 1 < len(all_cells) and all_cells[i + 1].type == "samasst" else None
                filename = nxt.attrs.get("filename", "") if nxt else ""
                if not filename or filename.endswith("\\"):
                    continue
                source = source_of(filename)
                slot = int(cell.attrs["celldisppos"])
                if source is None:
                    missing.append(filename)
                a = cell.attrs
                pads.append(
                    {
                        "slot": slot,
                        "source": source,
                        "filename": filename,
                        "loop_mode": int(a.get("loopmodes", 0) or 0),
                        "params": padparams.read(a),
                        **window_within(nxt.attrs, wav_frames(source), slot, adjusted),
                    }
                )
            result.update(type="oneshot", pads=pads, missing=missing, adjusted=adjusted)
        elif track_type == "multisamtrack":
            inst = next((c for c in all_cells if c.type == "saminst"), None)
            zones = []
            missing = []
            for cell in all_cells:
                if cell.type != "samasst" or not cell.attrs.get("filename"):
                    continue
                a = cell.attrs
                source = source_of(a["filename"])
                if source is None:
                    missing.append(a["filename"])
                    continue
                vel_high = int(a.get("velrangetop", 127) or 0)
                root_note = int(a.get("rootnote", 60) or 0)
                zones.append(
                    {
                        "source": source,
                        "root": root_note,
                        "root_name": note_name(root_note),
                        "key_low": int(a.get("keyrangebottom", 0) or 0),
                        "key_high": int(a.get("keyrangetop", 127) or 0),
                        "vel_low": int(a.get("velrangebottom", 0) or 0),
                        "vel_high": min(vel_high, 127),
                        "vel_root": int(a.get("velroot", 64) or 0),
                        "warnings": [],
                    }
                )
            result.update(
                type="multisample",
                zones=zones,
                gain=milli_to(inst.attrs.get("gaindb")) if inst else 0.0,
                missing=missing,
            )
        else:
            raise HTTPException(400, f"{track_type or 'this'} patches cannot be edited yet")
        return result

    @app.put("/api/patch/tags")
    def set_tags(body: TagsIn) -> dict:
        root = body.ref.replace("/", "\\").split("\\")[0]
        if root != "UserPatches":
            raise HTTPException(403, "only user patches can be tagged")
        card.patch_dir(body.ref)
        snapshots.before_write(f"tagging {body.ref}")
        index_path = card.index_path("UserPatches")
        backup.save(index_path)
        index = card.load_index("UserPatches")
        index.set_tags(body.ref, body.tags)
        index.save()
        return {"ref": body.ref, "tags": index.tags_for(body.ref)}

    @app.get("/api/projects")
    def projects() -> list[dict]:
        return [asdict(p) for p in card.projects()]

    def project_xml(name: str) -> Path:
        try:
            project_dir = card.safe_path(f"Projects/{name}")
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        xml_path = project_dir / "project.xml"
        if not name.strip() or "/" in name or not xml_path.is_file():
            raise HTTPException(404, f"project not found: {name}")
        return xml_path

    @app.get("/api/project/detail")
    def project_detail(name: str) -> dict:
        """Tempo, tracks, MIDI channels, sequences and the pads of one-shot tracks."""
        xml_path = project_xml(name)
        text = xml_path.read_bytes().decode("utf-8-sig")
        if not text.strip():
            raise HTTPException(422, DAMAGED_XML.format(name="project.xml"))
        data = projectseq.read_project(text)
        for track in data["tracks"]:
            for pad in track["pads"]:
                path = resolve_sample_reference(card.root, pad["filename"], xml_path.parent)
                pad["source"] = f"card:{card.relative(path)}" if path and path.is_file() else None
                pad["frames"] = wav_frames(pad["source"])
        data["name"] = name
        data["autosave"] = (xml_path.parent.parent / f"{name} - autosave" / "project.xml").is_file()
        data["step_lengths"] = projectseq.STEP_LENGTHS
        data["quant_sizes"] = projectseq.QUANT_SIZES
        return data

    def track_pad_updates(
        text: str, index: int, pads: list[PadIn], project_dir: Path, copies: list[tuple[Path, Path]]
    ) -> dict[int, tuple[dict, dict]]:
        """Pad changes of a one-shot track in a project.

        Samples on the card are referenced where they are, relative to the card root. Samples from the
        inbox or a library are copied into the project folder and referenced as .\\name, like recordings.
        """
        track = next((tr for tr in projectseq.tracks(text) if tr.index == index), None)
        if track is None or track.type != "samtrack":
            raise HTTPException(400, f"track {index} is not a one-shot track")
        existing = {p["slot"]: p for p in projectseq.pads_of(text, track)}
        used = {p.name.casefold() for p in project_dir.iterdir()} | {t.name.casefold() for _, t in copies}
        errors: list[str] = []
        updates: dict[int, tuple[dict, dict]] = {}
        listed = set()
        for pad in pads:
            listed.add(pad.slot)
            if not 0 <= pad.slot <= 15:
                raise HTTPException(400, f"invalid pad {pad.slot}")
            if pad.source is None:
                continue
            label = f"pad {builder.pad_number(pad.slot)}"
            errors += padparams.validate(pad.params, label)
            path = sources.resolve(pad.source)
            info = builder.check_wav(path, label, errors, [])
            if info is None:
                continue
            inst = {"loopmodes": pad.loop_mode, **pad.params}
            old = existing.get(pad.slot)
            old_path = resolve_sample_reference(card.root, old["filename"], project_dir) if old else None
            start = pad.start or 0
            length = info.frames - start if pad.length is None else pad.length
            if start < 0 or length < 1 or start + length > info.frames:
                errors.append(f"{label}: start {start} and length {length} exceed the {info.frames} frames of the file")
                continue
            if old_path is not None and old_path.resolve() == path.resolve():
                updates[pad.slot] = (inst, {"samstart": start, "samlen": length})
                continue
            if path.is_relative_to(card.root):
                reference = join_reference(*path.relative_to(card.root).parts)
            else:
                name = path.name
                stem, n = path.stem, 2
                while name.casefold() in used:
                    name = f"{stem}_{n}{path.suffix}"
                    n += 1
                used.add(name.casefold())
                copies.append((path, project_dir / name))
                reference = ".\\" + name
            updates[pad.slot] = (
                inst,
                {"filename": reference, "samstart": start, "samlen": length, "loopstart": 0, "loopend": info.frames},
            )
        for slot, old in existing.items():
            if slot not in listed:
                updates[slot] = ({}, {"filename": "", "samstart": 0, "samlen": 0, "loopstart": 0, "loopend": 0})
        if errors:
            raise HTTPException(400, "; ".join(errors))
        return updates

    @app.put("/api/project/sequences")
    def project_sequences(body: ProjectChangeIn) -> dict:
        """Write MIDI channels and sequences of tracks into a project.xml."""
        if not snapshots.card_present():
            raise HTTPException(409, "card not connected")
        xml_path = project_xml(body.name)
        raw = xml_path.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        copies: list[tuple[Path, Path]] = []
        changes = []
        for t in body.tracks:
            pad_updates = track_pad_updates(text, t.index, t.pads, xml_path.parent, copies) if t.pads is not None else {}
            changes.append(projectseq.TrackChange(t.index, t.midiinchan, t.midioutchan, t.sequences, pad_updates))
        try:
            new_text = projectseq.apply_changes(text, changes)
        except (projectseq.SequenceError, KeyError, TypeError) as exc:
            raise HTTPException(400, f"cannot write the changes: {exc}") from exc
        if new_text == text and not copies:
            return {"changed": False}
        what = f"saving project {body.name}"
        snapshots.before_write(what)
        for src, target in copies:
            shutil.copy2(src, target)
            backup.record_created(target)
        backup.save(xml_path)
        tmp = xml_path.with_name(xml_path.name + ".blackbook-tmp")
        tmp.write_bytes((b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8"))
        tmp.replace(xml_path)
        snapshots.after_write(what)
        return {"changed": True}

    @app.get("/api/project/samples")
    def project_samples(name: str) -> list[dict]:
        """Every WAV a project references, once, with its card path and the number of uses."""
        try:
            project_dir = card.safe_path(f"Projects/{name}")
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        xml_path = project_dir / "project.xml"
        if not xml_path.is_file():
            raise HTTPException(404, f"project not found: {name}")
        root = parse_xml(xml_path)
        found: dict[str, dict] = {}
        for p in root.iter("params"):
            ref = p.get("filename", "")
            if not ref or ref.endswith("\\"):
                continue
            resolved = resolve_sample_reference(card.root, ref, project_dir)
            exists = resolved is not None and resolved.is_file()
            key = card.relative(resolved).casefold() if exists else ref.casefold()
            entry = found.setdefault(key, {
                "filename": ref,
                "path": card.relative(resolved) if exists else "",
                "source": f"card:{card.relative(resolved)}" if exists else None,
                "uses": 0,
            })
            entry["uses"] += 1
        return sorted(found.values(), key=lambda e: (e["path"] or e["filename"]).casefold())

    @app.get("/api/browse")
    def browse_folder(root: str = "card", path: str = "") -> dict:
        base = sources.roots.get(root)
        if base is None:
            raise HTTPException(404, f"unknown root: {root}")
        try:
            entries = browse(base, path)
        except (FileNotFoundError, PermissionError) as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"root": root, "path": path.strip("/"), "entries": [asdict(e) for e in entries]}

    @app.get("/api/audio")
    def audio(src: str) -> FileResponse:
        path = sources.resolve(src)
        if not path.is_file() or path.suffix.lower() != ".wav":
            raise HTTPException(404, "not a WAV file")
        return FileResponse(path, media_type="audio/wav")

    @app.get("/api/wavinfo")
    def wavinfo(src: str) -> dict:
        path = sources.resolve(src)
        try:
            info = read_info(path)
        except (WavError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"info": info.describe(), "frames": info.frames, "duration": info.duration, "cues": info.cues}

    @app.post("/api/multisample/automap")
    def multisample_automap(body: AutomapIn) -> list[dict]:
        pairs = [(s, Path(s.partition(":")[2]).stem) for s in body.sources]
        return [zone_out(z) for z in automap(pairs, body.gap_rule)]

    @app.post("/api/multisample/remap")
    def multisample_remap(body: RemapIn) -> list[dict]:
        zones = [Zone(**z.model_dump()) for z in body.zones]
        assign_key_ranges(zones, body.gap_rule)
        return [zone_out(z) for z in zones]

    @app.post("/api/build/plan")
    def build_plan(body: BuildIn) -> dict:
        plan = make_plan(body)
        repo = snapshots.repo
        if repo is None or not repo.initialized:
            plan.warnings.append(
                "No backup is set up, this change is not saved in a snapshot. Set up the backup in the Backup tab "
                "or keep your own copy of the card."
            )
        return {
            "ok": plan.ok,
            "target": card.relative(plan.target_dir) if plan.target_dir.is_relative_to(card.root) else "",
            "errors": plan.errors,
            "warnings": plan.warnings,
            "files": [{"source": str(c.source), "name": c.target_name, "info": c.info} for c in plan.copies],
            "preview_seconds": round(len(plan.preview) / builder.PREVIEW_RATE, 2) if plan.preview is not None else 0,
            "tags": plan.tags,
            "xml": plan.xml,
        }

    @app.post("/api/build/apply")
    def build_apply(body: BuildIn) -> dict:
        plan = make_plan(body)
        if not plan.ok:
            raise HTTPException(400, "; ".join(plan.errors))
        what = f"{'saving' if plan.mode == 'edit' else 'creating'} {plan.target_ref}"
        snapshots.before_write(what)
        written = builder.apply(card, plan, backup)
        snapshots.after_write(what)
        return {"ref": plan.target_ref, "written": written}

    # ---------- backup ----------

    def snapshot_call(func, *args):
        try:
            return func(*args)
        except SnapshotError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/backup/status")
    def backup_status() -> dict:
        repo = snapshots.repo
        status = repo.status() if repo else {"target": None, "initialized": False}
        status["card_present"] = snapshots.card_present()
        status["events"] = list(snapshots.events)
        status["inside_program"] = bool(repo) and inside_program(repo.target)
        return status

    @app.put("/api/backup/target")
    def backup_target(body: BackupTargetIn) -> dict:
        path = Path(body.path).expanduser()
        if not path.is_absolute():
            raise HTTPException(400, "absolute path required")
        if path.resolve() == card.root or path.resolve().is_relative_to(card.root):
            raise HTTPException(400, "the backup folder must not be on the card")
        if inside_program(path):
            raise HTTPException(400, PROGRAM_FOLDER_MESSAGE)
        # A folder that already holds other files gets its own subfolder for the backup
        try:
            foreign = path.is_dir() and any(path.iterdir()) and not (path / CONFIG_NAME).exists()
        except OSError:
            foreign = False
        if foreign:
            path = path / "blackbook-backup"
        repo = SnapshotRepo(path)
        snapshot_call(repo.init)
        snapshots.repo = repo
        settings.set_value("backup_target", str(repo.target))
        # A new backup folder starts with a complete snapshot of the card
        if snapshots.card_present() and not repo.has_commits():
            commit = snapshot_call(repo.snapshot, card.root, "Initial snapshot")
            snapshots.record("Initial snapshot", commit)
        return repo.status()

    @app.post("/api/backup/setup")
    def backup_setup() -> dict:
        """Set up the suggested backup folder and take the first snapshot."""
        return backup_target(BackupTargetIn(path=str(default_target())))

    # ---------- folder picker ----------

    @app.get("/api/fs/dirs")
    def fs_dirs(path: str = "") -> dict:
        base = Path(path).expanduser() if path else Path.home()
        if not base.is_absolute() or not base.is_dir():
            raise HTTPException(404, f"folder not found: {path}")
        try:
            dirs = sorted(
                (p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")), key=str.casefold
            )
        except OSError as exc:
            raise HTTPException(403, f"cannot open {base}: {exc.strerror}") from exc
        roots = [str(Path.home())]
        if sys.platform == "win32":
            roots += [f"{d}:\\" for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{d}:\\").exists()]
        else:
            roots.append("/")
        return {
            "path": str(base),
            "parent": str(base.parent) if base.parent != base else None,
            "dirs": dirs,
            "roots": roots,
            "is_card": base.resolve() == card.root or base.resolve().is_relative_to(card.root),
            "is_program": inside_program(base),
        }

    @app.post("/api/fs/mkdir")
    def fs_mkdir(body: MkdirIn) -> dict:
        name = body.name.strip()
        if not name or any(ch in name for ch in '/\\:*?"<>|'):
            raise HTTPException(400, "invalid folder name")
        target = Path(body.path) / name
        try:
            target.mkdir(parents=False, exist_ok=False)
        except FileExistsError as exc:
            raise HTTPException(409, f"{name} exists already") from exc
        except OSError as exc:
            raise HTTPException(400, f"cannot create {target}: {exc.strerror}") from exc
        return {"path": str(target)}

    # ---------- first start and updates ----------

    @app.post("/api/welcome/done")
    def welcome_done() -> dict:
        settings.set_value("welcome_done", True)
        return {"ok": True}

    @app.get("/api/update/check")
    def update_check() -> dict:
        return updater.check()

    @app.post("/api/update/apply")
    def update_apply() -> dict:
        try:
            return updater.apply_release()
        except (updater.UpdateError, OSError) as exc:
            raise HTTPException(400, f"update failed: {exc}") from exc

    def stop_server() -> None:
        # The entry point sets stop_server to end uvicorn cleanly; without it the process just ends
        stop = getattr(app.state, "stop_server", None)
        if stop is None:
            os._exit(0)
        stop()

    @app.post("/api/shutdown")
    def shutdown() -> dict:
        # Leave time for the response, then stop so the start script finishes
        threading.Timer(0.5, stop_server).start()
        return {"ok": True}

    @app.post("/api/restart")
    def restart() -> dict:
        app.state.restart_requested = True
        threading.Timer(0.5, stop_server).start()
        return {"ok": True}

    @app.post("/api/backup/snapshot")
    def backup_snapshot(body: SnapshotIn) -> dict:
        repo = snapshots.require()
        if not snapshots.card_present():
            raise HTTPException(409, "card not connected")
        commit = snapshot_call(repo.snapshot, card.root, body.message.strip() or "Manual snapshot")
        return {"commit": asdict(commit) if commit else None}

    @app.get("/api/backup/log")
    def backup_log(limit: int = 200) -> list[dict]:
        repo = snapshots.require()
        return [asdict(c) for c in snapshot_call(repo.log, limit)]

    @app.get("/api/backup/commit")
    def backup_commit(id: str) -> list[dict]:
        repo = snapshots.require()
        return [asdict(c) for c in snapshot_call(repo.changes, id)]

    @app.get("/api/backup/diff")
    def backup_diff(id: str, path: str) -> dict:
        repo = snapshots.require()
        return {"diff": snapshot_call(repo.file_diff, id, path)}

    @app.get("/api/backup/restore-check")
    def backup_restore_check(commit: str, path: str) -> dict:
        """What a restore of a single WAV affects: where it is used and whether its length changes."""
        repo = snapshots.require()
        rel = path.strip("/")
        if not rel.lower().endswith(".wav"):
            return {"is_wav": False}

        def frames_of(data: bytes) -> int | None:
            with tempfile.TemporaryDirectory() as tmp:
                file = Path(tmp) / "snapshot.wav"
                file.write_bytes(data)
                try:
                    return read_info(file).frames
                except (WavError, OSError):
                    return None

        try:
            data = repo.git("show", f"{commit}:{MIRROR}/{rel}", binary=True)
            frames_snapshot = frames_of(data)
            in_snapshot = True
        except SnapshotError:
            frames_snapshot, in_snapshot = None, False
        current = card.root / rel
        try:
            frames_now = read_info(current).frames if current.is_file() else None
        except (WavError, OSError):
            frames_now = None
        refs = find_references(card.root, rel) if snapshots.card_present() else []
        return {
            "is_wav": True,
            "in_snapshot": in_snapshot,
            "frames_snapshot": frames_snapshot,
            "frames_now": frames_now,
            "references": [asdict(r) for r in refs],
        }

    @app.post("/api/backup/restore")
    def backup_restore(body: RestoreIn) -> dict:
        repo = snapshots.require()
        if not snapshots.card_present():
            raise HTTPException(409, "card not connected")
        return snapshot_call(repo.restore, card.root, body.commit, body.path)

    @app.get("/api/backup/config")
    def backup_config() -> dict:
        repo = snapshots.require()
        if not repo.initialized:
            raise HTTPException(409, "backup folder not initialized")
        return {"name": CONFIG_NAME, "text": repo.config_path.read_text(encoding="utf-8")}

    @app.put("/api/backup/config")
    def backup_config_save(body: ConfigIn) -> dict:
        repo = snapshots.require()
        try:
            tomllib.loads(body.text)
        except tomllib.TOMLDecodeError as exc:
            raise HTTPException(400, f"invalid TOML: {exc}") from exc
        repo.config_path.write_text(body.text, encoding="utf-8")
        snapshot_call(repo.config)
        return {"saved": True}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
