from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from blackbook import builder
from blackbook.backup import Backup
from blackbook.card import Card, browse
from blackbook.cardpath import resolve_sample_reference, validate_name
from blackbook.mapping import automap, note_name, parse_note_name
from blackbook.patchindex import PatchIndex
from blackbook.wav import read_audio, read_info

from .conftest import make_wav


def parse(path: Path) -> ET.Element:
    return ET.fromstring(path.read_bytes().decode("utf-8-sig").encode())


# ---------- wav ----------


def test_read_info_skips_junk_and_reads_cues(tmp_path: Path) -> None:
    path = make_wav(tmp_path / "a.wav", frames=1000, channels=2, bits=24, junk=True, cues=[100, 500])
    info = read_info(path)
    assert (info.channels, info.bits, info.sample_rate, info.frames) == (2, 24, 44100, 1000)
    assert info.cues == [100, 500]


def test_read_audio_24bit(tmp_path: Path) -> None:
    path = make_wav(tmp_path / "a.wav", frames=441, channels=2, bits=24)
    data, rate = read_audio(path)
    assert data.shape == (441, 2) and rate == 44100
    assert 0.45 < float(abs(data).max()) < 0.55


# ---------- paths ----------


def test_resolve_reference_forms(card: Path) -> None:
    project = card / "Projects" / "Song"
    assert resolve_sample_reference(card, ".\\RC000001.wav", project) == project / "RC000001.wav"
    assert resolve_sample_reference(card, "Samples\\Pack\\BD.wav", project) == card / "Samples/Pack/BD.wav"
    assert resolve_sample_reference(card, "\\samples\\pack\\bd.wav", project) == card / "Samples/Pack/BD.wav"
    assert resolve_sample_reference(card, "Kick.wav", card / "Patches/OneShots/Kit A").name == "Kick.wav"


def test_validate_name() -> None:
    assert validate_name("Kick Kit")[0] == []
    assert validate_name("bad/name")[0]
    assert validate_name("trailing.")[0]
    assert validate_name("")[0]


# ---------- patchindex ----------


def test_patchindex_preserves_bom_and_formatting(card: Path) -> None:
    path = card / "Patches" / "patchindex.xml"
    original = path.read_bytes()
    index = PatchIndex(path)
    assert index.has_bom
    assert index.tags_for("Patches\\OneShots\\Kit A") == ["Drum"]
    assert index.render() == original


def test_patchindex_set_and_remove_tags(card: Path) -> None:
    path = card / "Patches" / "patchindex.xml"
    index = PatchIndex(path)
    index.set_tags("Patches\\OneShots\\Kit A", ["Drum", "Percussion"])
    index.set_tags("Patches\\OneShots\\New & Co", ["SFX"])
    index.save()

    reread = PatchIndex(path)
    assert reread.tags_for("Patches\\OneShots\\Kit A") == ["Drum", "Percussion"]
    assert reread.tags_for("Patches\\OneShots\\New & Co") == ["SFX"]
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    reread.set_tags("Patches\\OneShots\\Kit A", [])
    assert reread.tags_for("Patches\\OneShots\\Kit A") == []
    assert "Kit A" not in reread.text


def test_patchindex_created_without_bom(tmp_path: Path) -> None:
    index = PatchIndex(tmp_path / "patchindex.xml")
    index.set_tags("UserPatches\\OneShots\\X", ["Drum"])
    index.save()
    assert (tmp_path / "patchindex.xml").read_bytes().startswith(b"<?xml")
    assert PatchIndex(tmp_path / "patchindex.xml").tags_for("UserPatches\\OneShots\\X") == ["Drum"]


# ---------- mapping ----------


def test_note_names() -> None:
    assert note_name(36) == "C2"
    assert parse_note_name("C2") == 36
    assert parse_note_name("F#3") == 54


def test_automap_patterns() -> None:
    zones = automap(
        [
            ("a", "Chords_Junos_48_0_127"),
            ("b", "Pad_60"),
            ("c", "Lead_C5"),
            ("d", "nothing"),
        ]
    )
    by_source = {z.source: z for z in zones}
    assert by_source["a"].root == 48 and (by_source["a"].vel_low, by_source["a"].vel_high) == (0, 127)
    assert by_source["b"].root == 60
    assert by_source["c"].root == 72
    assert by_source["d"].warnings


def test_automap_wizard_velocity_layers() -> None:
    zones = automap([("s", "Piano-060-040"), ("l", "Piano-060-100"), ("m", "Piano-060-127")])
    layers = sorted((z.vel_low, z.vel_high) for z in zones)
    assert layers == [(0, 70), (71, 113), (114, 127)]
    assert all((z.key_low, z.key_high) == (0, 127) for z in zones)


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("split", [(0, 54), (55, 66), (67, 127)]),
        ("up", [(0, 59), (60, 71), (72, 127)]),
        ("down", [(0, 48), (49, 60), (61, 127)]),
    ],
)
def test_gap_rules(rule: str, expected: list[tuple[int, int]]) -> None:
    zones = automap([("a", "x_48"), ("b", "x_60"), ("c", "x_72")], gap_rule=rule)
    assert sorted((z.key_low, z.key_high) for z in zones) == expected


# ---------- card ----------


