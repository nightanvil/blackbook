"""Key and velocity mapping of multisample zones from file names."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_OFFSETS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_name(note: int) -> str:
    """MIDI note name with note 36 = C2, as on the device."""
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


def parse_note_name(text: str) -> int | None:
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", text)
    if not m:
        return None
    note = NOTE_OFFSETS[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    value = (int(m.group(3)) + 1) * 12 + note
    return value if 0 <= value <= 127 else None


@dataclass
class Zone:
    source: str
    root: int
    key_low: int = 0
    key_high: int = 127
    vel_low: int = 0
    vel_high: int = 127
    vel_root: int = 64
    detected: str = ""
    warnings: list[str] = field(default_factory=list)


PATTERNS = [
    # Name_060_000_127.wav or Name_60_0_127.wav: note, velocity low, velocity high
    ("note+range", re.compile(r"[_\- ](\d{1,3})[_\- ](\d{1,3})[_\- ](\d{1,3})$")),
    # Name-060-100.wav: note and recorded velocity (multisample wizard)
    ("note+vel", re.compile(r"[_\- ](\d{1,3})[_\- ](\d{1,3})$")),
    # Name_C3.wav, Name_F#2.wav
    ("notename", re.compile(r"[_\- ]([A-Ga-g][#b]?-?\d)$")),
    # Name_60.wav
    ("note", re.compile(r"[_\- ](\d{1,3})$")),
]


def detect(stem: str) -> tuple[str, int | None, tuple[int, int] | None, int | None]:
    """Return (pattern, note, velocity range, single velocity) for a file stem."""
    for kind, pattern in PATTERNS:
        m = pattern.search(stem)
        if not m:
            continue
        if kind == "note+range":
            note, lo, hi = (int(g) for g in m.groups())
            if note <= 127 and lo <= hi <= 127:
                return kind, note, (lo, hi), None
        elif kind == "note+vel":
            note, vel = (int(g) for g in m.groups())
            if note <= 127 and vel <= 127:
                return kind, note, None, vel
        elif kind == "notename":
            note = parse_note_name(m.group(1))
            if note is not None:
                return kind, note, None, None
        elif kind == "note":
            note = int(m.group(1))
            if note <= 127:
                return kind, note, None, None
    return "", None, None, None


def automap(sources: list[tuple[str, str]], gap_rule: str = "split") -> list[Zone]:
    """Build zones from (source id, file stem) pairs.

    gap_rule decides how unmapped keys between two sampled notes are assigned:
    'split' halves the gap, 'up' extends each sample upwards, 'down' downwards.
    """
    zones: list[Zone] = []
    single_velocities: dict[int, list[Zone]] = {}

    for source, stem in sources:
        kind, note, vel_range, vel = detect(stem)
        if note is None:
            zone = Zone(source=source, root=60, detected="none")
            zone.warnings.append("no note found in file name, mapped to C4 (60)")
            zones.append(zone)
            continue
        zone = Zone(source=source, root=note, detected=kind)
        if vel_range:
            zone.vel_low, zone.vel_high = vel_range
        elif vel is not None:
            single_velocities.setdefault(note, []).append(zone)
            zone.vel_root = vel
        zones.append(zone)

    # Velocity layers recorded with a single velocity value split the range between neighbours
    for layer in single_velocities.values():
        layer.sort(key=lambda z: z.vel_root)
        for i, zone in enumerate(layer):
            lower = 0 if i == 0 else (layer[i - 1].vel_root + zone.vel_root) // 2 + 1
            upper = 127 if i == len(layer) - 1 else (zone.vel_root + layer[i + 1].vel_root) // 2
            zone.vel_low, zone.vel_high = lower, upper

    for zone in zones:
        if zone.detected != "note+vel":
            zone.vel_root = (zone.vel_low + zone.vel_high) // 2

    assign_key_ranges(zones, gap_rule)
    return zones


def assign_key_ranges(zones: list[Zone], gap_rule: str = "split") -> None:
    roots = sorted({z.root for z in zones})
    if not roots:
        return
    bounds: dict[int, tuple[int, int]] = {}
    for i, root in enumerate(roots):
        prev_root = roots[i - 1] if i > 0 else None
        next_root = roots[i + 1] if i + 1 < len(roots) else None

        if prev_root is None:
            low = 0
        elif gap_rule == "up":
            low = root
        elif gap_rule == "down":
            low = prev_root + 1
        else:
            low = (prev_root + root) // 2 + 1

        if next_root is None:
            high = 127
        elif gap_rule == "up":
            high = next_root - 1
        elif gap_rule == "down":
            high = root
        else:
            high = (root + next_root) // 2
        bounds[root] = (low, high)

    for zone in zones:
        zone.key_low, zone.key_high = bounds[zone.root]
