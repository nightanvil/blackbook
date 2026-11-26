"""Find the patches and projects that reference a WAV file on the card."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .cardpath import split_reference

SAMASST = re.compile(r'<cell type="samasst"[^>]*>\s*<params ([^>]*?)/?>')
ATTR = re.compile(r'(\w+)="([^"]*)"')


@dataclass
class Reference:
    xml: str  # card relative path of the patch.xml or project.xml, with forward slashes
    kind: str  # patch or project
    samlen: int


def reference_target(ref: str, owner_rel: str) -> str:
    """Card relative path (forward slashes, casefolded) a samasst filename points to.

    Bare names and names starting with '.' are relative to the folder of the XML file,
    all others to the card root. The file does not need to exist.
    """
    normalized = ref.replace("/", "\\")
    parts = [p for p in split_reference(normalized) if p != "."]
    if normalized.startswith(".\\") or "\\" not in normalized:
        owner = [p for p in owner_rel.split("/")[:-1] if p]
        parts = owner + parts
    return "/".join(parts).casefold()


def xml_files(card_root: Path) -> list[tuple[str, str]]:
    """All patch.xml and project.xml files as (card relative path, kind)."""
    found: list[tuple[str, str]] = []
    for base, pattern, kind in (
        ("Patches", "*/*/patch.xml", "patch"),
        ("UserPatches", "*/*/patch.xml", "patch"),
        ("Projects", "*/project.xml", "project"),
    ):
        folder = card_root / base
        if folder.is_dir():
            found += [(p.relative_to(card_root).as_posix(), kind) for p in sorted(folder.glob(pattern))]
    return found


def find_references(card_root: Path, wav_rel: str) -> list[Reference]:
    """Every samasst entry in patches and projects that points to the WAV at wav_rel."""
    wanted = wav_rel.strip("/").casefold()
    result: list[Reference] = []
    for xml_rel, kind in xml_files(card_root):
        try:
            text = (card_root / xml_rel).read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        for match in SAMASST.finditer(text):
            attrs = dict(ATTR.findall(match.group(1)))
            filename = attrs.get("filename", "")
            if not filename or filename.endswith("\\"):
                continue
            if reference_target(filename, xml_rel) == wanted:
                try:
                    samlen = int(attrs.get("samlen", 0) or 0)
                except ValueError:
                    samlen = 0
                result.append(Reference(xml_rel, kind, samlen))
    return result