def test_card_patches_and_projects(card: Path) -> None:
    c = Card(card)
    patches = c.patches()
    assert [(p.ref, p.tags) for p in patches] == [("Patches\\OneShots\\Kit A", ["Drum"])]

    track_type, samples = c.patch_samples("Patches\\OneShots\\Kit A")
    assert track_type == "samtrack"
    assert samples[0].slot == 8 and samples[0].resolved == "Patches/OneShots/Kit A/Kick.wav"

    (project,) = c.projects()
    assert project.references == 3
    assert project.missing == ["\\Samples\\Pack\\Missing.wav"]
    assert project.unused == ["RC000002.wav"]


def test_browse_lists_dirs_then_wavs(card: Path) -> None:
    entries = browse(card, "Samples/Pack")
    assert [e.name for e in entries] == ["BD.wav", "SD.wav"]
    assert entries[1].info.startswith("PCM 24 bit")
    with pytest.raises(PermissionError):
        browse(card, "../..")


# ---------- builder ----------


def test_build_oneshot(card: Path, tmp_path: Path) -> None:
    c = Card(card)
    pack = card / "Samples" / "Pack"
    spec = builder.OneShotSpec(
        name="My Kit",
        tags=["Drum"],
        pads={
            0: builder.Pad(pack / "BD.wav", gain=-3.5),
            1: builder.Pad(pack / "SD.wav", pitch=2),
            2: builder.Pad(pack / "BD.wav"),
        },
    )
    plan = builder.plan_oneshot(c, spec)
    assert plan.ok, plan.errors
    assert [f.target_name for f in plan.copies] == ["BD.wav", "SD.wav"]

    backup = Backup(tmp_path / "backups", c.root)
    written = builder.apply(c, plan, backup)
    target = card / "UserPatches" / "OneShots" / "My Kit"
    assert sorted(p.name for p in target.iterdir()) == ["BD.wav", "SD.wav", "patch.xml", "preview.wav"]
    assert "UserPatches/patchindex.xml" in written

    raw = (target / "patch.xml").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf<?xml")
    track = parse(target / "patch.xml").find("./session/track")
    cells = track.findall("cell")
    assert len(cells) == 33  # 16 pads x 2 cells + noteseq
    pads = {
        int(cells[i].find("params").get("celldisppos")): (cells[i].find("params"), cells[i + 1].find("params"))
        for i in range(0, 32, 2)
    }
    assert pads[0][0].get("gaindb") == "-3500"
    assert pads[0][1].get("filename") == "BD.wav" and pads[0][1].get("samlen") == "2000"
    assert pads[1][0].get("pitch") == "2000"
    assert pads[5][1].get("filename") == ""

    preview = read_info(target / "preview.wav")
    assert (preview.bits, preview.sample_rate, preview.channels) == (24, 48000, 2)

    assert PatchIndex(card / "UserPatches" / "patchindex.xml").tags_for("UserPatches\\OneShots\\My Kit") == ["Drum"]
    assert (backup.dir / "journal.json").exists()

    # A second build with the same name is rejected
    assert not builder.plan_oneshot(c, spec).ok


def test_build_multisample(card: Path, tmp_path: Path) -> None:
    c = Card(card)
    piano = card / "Samples" / "Piano"
    files = sorted(piano.glob("*.wav"))
    zones = automap([(str(f), f.stem) for f in files])
    spec = builder.MultisampleSpec(
        name="Piano",
        tags=[],
        zones=[builder.MultisampleZone(Path(z.source), z) for z in zones],
    )
    plan = builder.plan_multisample(c, spec)
    assert plan.ok, plan.errors
    builder.apply(c, plan, Backup(tmp_path / "b", c.root))

    target = card / "UserPatches" / "SampInst" / "Piano"
    track = parse(target / "patch.xml").find("./session/track")
    assert track.get("type") == "multisamtrack"
    assts = [cell.find("params") for cell in track.findall("cell") if cell.get("type") == "samasst"]
    assert [(a.get("rootnote"), a.get("keyrangebottom"), a.get("keyrangetop")) for a in assts] == [
        ("48", "0", "54"),
        ("60", "55", "66"),
        ("72", "67", "127"),
    ]
    assert {a.get("velrangetop") for a in assts} == {"128"}
    # No tags: no index entry and no index file
    assert not (card / "UserPatches" / "patchindex.xml").exists()


def test_build_rejects_invalid_input(card: Path) -> None:
    c = Card(card)
    plan = builder.plan_oneshot(c, builder.OneShotSpec(name="bad:name", tags=[], pads={}))
    assert not plan.ok
    assert any("invalid characters" in e for e in plan.errors)
    assert any("no pad" in e for e in plan.errors)


def test_card_detection(tmp_path, monkeypatch) -> None:
    from blackbook import carddetect

    card = tmp_path / "BB2"
    (card / "UserPatches").mkdir(parents=True)
    (card / "bb2-stng.mml").write_text("settings")
    (tmp_path / "USBSTICK").mkdir()
    monkeypatch.setattr(carddetect, "mount_points", lambda: [tmp_path / "USBSTICK", card])
    assert carddetect.find_cards() == [card]
    assert not carddetect.is_card(tmp_path / "missing")


def test_ui_files_are_revalidated(card, tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from blackbook import settings
    from blackbook.server import create_app

    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    app = create_app(card, [], tmp_path / "copies", inbox_dir=tmp_path / "inbox")
    with TestClient(app) as client:
        assert client.get("/static/sequencer.js").headers["cache-control"] == "no-cache"
        assert client.get("/").headers["cache-control"] == "no-cache"
