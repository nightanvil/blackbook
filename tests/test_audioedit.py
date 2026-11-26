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
