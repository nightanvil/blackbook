from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from blackbook import builder, patchedit, settings
from blackbook.backup import Backup
from blackbook.card import Card
from blackbook.mapping import automap
from blackbook.patchindex import PatchIndex
from blackbook.server import create_app


def build_kit(card: Path, tmp_path: Path) -> Path:
    c = Card(card)
    pack = card / "Samples" / "Pack"
    spec = builder.OneShotSpec(
        name="Kit",
        tags=["Drum"],
        pads={0: builder.Pad(pack / "BD.wav"), 1: builder.Pad(pack / "SD.wav"), 2: builder.Pad(pack / "BD.wav")},
    )
    builder.apply(c, builder.plan_oneshot(c, spec), Backup(tmp_path / "b", c.root))
    return card / "UserPatches" / "OneShots" / "Kit"


def add_device_content(patch_dir: Path) -> None:
    """Simulate content written by the device that the builder does not know."""
    xml = patch_dir / "patch.xml"
    text = xml.read_bytes().decode("utf-8-sig")
    text = text.replace(
        'celldisppos="0"/>', 'celldisppos="0" duckattack="7"/>\n                <modsource src="1"/>', 1
    )
    text = text.replace(
        "<sequence/>", '<sequence>\n                    <seqevent pos="0" note="36"/>\n                </sequence>'
    )
    xml.write_bytes(("﻿" + text).encode())


def pad_params(patch_dir: Path) -> dict[int, tuple[dict, dict]]:
    text = (patch_dir / "patch.xml").read_bytes().decode("utf-8-sig")
    all_cells = patchedit.cells(text)
    return {
        int(c.attrs["celldisppos"]): (c.attrs, all_cells[i + 1].attrs)
        for i, c in enumerate(all_cells)
        if c.type == "saminst" and "celldisppos" in c.attrs
    }


def test_edit_oneshot_in_place_preserves_unknown_content(card: Path, tmp_path: Path) -> None:
    kit = build_kit(card, tmp_path)
    add_device_content(kit)
    c = Card(card)
    before = pad_params(kit)
    # Simulate a trim made on the device for pad 1
    text = (kit / "patch.xml").read_bytes().decode("utf-8-sig")
    text = text.replace(
        'filename="SD.wav" rootnote="0" keyrangebottom="0" keyrangetop="0" velroot="0" velrangebottom="0" velrangetop="0" samstart="0"',
        'filename="SD.wav" rootnote="0" keyrangebottom="0" keyrangetop="0" velroot="0" velrangebottom="0" velrangetop="0" samstart="100"',
    )
    (kit / "patch.xml").write_bytes(("﻿" + text).encode())

    spec = builder.OneShotSpec(
        name="ignored in edit mode",
        tags=["Drum", "SFX"],
        pads={
            0: builder.Pad(kit / "BD.wav", gain=-6),
            1: builder.Pad(kit / "SD.wav", pitch=2),
            3: builder.Pad(card / "Samples" / "Pack" / "SD.wav"),
        },
    )
    plan = builder.plan_oneshot(c, spec, builder.Base.load(kit, "edit"))
    assert plan.ok, plan.errors
    assert plan.target_dir == kit
    assert [f.target_name for f in plan.copies] == ["SD_2.wav"]

    builder.apply(c, plan, Backup(tmp_path / "b2", c.root))
    text = (kit / "patch.xml").read_bytes().decode("utf-8-sig")
    assert 'duckattack="7"' in text
    assert '<modsource src="1"/>' in text
    assert '<seqevent pos="0" note="36"/>' in text
    assert (kit / "patch.xml").read_bytes().startswith(b"\xef\xbb\xbf")

    after = pad_params(kit)
    assert after[0][0]["gaindb"] == "-6000"
    assert after[1][0]["pitch"] == "2000"
    assert after[1][1]["samstart"] == "100"  # unchanged sample keeps its trim
    assert after[2][1]["filename"] == ""  # pad 3 was removed
    assert after[3][1]["filename"] == "SD_2.wav"
    assert int(after[3][1]["samlen"]) == 3000
    assert before[2][1]["filename"] == "BD.wav"
    # Files are never deleted by an edit
    assert (kit / "BD.wav").is_file() and (kit / "SD.wav").is_file() and (kit / "SD_2.wav").is_file()
    assert PatchIndex(card / "UserPatches" / "patchindex.xml").tags_for("UserPatches\\OneShots\\Kit") == ["Drum", "SFX"]


