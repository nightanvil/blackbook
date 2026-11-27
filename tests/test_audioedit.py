from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from blackbook import audioedit, settings
from blackbook.server import create_app
from blackbook.wav import read_audio, read_info

from .conftest import make_wav


@pytest.mark.parametrize("bits,channels", [(16, 1), (24, 2)])
def test_untouched_samples_stay_bit_identical(tmp_path: Path, bits: int, channels: int) -> None:
    src = make_wav(tmp_path / "in.wav", frames=1000, channels=channels, bits=bits)
    data, rate = read_audio(src)
    out = tmp_path / "out.wav"
    audioedit.write_wav(out, data, rate, bits, False)
    info_in, info_out = read_info(src), read_info(out)
    raw_in = src.read_bytes()[info_in.data_offset:info_in.data_offset + info_in.data_size]
    raw_out = out.read_bytes()[info_out.data_offset:info_out.data_offset + info_out.data_size]
    assert raw_in == raw_out


def test_operations() -> None:
    data = np.linspace(-1, 1, 100, dtype=np.float32).reshape(-1, 1)
    assert len(audioedit.apply_op(data, "crop", 10, 30)) == 20
    assert len(audioedit.apply_op(data, "delete", 10, 30)) == 80
    assert not audioedit.apply_op(data, "silence", 0, 50)[:50].any()
    faded = audioedit.apply_op(np.ones((100, 1), np.float32), "fade_in", 0, 100)
    assert faded[0, 0] == 0 and faded[-1, 0] == pytest.approx(1)
    normalized = audioedit.apply_op(data * 0.25, "normalize", 0, 100, 0.0)
    assert np.max(np.abs(normalized)) == pytest.approx(1)
    assert audioedit.apply_op(data, "reverse", 0, 100)[0, 0] == pytest.approx(1)
    louder = audioedit.apply_op(data * 0.1, "gain", 0, 100, 6.0)
    assert np.max(np.abs(louder)) == pytest.approx(0.1 * 10 ** 0.3, rel=1e-4)
    with pytest.raises(audioedit.EditError):
        audioedit.apply_op(data, "delete", 0, 100)
    with pytest.raises(audioedit.EditError):
        audioedit.apply_op(data, "crop", 50, 200)


def test_nearest_zero_crossing() -> None:
    t = np.arange(1000)
    data = np.sin(2 * np.pi * t / 100).astype(np.float32).reshape(-1, 1)
    # Zero crossings of this sine are every 50 frames
    assert audioedit.nearest_zero_crossing(data, 140) in (150, 151)
    assert audioedit.nearest_zero_crossing(data, 230) in (250, 251, 200, 201)


