"""Reading and format-preserving updates of patchindex.xml."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

BOM = "﻿"

FACTORY_TAGS = [
    "Atmosphere",
    "Bass",
    "Drum",
    "Foley",
    "Guitar",
    "Keys",
    "Lead",
    "Orchestral",
    "Organ",
    "Pad",
    "Percussion",
    "SFX",
    "Strings",
    "Synth",
    "Vocal",
]

EMPTY_INDEX = '<?xml version="1.0" encoding="UTF-8"?>\n<patchmetadata version="1">\n</patchmetadata>\n'


def _key(path: str) -> str:
    return path.replace("/", "\\").strip("\\").casefold()


class PatchIndex:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            raw = path.read_bytes().decode("utf-8")
            self.has_bom = raw.startswith(BOM)
            self.text = raw[1:] if self.has_bom else raw
        else:
            # The device writes UserPatches/patchindex.xml without BOM
            self.has_bom = False
            self.text = EMPTY_INDEX
        self.entries = self._parse()

    def _parse(self) -> dict[str, tuple[str, list[str]]]:
        entries: dict[str, tuple[str, list[str]]] = {}
        root = ET.fromstring(self.text.encode("utf-8"))
        for patch in root.iter("patch"):
            path = patch.get("path", "")
            tags = [t.text.strip() for t in patch.findall("tag") if t.text and t.text.strip()]
            entries[_key(path)] = (path, tags)
        return entries

    def tags_for(self, path: str) -> list[str]:
        entry = self.entries.get(_key(path))
        return list(entry[1]) if entry else []

    def all_tags(self) -> set[str]:
        return {tag for _, tags in self.entries.values() for tag in tags}

    def _block_pattern(self, path: str) -> re.Pattern[str]:
        stored = self.entries.get(_key(path), (path, []))[0]
        attr = re.escape(escape(stored, {'"': "&quot;"}))
        return re.compile(r'[ \t]*<patch\s+path="' + attr + r'"\s*>.*?</patch>[ \t]*\r?\n?', re.DOTALL)

    def set_tags(self, path: str, tags: list[str]) -> None:
        """Replace the tags of a patch. An empty tag list removes the entry."""
        tags = [t for t in dict.fromkeys(t.strip() for t in tags) if t]
        pattern = self._block_pattern(path)
        existing = pattern.search(self.text)

        block = ""
        if tags:
            lines = [f"    <patch path={quoteattr(path)}>"]
            lines += [f"        <tag>{escape(tag)}</tag>" for tag in tags]
            lines.append("    </patch>")
            block = "\n".join(lines) + "\n"

        if existing:
            self.text = self.text[: existing.start()] + block + self.text[existing.end() :]
        elif block:
            close = self.text.rfind("</patchmetadata>")
            if close < 0:
                raise ValueError(f"no closing patchmetadata element in {self.path}")
            line_start = self.text.rfind("\n", 0, close) + 1
            self.text = self.text[:line_start] + block + self.text[line_start:]

        self.entries = self._parse()

    def render(self) -> bytes:
        return ((BOM if self.has_bom else "") + self.text).encode("utf-8")

    def save(self) -> None:
        self.path.write_bytes(self.render())