def test_edit_without_sample_changes_keeps_preview(card: Path, tmp_path: Path) -> None:
    kit = build_kit(card, tmp_path)
    preview = (kit / "preview.wav").read_bytes()
    c = Card(card)
    spec = builder.OneShotSpec(
        name="Kit",
        tags=["Drum"],
        pads={0: builder.Pad(kit / "BD.wav", gain=3), 1: builder.Pad(kit / "SD.wav"), 2: builder.Pad(kit / "BD.wav")},
    )
    plan = builder.plan_oneshot(c, spec, builder.Base.load(kit, "edit"))
    assert plan.preview is None
    builder.apply(c, plan, Backup(tmp_path / "b2", c.root))
    assert (kit / "preview.wav").read_bytes() == preview


def test_factory_patch_as_template(card: Path, tmp_path: Path) -> None:
    c = Card(card)
    factory = card / "Patches" / "OneShots" / "Kit A"
    spec = builder.OneShotSpec(name="My Kit A", tags=["Drum"], pads={8: builder.Pad(factory / "Kick.wav", gain=1.5)})

    rejected = builder.plan_oneshot(c, spec, builder.Base.load(factory, "edit"))
    assert any("only user patches" in e for e in rejected.errors)

    plan = builder.plan_oneshot(c, spec, builder.Base.load(factory, "copy"))
    assert plan.ok, plan.errors
    builder.apply(c, plan, Backup(tmp_path / "b", c.root))

    target = card / "UserPatches" / "OneShots" / "My Kit A"
    assert (target / "Kick.wav").is_file()
    text = (target / "patch.xml").read_text(encoding="utf-8")
    assert 'cellname="My Kit A"' in text
    assert 'gaindb="1500"' in text
    # The factory patch stays untouched
    assert "gaindb" not in (factory / "patch.xml").read_text(encoding="utf-8")


def test_edit_multisample_zones(card: Path, tmp_path: Path) -> None:
    c = Card(card)
    piano = card / "Samples" / "Piano"
    files = sorted(piano.glob("*.wav"))
    zones = automap([(str(f), f.stem) for f in files])
    spec = builder.MultisampleSpec("Piano", [], [builder.MultisampleZone(Path(z.source), z) for z in zones])
    builder.apply(c, builder.plan_multisample(c, spec), Backup(tmp_path / "b", c.root))
    patch = card / "UserPatches" / "SampInst" / "Piano"
    add_device_content(patch)

    edited = automap(
        [(str(patch / f.name), f.stem) for f in files[:2]] + [(str(card / "Samples/Pack/BD.wav"), "BD_84")]
    )
    spec = builder.MultisampleSpec("Piano", ["Keys"], [builder.MultisampleZone(Path(z.source), z) for z in edited])
    plan = builder.plan_multisample(c, spec, builder.Base.load(patch, "edit"))
    assert plan.ok, plan.errors
    builder.apply(c, plan, Backup(tmp_path / "b2", c.root))

    text = (patch / "patch.xml").read_bytes().decode("utf-8-sig")
    assts = [cell.attrs for cell in patchedit.cells(text) if cell.type == "samasst"]
    assert [(a["filename"], a["rootnote"], a["keyrangebottom"], a["keyrangetop"]) for a in assts] == [
        ("Piano-048-100.wav", "48", "0", "54"),
        ("Piano-060-100.wav", "60", "55", "72"),
        ("BD.wav", "84", "73", "127"),
    ]
    assert '<seqevent pos="0" note="36"/>' in text
    assert (patch / "Piano-072-100.wav").is_file()


def test_api_load_and_edit(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    build_kit(card, tmp_path)
    app = create_app(card, [], tmp_path / "copies")
    with TestClient(app) as client:
        data = client.get("/api/patch/load", params={"ref": "UserPatches\\OneShots\\Kit"}).json()
        assert data["type"] == "oneshot" and data["is_user"] and data["tags"] == ["Drum"]
        assert [(p["slot"], p["source"]) for p in data["pads"]] == [
            (0, "card:UserPatches/OneShots/Kit/BD.wav"),
            (1, "card:UserPatches/OneShots/Kit/SD.wav"),
            (2, "card:UserPatches/OneShots/Kit/BD.wav"),
        ]
        pads = [{**p, "gain": -1.5} if p["slot"] == 0 else p for p in data["pads"]]
        body = {
            "type": "oneshot",
            "name": "Kit",
            "tags": ["Drum"],
            "pads": pads,
            "base_ref": data["ref"],
            "mode": "edit",
        }
        plan = client.post("/api/build/plan", json=body).json()
        assert plan["ok"] and plan["files"] == []
        assert client.post("/api/build/apply", json=body).status_code == 200
        again = client.get("/api/patch/load", params={"ref": "UserPatches\\OneShots\\Kit"}).json()
        assert again["pads"][0]["gain"] == -1.5