def test_edit_api_flow(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    app = create_app(card, [], tmp_path / "copies", inbox_dir=tmp_path / "inbox")
    with TestClient(app) as client:
        state = client.post("/api/audio-edit/open", json={"source": "card:Samples/Pack/BD.wav"}).json()
        frames = state["frames"]
        pcm = client.get(f"/api/audio-edit/{state['id']}/pcm").content
        assert len(pcm) == frames * state["channels"] * 4
        sid = state["id"]
        state = client.post(f"/api/audio-edit/{sid}/op", json={"op": "crop", "start": 0, "end": 1000}).json()
        assert state["frames"] == 1000 and state["can_undo"]
        state = client.post(f"/api/audio-edit/{sid}/undo").json()
        assert state["frames"] == frames and state["can_redo"]
        state = client.post(f"/api/audio-edit/{sid}/redo").json()
        assert state["frames"] == 1000
        assert client.post(f"/api/audio-edit/{sid}/op", json={"op": "nope", "start": 0, "end": 10}).status_code == 400
        saved = client.post(f"/api/audio-edit/{sid}/save").json()
        assert saved["source"] == "inbox:edits/BD_edit.wav"
        assert read_info(tmp_path / "inbox" / "edits" / "BD_edit.wav").frames == 1000
        # The original on the card is untouched
        assert read_info(card / "Samples" / "Pack" / "BD.wav").frames == frames
        assert client.get(f"/api/audio-edit/{sid}/pcm").status_code == 404


def test_map_position() -> None:
    ops = [("delete", 100, 200), ("crop", 50, 500)]
    assert audioedit.map_position(ops, 0) == 0
    assert audioedit.map_position(ops, 150) == 50
    assert audioedit.map_position(ops, 300) == 150
    assert audioedit.map_position(ops, 5000) == 450


def test_adjust_text_changes_only_positions() -> None:
    from blackbook import sampleupdate

    text = (
        '<document>\r\n<cell type="samasst">\r\n    <params filename="Kick.wav" samstart="0" samlen="1000" '
        'loopstart="0" loopend="1000" extra="x"/>\r\n    <slices>\r\n        <slice pos="600"/>\r\n    </slices>\r\n'
        '</cell>\r\n<cell type="samasst"><params filename="Other.wav" samlen="1000"/></cell>\r\n</document>\r\n'
    )
    ops = [("delete", 100, 300)]
    new, changes = sampleupdate.adjust_text(
        text, "UserPatches/OneShots/K/patch.xml", "UserPatches/OneShots/K/Kick.wav", 800,
        lambda f: audioedit.map_position(ops, f),
    )
    assert 'samlen="800"' in new and 'loopend="800"' in new and 'pos="400"' in new
    assert 'extra="x"' in new and '<params filename="Other.wav" samlen="1000"/>' in new
    assert new.count("\r\n") == text.count("\r\n")
    assert len(changes) == 1 and changes[0].slices == 1


def test_overwrite_adjusts_references(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    user = card / "UserPatches" / "OneShots" / "Mine"
    make_wav(user / "Hit.wav", frames=2000, cues=[1500])
    (user / "Hit.wav.pk").write_bytes(b"cache")
    xml = (
        '﻿<document><session version="1"><track type="samtrack">'
        '<cell type="samasst"><params filename="Hit.wav" samstart="0" samlen="2000" foo="1"/></cell>'
        "</track></session></document>\n"
    )
    (user / "patch.xml").write_text(xml, encoding="utf-8")
    project_xml = card / "Projects" / "Song" / "project.xml"
    project_xml.write_text(
        project_xml.read_text(encoding="utf-8").replace(
            "</track>",
            '<cell type="samasst"><params filename="UserPatches\\OneShots\\Mine\\Hit.wav" samstart="1200" samlen="800"/></cell></track>',
        ),
        encoding="utf-8",
    )
    app = create_app(card, [], tmp_path / "copies", inbox_dir=tmp_path / "inbox")
    with TestClient(app) as client:
        state = client.post("/api/audio-edit/open", json={"source": "card:UserPatches/OneShots/Mine/Hit.wav"}).json()
        client.post(f"/api/audio-edit/{state['id']}/op", json={"op": "delete", "start": 0, "end": 500})
        impact = client.get(f"/api/audio-edit/{state['id']}/impact").json()
        assert impact["can_overwrite"] and impact["frames_after"] == 1500 and impact["cache"]
        assert {r["xml"] for r in impact["references"]} == {"UserPatches/OneShots/Mine/patch.xml", "Projects/Song/project.xml"}
        result = client.post(f"/api/audio-edit/{state['id']}/write", json={"mode": "overwrite"}).json()
        assert len(result["adjusted"]) == 2
    info = read_info(user / "Hit.wav")
    assert info.frames == 1500 and info.cues == [1000]
    assert not (user / "Hit.wav.pk").exists()
    patch = (user / "patch.xml").read_bytes()
    assert patch.startswith(b"\xef\xbb\xbf") and b'samlen="1500"' in patch and b'foo="1"' in patch
    project = project_xml.read_text(encoding="utf-8")
    assert 'samstart="700" samlen="800"' in project


def test_factory_sample_saves_as_new_file(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    app = create_app(card, [], tmp_path / "copies", inbox_dir=tmp_path / "inbox")
    original = (card / "Patches" / "OneShots" / "Kit A" / "Kick.wav").read_bytes()
    with TestClient(app) as client:
        state = client.post("/api/audio-edit/open", json={"source": "card:Patches/OneShots/Kit A/Kick.wav"}).json()
        client.post(f"/api/audio-edit/{state['id']}/op", json={"op": "gain", "start": 0, "end": 100, "value": -6})
        impact = client.get(f"/api/audio-edit/{state['id']}/impact").json()
        assert not impact["can_overwrite"] and impact["new_file"] == "Samples/Edited/Kick_edit.wav"
        assert client.post(f"/api/audio-edit/{state['id']}/write", json={"mode": "overwrite"}).status_code == 403
        result = client.post(f"/api/audio-edit/{state['id']}/write", json={"mode": "new"}).json()
        assert result["source"] == "card:Samples/Edited/Kick_edit.wav"
        samples = client.get("/api/project/samples", params={"name": "Song"}).json()
        assert [s["uses"] for s in samples if s["path"] == "Samples/Pack/BD.wav"] == [1]
    assert (card / "Samples" / "Edited" / "Kick_edit.wav").is_file()
    assert (card / "Patches" / "OneShots" / "Kit A" / "Kick.wav").read_bytes() == original


def test_rename_sample_updates_references(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    user = card / "UserPatches" / "OneShots" / "Mine"
    make_wav(user / "Hit.wav")
    make_wav(user / "Other.wav")
    (user / "Hit.wav.pk").write_bytes(b"cache")
    (user / "patch.xml").write_text(
        '﻿<document><session version="1"><track type="samtrack">'
        '<cell type="samasst"><params filename="Hit.wav" samlen="4410"/></cell></track></session></document>\n',
        encoding="utf-8",
    )
    project_xml = card / "Projects" / "Song" / "project.xml"
    project_xml.write_text(
        project_xml.read_text(encoding="utf-8").replace(
            "</track>", '<cell type="samasst"><params filename="UserPatches\\OneShots\\Mine\\Hit.wav"/></cell></track>'
        ),
        encoding="utf-8",
    )
    app = create_app(card, [], tmp_path / "copies", inbox_dir=tmp_path / "inbox")
    with TestClient(app) as client:
        body = {"source": "card:UserPatches/OneShots/Mine/Hit.wav", "name": "Snap Hard"}
        preview = client.post("/api/sample/rename", json=body).json()
        assert preview["new_path"] == "UserPatches/OneShots/Mine/Snap Hard.wav"
        assert {r["xml"] for r in preview["references"]} == {"UserPatches/OneShots/Mine/patch.xml", "Projects/Song/project.xml"}
        assert (user / "Hit.wav").is_file()
        result = client.post("/api/sample/rename", json={**body, "apply": True}).json()
        assert result["source"] == "card:UserPatches/OneShots/Mine/Snap Hard.wav"
        assert client.post("/api/sample/rename", json={"source": "card:Patches/OneShots/Kit A/Kick.wav", "name": "x"}).status_code == 403
        clash = client.post("/api/sample/rename", json={"source": result["source"], "name": "other"})
        assert clash.status_code == 400
    assert (user / "Snap Hard.wav").is_file() and not (user / "Hit.wav").exists() and not (user / "Hit.wav.pk").exists()
    assert 'filename="Snap Hard.wav"' in (user / "patch.xml").read_text(encoding="utf-8-sig")
    assert 'filename="UserPatches\\OneShots\\Mine\\Snap Hard.wav"' in project_xml.read_text(encoding="utf-8")
    assert (user / "patch.xml").read_bytes().startswith(b"\xef\xbb\xbf")
