from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from blackbook import projectseq, settings
from blackbook.server import create_app

from .conftest import make_wav

PROJECT = (
    "﻿<document>\r\n"
    '    <session version="2">\r\n'
    '        <track type="samtrack">\r\n'
    '            <params cellname="Drums" midiinchan="1" midioutchan="0" other="x"/>\r\n'
    '            <cell type="noteseq">\r\n'
    '                <params cellname="Seq 1" notesteplen="10" notestepcount="16" notestepcountset="1" seqstepmode="1" celldisppos="0" quantsizeseq="1" uiseqknobmode="2" seqslide="0"/>\r\n'
    "                <sequence>\r\n"
    '                    <seqevent step="1" chan="9" type="note" strtks="960" pitch="0" lencount="1" lentks="960" velocity="100"/>\r\n'
    '                    <seqevent step="0" type="note" strtks="0" pitch="0" lencount="1" lentks="960" velocity="100"/>\r\n'
    '                    <seqevent step="2" chan="8" type="note" strtks="1910" pitch="0" lencount="1" lentks="960" velocity="64" cond="50"/>\r\n'
    "                </sequence>\r\n"
    "            </cell>\r\n"
    '            <cell type="noteseq">\r\n'
    '                <params cellname="Seq 6" notesteplen="10" notestepcount="0" notestepcountset="1" seqstepmode="0" celldisppos="5" quantsizeseq="0" uiseqknobmode="2" seqslide="0"/>\r\n'
    "                <sequence>\r\n"
    '                    <seqevent step="0" chan="8" type="note" strtks="0" pitch="0" lencount="0" lentks="240"/>\r\n'
    "                </sequence>\r\n"
    "            </cell>\r\n"
    '            <cell type="saminst">\r\n'
    '                <params gaindb="0" celldisppos="8"/>\r\n'
    "            </cell>\r\n"
    '            <cell type="samasst">\r\n'
    '                <params filename="Samples\\Pack\\BD.wav" samstart="0" samlen="2000"/>\r\n'
    "            </cell>\r\n"
    "        </track>\r\n"
    '        <track type="mastrack">\r\n'
    '            <params globtempo="123" swing="55"/>\r\n'
    "        </track>\r\n"
    "    </session>\r\n"
    "</document>\r\n"
)


def test_read_project() -> None:
    data = projectseq.read_project(PROJECT.lstrip("﻿"))
    assert data["tempo"] == 123 and data["swing"] == 55
    track = data["tracks"][0]
    assert track["midiinchan"] == 1 and [s["slot"] for s in track["sequences"]] == [0, 5]
    events = track["sequences"][0]["events"]
    assert [(e["step"], e["chan"], e["offset"], e["prob"]) for e in events] == [(1, 9, 0, 100), (0, 0, 0, 100), (2, 8, -1, 50)]
    assert track["sequences"][1]["stepcount"] == 0 and not track["sequences"][1]["snap"]
    assert track["pads"][0]["slot"] == 8 and track["pads"][0]["length"] == 2000


def test_unchanged_write_is_byte_identical() -> None:
    text = PROJECT.lstrip("﻿")
    track = projectseq.read_project(text)["tracks"][0]
    change = projectseq.TrackChange(track["index"], track["midiinchan"], track["midioutchan"], track["sequences"])
    assert projectseq.apply_changes(text, [change]) == text


def test_edit_and_new_sequence() -> None:
    text = PROJECT.lstrip("﻿")
    seq = {"slot": 2, "name": "", "steplen": 8, "stepcount": 7, "quant": 4, "snap": True,
           "events": [{"step": 3, "chan": 15, "strtks": 3350, "velocity": 90, "prob": 100, "lencount": 2, "lentks": 1920}]}
    new = projectseq.apply_changes(text, [projectseq.TrackChange(0, midiinchan=5, midioutchan=16, sequences=[seq])])
    assert 'midiinchan="5" midioutchan="16" other="x"' in new
    assert 'cellname="Seq 3" notesteplen="8" notestepcount="7"' in new
    assert '<seqevent step="3" chan="15" type="note" strtks="3350" pitch="0" lencount="2" lentks="1920" velocity="90"/>' in new
    assert "\n" not in new.replace("\r\n", "")
    again = projectseq.read_project(new)["tracks"][0]["sequences"]
    assert [s["slot"] for s in again] == [0, 2, 5]
    with pytest.raises(projectseq.SequenceError):
        projectseq.apply_changes(text, [projectseq.TrackChange(0, sequences=[{**seq, "steplen": 16}])])


def test_project_api(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    project = card / "Projects" / "Beat"
    project.mkdir()
    make_wav(project / "x.wav")
    (project / "project.xml").write_text(PROJECT, encoding="utf-8", newline="")
    app = create_app(card, [], tmp_path / "copies", inbox_dir=tmp_path / "inbox")
    with TestClient(app) as client:
        data = client.get("/api/project/detail", params={"name": "Beat"}).json()
        assert data["tracks"][0]["pads"][0]["source"] == "card:Samples/Pack/BD.wav"
        seq = data["tracks"][0]["sequences"][0]
        seq["events"] = seq["events"][:1]
        result = client.put("/api/project/sequences", json={"name": "Beat", "tracks": [{"index": 0, "sequences": [seq]}]})
        assert result.json() == {"changed": True}
        assert client.get("/api/project/detail", params={"name": "../Beat"}).status_code in (403, 404)
    raw = (project / "project.xml").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and raw.count(b"<seqevent") == 2
