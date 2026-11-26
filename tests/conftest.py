"""Synthetic card fixtures, no factory content involved."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest


def make_wav(
    path: Path,
    frames: int = 4410,
    channels: int = 1,
    rate: int = 44100,
    bits: int = 16,
    junk: bool = False,
    cues: list[int] | None = None,
) -> Path:
    t = np.arange(frames) / rate
    signal = 0.5 * np.sin(2 * np.pi * 220 * t)
    data = np.repeat(signal[:, None], channels, axis=1).reshape(-1)

    if bits == 16:
        payload = (data * 32767).astype("<i2").tobytes()
    elif bits == 24:
        ints = (data * 8388607).astype(np.int32)
        raw = np.empty((len(ints), 3), dtype=np.uint8)
        raw[:, 0] = ints & 0xFF
        raw[:, 1] = (ints >> 8) & 0xFF
        raw[:, 2] = (ints >> 16) & 0xFF
        payload = raw.tobytes()
    else:
        raise ValueError(bits)

    block = channels * bits // 8
    chunks = b""
    if junk:
        chunks += b"JUNK" + struct.pack("<I", 28) + b"\x00" * 28
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * block, block, bits)
    chunks += b"fmt " + struct.pack("<I", len(fmt)) + fmt
    if cues:
        body = struct.pack("<I", len(cues))
        for i, pos in enumerate(cues):
            body += struct.pack("<II4sIII", i + 1, pos, b"data", 0, 0, pos)
        chunks += b"cue " + struct.pack("<I", len(body)) + body
    chunks += b"data" + struct.pack("<I", len(payload)) + payload
    if len(payload) & 1:
        chunks += b"\x00"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks)
    return path


@pytest.fixture
def card(tmp_path: Path) -> Path:
    root = tmp_path / "card"
    (root / "Patches" / "OneShots" / "Kit A").mkdir(parents=True)
    make_wav(root / "Patches" / "OneShots" / "Kit A" / "Kick.wav")
    (root / "Patches" / "OneShots" / "Kit A" / "patch.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<document>\n    <session version="1">\n'
        '        <track type="samtrack">\n            <params cellname="Kit A"/>\n'
        '            <cell type="saminst">\n                <params celldisppos="8"/>\n            </cell>\n'
        '            <cell type="samasst">\n                <params filename="Kick.wav" samlen="4410"/>\n'
        "                <slices/>\n            </cell>\n        </track>\n    </session>\n</document>\n",
        encoding="utf-8",
    )
    (root / "Patches" / "patchindex.xml").write_text(
        '﻿<?xml version="1.0" encoding="UTF-8"?>\n<patchmetadata version="1">\n    \n'
        '    <patch path="Patches\\OneShots\\Kit A">\n        <tag>Drum</tag>\n    </patch>\n'
        "</patchmetadata>\n",
        encoding="utf-8",
    )
    for sub in ("OneShots", "SampInst"):
        (root / "UserPatches" / sub).mkdir(parents=True)

    samples = root / "Samples" / "Pack"
    make_wav(samples / "BD.wav", frames=2000)
    make_wav(samples / "SD.wav", frames=3000, channels=2, bits=24, junk=True)
    for note in (48, 60, 72):
        make_wav(root / "Samples" / "Piano" / f"Piano-{note:03d}-100.wav", frames=8000, channels=2, rate=48000, bits=24)

    project = root / "Projects" / "Song"
    project.mkdir(parents=True)
    make_wav(project / "RC000001.wav")
    make_wav(project / "RC000002.wav")
    (project / "project.xml").write_text(
        '﻿<?xml version="1.0" encoding="UTF-8"?>\n<document><session version="2"><track type="samtrack">'
        '<cell type="samasst"><params filename=".\\RC000001.wav"/></cell>'
        '<cell type="samasst"><params filename="Samples\\Pack\\BD.wav"/></cell>'
        '<cell type="samasst"><params filename="\\Samples\\Pack\\Missing.wav"/></cell>'
        "</track></session></document>\n",
        encoding="utf-8",
    )
    return root
