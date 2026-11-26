"""Read access to a blackbox 2 card: patches, projects and sample folders."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .cardpath import card_reference, resolve_sample_reference
from .patchindex import PatchIndex
from .wav import WavError, read_info

PATCH_ROOTS = ("Patches", "UserPatches")

PATCH_TYPES = {
    "OneShots": "samtrack",
    "SampInst": "multisamtrack",
    "Loops": "looptrack",
    "Slicer": "slicertrack",
    "Shredder": "granslicertrack",
}

IGNORED_DIRS = {".trash-1000", "system volume information", "$recycle.bin", ".spotlight-v100", ".fseventsd"}


def parse_xml(path: Path) -> ET.Element:
    return ET.fromstring(path.read_bytes().decode("utf-8-sig").encode("utf-8"))


@dataclass
class PatchSummary:
    ref: str
    root: str
    type: str
    name: str
    tags: list[str]
    wav_count: int
    has_preview: bool

    @property
    def is_user(self) -> bool:
        return self.root == "UserPatches"


@dataclass
class SampleRef:
    filename: str
    resolved: str | None
    samlen: int
    attrs: dict[str, str]
    slot: int | None = None
    instrument: dict[str, str] = field(default_factory=dict)


@dataclass
class ProjectSummary:
    name: str
    is_autosave: bool
    wav_files: int
    references: int
    missing: list[str]
    unused: list[str]


class Card:
    def __init__(self, root: Path):
        # The card may be absent, for example while the blackbox is not in microSD mode
        self.root = root.resolve()

    def index_path(self, patch_root: str) -> Path:
        return self.root / patch_root / "patchindex.xml"

    def load_index(self, patch_root: str) -> PatchIndex:
        return PatchIndex(self.index_path(patch_root))

    def patches(self) -> list[PatchSummary]:
        result: list[PatchSummary] = []
        for patch_root in PATCH_ROOTS:
            base = self.root / patch_root
            if not base.is_dir():
                continue
            index = self.load_index(patch_root)
            for type_dir in sorted(base.iterdir()):
                if not type_dir.is_dir() or type_dir.name not in PATCH_TYPES:
                    continue
                for patch_dir in sorted(type_dir.iterdir(), key=lambda p: p.name.casefold()):
                    if not (patch_dir / "patch.xml").is_file():
                        continue
                    ref = card_reference(self.root, patch_dir)
                    wavs = [p for p in patch_dir.iterdir() if p.suffix.lower() == ".wav"]
                    result.append(
                        PatchSummary(
                            ref=ref,
                            root=patch_root,
                            type=type_dir.name,
                            name=patch_dir.name,
                            tags=index.tags_for(ref),
                            wav_count=sum(1 for p in wavs if p.name.lower() != "preview.wav"),
                            has_preview=(patch_dir / "preview.wav").is_file(),
                        )
                    )
        return result

    def patch_dir(self, ref: str) -> Path:
        path = self.safe_path(ref.replace("\\", "/"))
        if not (path / "patch.xml").is_file():
            raise FileNotFoundError(f"no patch at {ref}")
        return path

    def patch_samples(self, ref: str) -> tuple[str, list[SampleRef]]:
        """Return the track type and the sample cells of a patch in file order."""
        patch_dir = self.patch_dir(ref)
        root = parse_xml(patch_dir / "patch.xml")
        track = root.find("./session/track")
        if track is None:
            return "", []
        samples: list[SampleRef] = []
        last_instrument: dict[str, str] = {}
        for cell in track.findall("cell"):
            params = cell.find("params")
            attrs = dict(params.attrib) if params is not None else {}
            cell_type = cell.get("type")
            if cell_type in ("saminst", "loopinst"):
                last_instrument = attrs
            elif cell_type == "samasst":
                filename = attrs.get("filename", "")
                resolved = resolve_sample_reference(self.root, filename, patch_dir) if filename else None
                slot = last_instrument.get("celldisppos")
                samples.append(
                    SampleRef(
                        filename=filename,
                        resolved=self.relative(resolved) if resolved and resolved.is_file() else None,
                        samlen=int(attrs.get("samlen", "0") or 0),
                        attrs=attrs,
                        slot=int(slot) if slot is not None and track.get("type") == "samtrack" else None,
                        instrument=last_instrument if track.get("type") == "samtrack" else {},
                    )
                )
        return track.get("type", ""), samples

    def projects(self) -> list[ProjectSummary]:
        base = self.root / "Projects"
        if not base.is_dir():
            return []
        result: list[ProjectSummary] = []
        for project_dir in sorted(base.iterdir(), key=lambda p: p.name.casefold()):
            xml_path = project_dir / "project.xml"
            if not xml_path.is_file():
                continue
            try:
                root = parse_xml(xml_path)
            except ET.ParseError:
                continue
            refs = [
                p.get("filename", "")
                for p in root.iter("params")
                if p.get("filename") and not p.get("filename", "").endswith("\\")
            ]
            missing: list[str] = []
            used_local: set[str] = set()
            for ref in refs:
                resolved = resolve_sample_reference(self.root, ref, project_dir)
                if resolved is None or not resolved.is_file():
                    missing.append(ref)
                elif resolved.parent == project_dir:
                    used_local.add(resolved.name.casefold())
            local_wavs = [p for p in project_dir.rglob("*") if p.suffix.lower() == ".wav"]
            unused = sorted(
                p.name for p in local_wavs if p.parent == project_dir and p.name.casefold() not in used_local
            )
            result.append(
                ProjectSummary(
                    name=project_dir.name,
                    is_autosave=project_dir.name.endswith(" - autosave"),
                    wav_files=len(local_wavs),
                    references=len(refs),
                    missing=sorted(set(missing)),
                    unused=unused,
                )
            )
        return result

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def safe_path(self, rel: str) -> Path:
        """Map a slash separated card relative path to a file system path inside the card."""
        path = (self.root / rel.strip("/")).resolve()
        if path != self.root and not path.is_relative_to(self.root):
            raise PermissionError(f"path outside of card: {rel}")
        return path


@dataclass
class BrowseEntry:
    name: str
    kind: str
    path: str
    info: str = ""
    duration: float = 0.0
    frames: int = 0


def browse(base: Path, rel: str) -> list[BrowseEntry]:
    """List subfolders and WAV files of a folder below base."""
    folder = (base / rel.strip("/")).resolve()
    if folder != base and not folder.is_relative_to(base):
        raise PermissionError(f"path outside of root: {rel}")
    if not folder.is_dir():
        raise FileNotFoundError(rel)

    dirs: list[BrowseEntry] = []
    files: list[BrowseEntry] = []
    for entry in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        if entry.name.startswith(".") or entry.name.casefold() in IGNORED_DIRS:
            continue
        rel_path = entry.relative_to(base).as_posix()
        if entry.is_dir():
            dirs.append(BrowseEntry(name=entry.name, kind="dir", path=rel_path))
        elif entry.suffix.lower() == ".wav":
            try:
                info = read_info(entry)
                files.append(
                    BrowseEntry(
                        name=entry.name,
                        kind="wav",
                        path=rel_path,
                        info=info.describe(),
                        duration=round(info.duration, 3),
                        frames=info.frames,
                    )
                )
            except (WavError, OSError) as exc:
                files.append(BrowseEntry(name=entry.name, kind="wav", path=rel_path, info=f"unreadable: {exc}"))
    return dirs + files
