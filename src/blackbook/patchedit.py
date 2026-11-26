"""Targeted edits of an existing patch.xml.

Only the attributes and cells handled by the builder change. Everything else,
such as sequences, modulation sources and parameters the builder does not know,
stays byte-identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.sax.saxutils import escape, unescape

from . import templates

CELL_RE = re.compile(r'(?P<indent>[ \t]*)<cell type="(?P<type>\w+)">.*?</cell>[ \t]*\r?\n?', re.DOTALL)
PARAMS_RE = re.compile(r"<params\b[^>]*?/>", re.DOTALL)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


@dataclass
class Cell:
    type: str
    start: int
    end: int
    indent: str
    params_start: int
    params_end: int
    attrs: dict[str, str]


def parse_attrs(params_text: str) -> dict[str, str]:
    return {k: unescape(v, {"&quot;": '"'}) for k, v in ATTR_RE.findall(params_text)}


def cells(text: str) -> list[Cell]:
    result: list[Cell] = []
    for m in CELL_RE.finditer(text):
        p = PARAMS_RE.search(text, m.start(), m.end())
        if p is None:
            result.append(Cell(m.group("type"), m.start(), m.end(), m.group("indent"), -1, -1, {}))
        else:
            result.append(
                Cell(m.group("type"), m.start(), m.end(), m.group("indent"), p.start(), p.end(), parse_attrs(p.group()))
            )
    return result


def set_attrs(params_text: str, values: dict[str, object]) -> str:
    """Replace attribute values in a <params .../> element, appending missing ones."""
    for key, value in values.items():
        encoded = escape(str(value), {'"': "&quot;"})
        pattern = re.compile(r"(\b" + re.escape(key) + r'=")[^"]*(")')
        if pattern.search(params_text):
            params_text = pattern.sub(lambda m, v=encoded: m.group(1) + v + m.group(2), params_text, count=1)
        else:
            params_text = re.sub(r"\s*/>$", f' {key}="{encoded}"/>', params_text)
    return params_text


class Editor:
    def __init__(self, text: str):
        self.text = text
        self.cells = cells(text)
        self._replacements: list[tuple[int, int, str]] = []

    def update_params(self, cell: Cell, values: dict[str, object]) -> None:
        if not values or cell.params_start < 0:
            return
        old = self.text[cell.params_start : cell.params_end]
        new = set_attrs(old, values)
        if new != old:
            self._replacements.append((cell.params_start, cell.params_end, new))

    def remove(self, cell: Cell) -> None:
        self._replacements.append((cell.start, cell.end, ""))

    def insert(self, position: int, text: str) -> None:
        self._replacements.append((position, position, text))

    def result(self) -> str:
        text = self.text
        # Apply from the end so earlier offsets stay valid; inserts at equal positions keep their order
        for start, end, new in sorted(self._replacements, key=lambda r: (r[0], r[1]), reverse=True):
            text = text[:start] + new + text[end:]
        return text


def edit_oneshot(text: str, updates: dict[int, tuple[dict, dict]]) -> tuple[str, list[str]]:
    """updates maps celldisppos to (saminst values, samasst values)."""
    editor = Editor(text)
    errors: list[str] = []
    slots = {}
    for i, cell in enumerate(editor.cells):
        if cell.type == "saminst" and "celldisppos" in cell.attrs:
            nxt = editor.cells[i + 1] if i + 1 < len(editor.cells) and editor.cells[i + 1].type == "samasst" else None
            slots[int(cell.attrs["celldisppos"])] = (cell, nxt)

    for slot, (inst_values, asst_values) in updates.items():
        if slot not in slots:
            number = slot - 7 if slot >= 8 else slot + 9
            errors.append(f"pad {number} has no cell in the base patch")
            continue
        inst, asst = slots[slot]
        editor.update_params(inst, inst_values)
        if asst_values:
            if asst is None:
                lines = templates.samasst_cell(asst_values, inst.indent)
                editor.insert(inst.end, "\n".join(lines) + "\n")
            else:
                editor.update_params(asst, asst_values)
    return editor.result(), errors


def edit_multisample(
    text: str, inst_values: dict, keep: list[tuple[str, dict]], add: list[dict]
) -> tuple[str, list[str]]:
    """Update, remove and add samasst cells of a multisample track.

    keep lists (existing filename, new values) for zones that stay. Existing
    samasst cells not listed in keep are removed, add creates new cells.
    """
    editor = Editor(text)
    errors: list[str] = []
    inst = next((c for c in editor.cells if c.type == "saminst"), None)
    assts = [c for c in editor.cells if c.type == "samasst"]
    if inst is not None:
        editor.update_params(inst, inst_values)

    unused = list(assts)
    for filename, values in keep:
        match = next((c for c in unused if c.attrs.get("filename", "").casefold() == filename.casefold()), None)
        if match is None:
            errors.append(f"zone {filename} not found in the base patch")
            continue
        unused.remove(match)
        editor.update_params(match, values)
    for cell in unused:
        editor.remove(cell)

    if add:
        anchor = assts[-1] if assts else inst
        if anchor is None:
            errors.append("base patch has no instrument cell")
        else:
            indent = anchor.indent
            block = "".join("\n".join(templates.samasst_cell(values, indent)) + "\n" for values in add)
            editor.insert(anchor.end, block)
    return editor.result(), errors


def set_track_params(text: str, values: dict[str, object]) -> str:
    """Update attributes of the track's own <params/> element."""
    track = re.search(r"<track\b[^>]*>", text)
    if not track:
        return text
    params = PARAMS_RE.search(text, track.end())
    if not params:
        return text
    return text[: params.start()] + set_attrs(params.group(), values) + text[params.end() :]
