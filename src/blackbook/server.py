"""FastAPI application serving the API and the browser UI."""

from __future__ import annotations

import re
import threading
import time
import tomllib
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import builder, patchedit, settings
from .backup import Backup
from .card import Card, browse
from .cardpath import INVALID_NAME_CHARS, resolve_sample_reference
from .mapping import Zone, assign_key_ranges, automap, note_name
from .patchindex import FACTORY_TAGS
from .snapshot import CONFIG_NAME, SnapshotError, SnapshotRepo
from .wav import WavError, read_info

STATIC_DIR = Path(__file__).parent / "static"


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

    def __init__(self, card: Card, target: Path | None):
        self.card = card
        self.repo = SnapshotRepo(target) if target else None
        self.last_event = ""
        self._stop = threading.Event()

    def require(self) -> SnapshotRepo:
        if self.repo is None:
            raise HTTPException(409, "no backup folder configured")
        return self.repo

    def card_present(self) -> bool:
        return (self.card.root / "bb2-stng.mml").is_file() or (self.card.root / "Projects").is_dir()

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
            self.last_event = f"{time.strftime('%H:%M')} {reason} failed: {exc}"

    def record(self, reason: str, commit) -> None:
        stamp = time.strftime("%H:%M")
        if commit:
            self.last_event = f"{stamp} snapshot created: {commit.subject}"
        else:
            self.last_event = f"{stamp} {reason}: no changes since the last snapshot, none created"

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
            self.last_event = f"{time.strftime('%H:%M')} After {what} failed: {exc}"

    def watch(self) -> None:
        present = False
        while not self._stop.is_set():
            now = self.card_present()
            if now and not present:
                self.auto_snapshot("Card connected", "snapshot_on_connect")
            present = now
            self._stop.wait(5)

    def stop(self) -> None:
        self._stop.set()


def create_app(
    card_root: Path,
    libraries: list[Path],
    backup_dir: Path,
    snapshot_target: Path | None = None,
    inbox_dir: Path | None = None,
) -> FastAPI:
    card = Card(card_root)
    sources = Sources(card, libraries, inbox_dir or settings.REPO_DIR / ".blackbook" / "inbox")
    backup = Backup(backup_dir, card.root)
    target = snapshot_target or (Path(settings.get("backup_target")) if settings.get("backup_target") else None)
    snapshots = SnapshotService(card, target)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        watcher = threading.Thread(target=snapshots.watch, name="card-watcher", daemon=True)
        watcher.start()
        yield
        snapshots.stop()

    app = FastAPI(title="blackbook", lifespan=lifespan)

    def make_base(body: BuildIn) -> builder.Base | None:
        if not body.base_ref or body.mode == "new":
            return None
        if body.mode not in ("edit", "copy"):
            raise HTTPException(400, f"unknown mode: {body.mode}")
        try:
            return builder.Base.load(card.patch_dir(body.base_ref), body.mode)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

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

    @app.get("/api/info")
    def info() -> dict:
        return {
            "card": str(card.root),
            "roots": [{"id": k, "path": str(v)} for k, v in sources.roots.items()],
            "backup": str(backup.dir),
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

    @app.get("/api/patch/load")
    def patch_load(ref: str) -> dict:
        """Builder state of an existing one-shot or multisample patch."""
        try:
            patch_dir = card.patch_dir(ref)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        text = (patch_dir / "patch.xml").read_bytes().decode("utf-8-sig")
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
                        "gain": milli_to(a.get("gaindb")),
                        "pitch": milli_to(a.get("pitch")),
                        "pan": int(a.get("panpos", 0) or 0),
                        "choke_group": int(a.get("chokegrp", 0) or 0),
                        "reverse": a.get("reverse", "0") != "0",
                        "loop_mode": int(a.get("loopmodes", 0) or 0),
                    }
                )
            result.update(type="oneshot", pads=pads, missing=missing)
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
        status["last_event"] = snapshots.last_event
        return status

    @app.put("/api/backup/target")
    def backup_target(body: BackupTargetIn) -> dict:
        path = Path(body.path).expanduser()
        if not path.is_absolute():
            raise HTTPException(400, "absolute path required")
        if path.resolve() == card.root or path.resolve().is_relative_to(card.root):
            raise HTTPException(400, "the backup folder must not be on the card")
        repo = SnapshotRepo(path)
        snapshot_call(repo.init)
        snapshots.repo = repo
        settings.set_value("backup_target", str(repo.target))
        return repo.status()

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
