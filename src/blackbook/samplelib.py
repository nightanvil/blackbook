"""All WAVs on the card with the patches and projects that use them, for the Samples tab."""

from __future__ import annotations

import re
from pathlib import Path

from .references import ATTR, SAMASST, reference_target, xml_files
from .wav import WavError, read_info

USER_ROOTS = ("Projects", "UserPatches", "Samples")
FACTORY_ROOT = "Patches"
RECORDING = re.compile(r"^RC\d+\.wav$", re.IGNORECASE)


def usage_map(card_root: Path) -> dict[str, list[dict]]:
    """Card relative WAV path (casefolded) to the patches and projects that reference it."""
    uses: dict[str, list[dict]] = {}
    for xml_rel, kind in xml_files(card_root):
        try:
            text = (card_root / xml_rel).read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        owner = xml_rel.split("/")[-2]
        for match in SAMASST.finditer(text):
            filename = dict(ATTR.findall(match.group(1))).get("filename", "")
            if not filename or filename.endswith("\\"):
                continue
            entries = uses.setdefault(reference_target(filename, xml_rel), [])
            if not any(e["xml"] == xml_rel for e in entries):
                entries.append({"xml": xml_rel, "kind": kind, "name": owner})
    return uses


def sample_index(card_root: Path, include_factory: bool = False) -> list[dict]:
    uses = usage_map(card_root)
    roots = USER_ROOTS + ((FACTORY_ROOT,) if include_factory else ())
    result: list[dict] = []
    for root in roots:
        base = card_root / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() != ".wav" or not path.is_file() or path.name.lower() == "preview.wav":
                continue
            rel = path.relative_to(card_root).as_posix()
            factory = root == FACTORY_ROOT
            entry = {
                "path": rel,
                "name": path.name,
                "folder": rel.rsplit("/", 1)[0],
                "source": f"card:{rel}",
                "size": path.stat().st_size,
                "duration": None,
                "factory": factory,
                "recording": root == "Projects" and bool(RECORDING.match(path.name)),
                "uses": uses.get(rel.casefold(), []),
            }
            if not factory:
                try:
                    entry["duration"] = round(read_info(path).duration, 3)
                except (WavError, OSError):
                    pass
            result.append(entry)
    return result
