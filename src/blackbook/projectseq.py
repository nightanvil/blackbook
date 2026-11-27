"""Tracks, MIDI channels and sequences of a project.xml, read and targeted writes.

Writes touch only the track attributes `midiinchan` and `midioutchan`, the `<params>` of the edited
`noteseq` cells and their `<sequence>` element. Everything else stays byte-identical. The encoding
is described in docs/card-format.md, section Sequences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import padparams
from .patchedit import cells, edit_oneshot, parse_attrs, set_attrs

TICKS_PER_STEP = 960
OFFSET_UNIT = 10
MAX_OFFSET = 47
MAX_STEPS = 256

STEP_LENGTHS = [
    "8 bars", "4 bars", "2 bars", "1 bar", "1/2", "1/2T", "1/4", "1/4T",
    "1/8", "1/8T", "1/16", "1/16T", "1/32", "1/32T", "1/64", "1/64T",
]
QUANT_SIZES = ["2 bars", "1 bar", "1/2", "1/2T", "1/4", "1/4T", "1/8", "1/8T", "1/16", "1/16T", "1/32", "1/32T", "1/64"]

TRACK_RE = re.compile(r'<track type="(?P<type>\w+)">(?P<body>.*?)</track>', re.DOTALL)
PARAMS_RE = re.compile(r"<params\b[^>]*?/>", re.DOTALL)
NOTESEQ_RE = re.compile(r'(?P<indent>[ \t]*)<cell type="noteseq">.*?</cell>', re.DOTALL)
SEQUENCE_RE = re.compile(r"<sequence\s*/>|<sequence>.*?</sequence>", re.DOTALL)
EVENT_RE = re.compile(r"<seqevent\b([^>]*?)/>", re.DOTALL)

EVENT_KNOWN = ("step", "chan", "type", "strtks", "pitch", "lencount", "lentks", "velocity", "cond")
SEQ_DEFAULTS = {
    "notesteplen": "10",
    "notestepcount": "16",
    "notestepcountset": "1",
    "seqstepmode": "1",
    "quantsizeseq": "1",
    "uiseqknobmode": "2",
    "seqslide": "0",
}


class SequenceError(Exception):
    pass


def _int(attrs: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(attrs.get(key, default) or default)
    except ValueError:
        return default


@dataclass
class Track:
    index: int
    type: str
    start: int  # offset of the track body in the text
    end: int
    attrs: dict[str, str]
    params_span: tuple[int, int]


def tracks(text: str) -> list[Track]:
    result: list[Track] = []
    for i, m in enumerate(TRACK_RE.finditer(text)):
        body_start = m.start("body")
        p = PARAMS_RE.search(text, body_start, m.end("body"))
        attrs = parse_attrs(p.group()) if p else {}
        span = (p.start(), p.end()) if p else (-1, -1)
        result.append(Track(i, m.group("type"), body_start, m.end("body"), attrs, span))
    return result


def read_event(attrs: dict[str, str]) -> dict:
    step = _int(attrs, "step")
    start = _int(attrs, "strtks", step * TICKS_PER_STEP)
    return {
        "step": step,
        "chan": _int(attrs, "chan"),
        "offset": round((start - step * TICKS_PER_STEP) / OFFSET_UNIT),
        "strtks": start,
        "pitch": _int(attrs, "pitch"),
        "lencount": _int(attrs, "lencount", 1),
        "lentks": _int(attrs, "lentks", TICKS_PER_STEP),
        "velocity": _int(attrs, "velocity") if "velocity" in attrs else None,
        "prob": _int(attrs, "cond", 100) if "cond" in attrs else 100,
        "type": attrs.get("type", "note"),
        "extra": {k: v for k, v in attrs.items() if k not in EVENT_KNOWN},
    }


def read_sequence(cell_text: str) -> dict:
    p = PARAMS_RE.search(cell_text)
    attrs = parse_attrs(p.group()) if p else {}
    seq = SEQUENCE_RE.search(cell_text)
    events = [read_event(parse_attrs(e)) for e in EVENT_RE.findall(seq.group())] if seq else []
    return {
        "slot": _int(attrs, "celldisppos"),
        "name": attrs.get("cellname", ""),
        "steplen": _int(attrs, "notesteplen", 10),
        "stepcount": _int(attrs, "notestepcount", 16),
        "quant": _int(attrs, "quantsizeseq", 1),
        "snap": _int(attrs, "seqstepmode", 1) == 1,
        "automation": "<automation" in cell_text,
        "events": events,
    }


def pads_of(text: str, track: Track) -> list[dict]:
    """Pads of a one-shot track: position, file reference, window and sound parameters."""
    body = text[track.start:track.end]
    all_cells = cells(body)
    pads: list[dict] = []
    for i, cell in enumerate(all_cells):
        if cell.type != "saminst" or "celldisppos" not in cell.attrs:
            continue
        nxt = all_cells[i + 1] if i + 1 < len(all_cells) and all_cells[i + 1].type == "samasst" else None
        filename = nxt.attrs.get("filename", "") if nxt else ""
        if not filename or filename.endswith("\\"):
            continue
        pads.append(
            {
                "slot": int(cell.attrs["celldisppos"]),
                "filename": filename,
                "start": _int(nxt.attrs, "samstart"),
                "length": _int(nxt.attrs, "samlen"),
                "loop_mode": _int(cell.attrs, "loopmodes"),
                "params": padparams.read(cell.attrs),
            }
        )
    return pads


def read_project(text: str) -> dict:
    """Tempo, swing and the instrument tracks with their sequences."""
    result: dict = {"tempo": 120, "swing": 50, "tracks": []}
    for track in tracks(text):
        if track.type == "mastrack":
            result["tempo"] = _int(track.attrs, "globtempo", 120)
            result["swing"] = _int(track.attrs, "swing", 50)
            continue
        body = text[track.start:track.end]
        sequences = sorted((read_sequence(m.group()) for m in NOTESEQ_RE.finditer(body)), key=lambda s: s["slot"])
        samples = sum(
            1
            for c in cells(body)
            if c.type == "samasst" and c.attrs.get("filename") and not c.attrs["filename"].endswith("\\")
        )
        result["tracks"].append(
            {
                "index": track.index,
                "position": _int(track.attrs, "celldisppos", track.index),
                "samples": samples,
                "type": track.type,
                "name": track.attrs.get("cellname", ""),
                "midiinchan": _int(track.attrs, "midiinchan"),
                "midioutchan": _int(track.attrs, "midioutchan"),
                "sequences": sequences,
                "pads": pads_of(text, track) if track.type == "samtrack" else [],
            }
        )
    # The device shows the tracks by their position, not by their order in the file
    result["tracks"].sort(key=lambda t: t["position"])
    return result


# ---------- writing ----------


def _check(value: int, low: int, high: int, what: str) -> int:
    if not isinstance(value, int) or not low <= value <= high:
        raise SequenceError(f"{what} must be between {low} and {high}, got {value}")
    return value


def event_xml(event: dict) -> str:
    """One event. strtks and lentks are written as given; the editor derives them from offset and length."""
    step = _check(event["step"], 0, MAX_STEPS - 1, "step")
    chan = _check(event.get("chan", 0), 0, 127, "pad")
    start = _check(event.get("strtks", step * TICKS_PER_STEP), 0, MAX_STEPS * TICKS_PER_STEP, "start")
    lencount = _check(event.get("lencount", 1), 0, MAX_STEPS, "length")
    lentks = _check(event.get("lentks", max(lencount, 1) * TICKS_PER_STEP), 1, 64 * MAX_STEPS * TICKS_PER_STEP, "length in ticks")
    parts = [f'step="{step}"']
    if chan:
        parts.append(f'chan="{chan}"')
    parts += [
        f'type="{event.get("type", "note")}"',
        f'strtks="{start}"',
        f'pitch="{_check(event.get("pitch", 0), 0, 127, "pitch")}"',
        f'lencount="{lencount}"',
        f'lentks="{lentks}"',
    ]
    if event.get("velocity") is not None:
        parts.append(f'velocity="{_check(event["velocity"], 1, 127, "velocity")}"')
    prob = _check(event.get("prob", 100), 1, 100, "probability")
    if prob < 100:
        parts.append(f'cond="{prob}"')
    for key, value in (event.get("extra") or {}).items():
        if re.fullmatch(r"\w+", key) and key not in EVENT_KNOWN:
            parts.append(f'{key}="{value}"')
    return "<seqevent " + " ".join(parts) + "/>"


def sequence_xml(events: list[dict], indent: str, newline: str) -> str:
    if not events:
        return "<sequence/>"
    lines = ["<sequence>"]
    lines += [f"{indent}    {event_xml(e)}" for e in events]
    lines.append(f"{indent}</sequence>")
    return newline.join(lines)


def seq_values(seq: dict) -> dict[str, object]:
    return {
        "cellname": str(seq.get("name", "")),
        "notesteplen": _check(seq["steplen"], 0, len(STEP_LENGTHS) - 1, "step length"),
        "notestepcount": _check(seq["stepcount"], 0, MAX_STEPS, "step count"),
        "quantsizeseq": _check(seq["quant"], 0, len(QUANT_SIZES) - 1, "quant size"),
        "seqstepmode": 1 if seq.get("snap", True) else 0,
    }


def write_sequence(body: str, seq: dict, newline: str) -> str:
    """Replace or add the noteseq cell for seq["slot"] in a track body."""
    slot = _check(seq["slot"], 0, 7, "sequence slot")
    values = seq_values(seq)
    existing = [m for m in NOTESEQ_RE.finditer(body)]
    for m in existing:
        p = PARAMS_RE.search(m.group())
        if p and _int(parse_attrs(p.group()), "celldisppos") == slot:
            cell = m.group()
            indent = m.group("indent")
            cell = cell[: p.start()] + set_attrs(p.group(), values) + cell[p.end():]
            seq_match = SEQUENCE_RE.search(cell)
            new_seq = sequence_xml(seq["events"], indent + "    ", newline)
            if seq_match:
                cell = cell[: seq_match.start()] + new_seq + cell[seq_match.end():]
            else:
                p2 = PARAMS_RE.search(cell)
                cell = cell[: p2.end()] + newline + indent + "    " + new_seq + cell[p2.end():]
            return body[: m.start()] + cell + body[m.end():]
    # New cell after the last noteseq cell, or after the track params
    if existing:
        indent = existing[-1].group("indent")
        insert_at = existing[-1].end()
    else:
        p = PARAMS_RE.search(body)
        if p is None:
            raise SequenceError("track without params")
        line_start = body.rfind("\n", 0, p.start()) + 1
        indent = body[line_start:p.start()]
        insert_at = p.end()
    attrs = {"cellname": values["cellname"] or f"Seq {slot + 1}", **SEQ_DEFAULTS, "celldisppos": slot}
    attrs.update({k: v for k, v in values.items() if k != "cellname"})
    order = ["cellname", "notesteplen", "notestepcount", "notestepcountset", "seqstepmode", "celldisppos",
             "quantsizeseq", "uiseqknobmode", "seqslide"]
    params = "<params " + " ".join(f'{k}="{attrs[k]}"' for k in order) + "/>"
    cell = newline.join(
        [
            f'{indent}<cell type="noteseq">',
            f"{indent}    {params}",
            f"{indent}    {sequence_xml(seq['events'], indent + '    ', newline)}",
            f"{indent}</cell>",
        ]
    )
    return body[:insert_at] + newline + cell + body[insert_at:]


@dataclass
class TrackChange:
    index: int
    midiinchan: int | None = None
    midioutchan: int | None = None
    sequences: list[dict] = field(default_factory=list)
    # celldisppos to (saminst values, samasst values), as patchedit.edit_oneshot takes them
    pad_updates: dict[int, tuple[dict, dict]] = field(default_factory=dict)


def apply_changes(text: str, changes: list[TrackChange]) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    by_index = {t.index: t for t in tracks(text)}
    # From the last track to the first, so earlier offsets stay valid
    for change in sorted(changes, key=lambda c: c.index, reverse=True):
        track = by_index.get(change.index)
        if track is None or track.type == "mastrack":
            raise SequenceError(f"no instrument track {change.index}")
        body = text[track.start:track.end]
        for seq in change.sequences:
            body = write_sequence(body, seq, newline)
        if change.pad_updates:
            if track.type != "samtrack":
                raise SequenceError(f"track {change.index} is not a one-shot track")
            body, errors = edit_oneshot(body, change.pad_updates)
            if errors:
                raise SequenceError("; ".join(errors))
            if newline == "\r\n":
                # New pad cells are built with \n; the file uses \r\n
                body = re.sub(r"(?<!\r)\n", "\r\n", body)
        values: dict[str, object] = {}
        if change.midiinchan is not None:
            values["midiinchan"] = _check(change.midiinchan, 0, 16, "MIDI in channel")
        if change.midioutchan is not None:
            values["midioutchan"] = _check(change.midioutchan, 0, 16, "MIDI out channel")
        if values:
            p = PARAMS_RE.search(body)
            if p is None:
                raise SequenceError("track without params")
            body = body[: p.start()] + set_attrs(p.group(), values) + body[p.end():]
        text = text[: track.start] + body + text[track.end:]
    return text
