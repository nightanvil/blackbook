"""Adjust patches and projects to a WAV whose audio was replaced in place.

Only the attributes `samstart`, `samlen`, `loopstart`, `loopend` and the `pos` of slices in
`samasst` cells that point to the WAV change. Everything else stays byte-identical.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .patchedit import parse_attrs, set_attrs
from .references import reference_target

SAMASST_CELL = re.compile(r'<cell type="samasst">.*?</cell>', re.DOTALL)
PARAMS = re.compile(r"<params\b[^>]*?/>", re.DOTALL)
SLICE_POS = re.compile(r'(<slice\b[^>]*?\bpos=")(\d+)(")')


@dataclass
class CellChange:
    before: dict[str, int]
    after: dict[str, int]
    slices: int = 0
    notes: list[str] = field(default_factory=list)


def _int(attrs: dict[str, str], key: str) -> int | None:
    try:
        return int(attrs[key]) if key in attrs and attrs[key] != "" else None
    except ValueError:
        return None


def adjust_cell(
    attrs: dict[str, str], new_frames: int, mapper: Callable[[int], int]
) -> tuple[dict[str, int], CellChange]:
    """New values for the position attributes of one samasst cell."""
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    notes: list[str] = []
    start = _int(attrs, "samstart")
    length = _int(attrs, "samlen")
    if length is not None:
        old_start = start or 0
        new_start = min(mapper(old_start), new_frames)
        new_end = min(mapper(old_start + length), new_frames)
        if new_end <= new_start:
            new_start, new_end = 0, new_frames
            notes.append("the part the pad played was removed, it now plays the whole sample")
        if start is not None:
            before["samstart"], after["samstart"] = start, new_start
        before["samlen"], after["samlen"] = length, new_end - new_start
    loop_start = _int(attrs, "loopstart")
    loop_end = _int(attrs, "loopend")
    if loop_end is not None:
        new_loop_start = min(mapper(loop_start or 0), new_frames)
        new_loop_end = min(mapper(loop_end), new_frames)
        if new_loop_end <= new_loop_start:
            new_loop_start, new_loop_end = after.get("samstart", 0), after.get("samstart", 0) + after.get(
                "samlen", new_frames
            )
            notes.append("the loop was removed, it now spans the played part")
        if loop_start is not None:
            before["loopstart"], after["loopstart"] = loop_start, new_loop_start
        before["loopend"], after["loopend"] = loop_end, new_loop_end
    changes = {k: v for k, v in after.items() if before.get(k) != v}
    return changes, CellChange(before, after, notes=notes)


def adjust_text(
    text: str, xml_rel: str, wav_rel: str, new_frames: int, mapper: Callable[[int], int]
) -> tuple[str, list[CellChange]]:
    """Return the XML text with every samasst cell for wav_rel adjusted, and what changed per cell."""
    wanted = wav_rel.strip("/").casefold()
    pieces: list[str] = []
    changes: list[CellChange] = []
    last = 0
    for cell in SAMASST_CELL.finditer(text):
        params = PARAMS.search(cell.group())
        if params is None:
            continue
        attrs = parse_attrs(params.group())
        filename = attrs.get("filename", "")
        if not filename or filename.endswith("\\") or reference_target(filename, xml_rel) != wanted:
            continue
        values, change = adjust_cell(attrs, new_frames, mapper)
        cell_text = cell.group()
        new_params = set_attrs(params.group(), values) if values else params.group()
        cell_text = cell_text[: params.start()] + new_params + cell_text[params.end():]

        def move_slice(m: re.Match[str], change: CellChange = change) -> str:
            old = int(m.group(2))
            new = min(mapper(old), max(new_frames - 1, 0))
            if new != old:
                change.slices += 1
            return f"{m.group(1)}{new}{m.group(3)}"

        cell_text = SLICE_POS.sub(move_slice, cell_text)
        pieces.append(text[last:cell.start()])
        pieces.append(cell_text)
        last = cell.end()
        changes.append(change)
    pieces.append(text[last:])
    return "".join(pieces), changes


def describe(change: CellChange) -> str:
    parts = [f"{k} {change.before[k]} to {change.after[k]}" for k in change.after if change.before[k] != change.after[k]]
    if change.slices:
        parts.append(f"{change.slices} slice positions moved")
    if not parts:
        parts.append("no change needed")
    return ", ".join(parts + change.notes)
