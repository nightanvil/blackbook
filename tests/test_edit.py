from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from blackbook import builder, eject, patchedit, server, settings
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


def test_import_dropped_files(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    (card / "bb2-stng.mml").write_text("settings")
    wav = (card / "Samples" / "Pack" / "BD.wav").read_bytes()
    app = create_app(card, [], tmp_path / "copies", inbox_dir=tmp_path / "inbox")
    with TestClient(app) as client:

        def upload(root: str, path: str, name: str, data: bytes):
            return client.post("/api/import", params={"root": root, "path": path, "name": name}, content=data)

        # Inbox: name sanitized, identical content reused, different content gets a suffix
        first = upload("inbox", "", "Kick:Hard?.WAV", wav).json()
        assert first == {"source": "inbox:Kick_Hard_.wav", "name": "Kick_Hard_.wav"}
        assert upload("inbox", "", "Kick:Hard?.wav", wav).json()["name"] == "Kick_Hard_.wav"
        other = (card / "Samples" / "Pack" / "SD.wav").read_bytes()
        assert upload("inbox", "", "Kick:Hard?.wav", other).json()["name"] == "Kick_Hard__2.wav"

        # Card: only below a folder other than Patches
        assert client.post("/api/import/prepare", json={"root": "card", "path": "Samples/New"}).status_code == 200
        assert upload("card", "Samples/New", "a.wav", wav).json()["source"] == "card:Samples/New/a.wav"
        assert (card / "Samples" / "New" / "a.wav").read_bytes() == wav
        assert upload("card", "Patches/OneShots", "a.wav", wav).status_code == 403
        assert upload("card", "", "a.wav", wav).status_code == 403
        assert upload("card", "../outside", "a.wav", wav).status_code == 403

        # Only WAV files are accepted
        assert upload("inbox", "", "notes.wav", b"hello world, no wav").status_code == 400

        # Inbox files can be used as pad sources
        body = {"type": "oneshot", "name": "Dropped", "tags": [], "pads": [{"slot": 8, "source": first["source"]}]}
        assert client.post("/api/build/apply", json=body).status_code == 200
        assert (card / "UserPatches" / "OneShots" / "Dropped" / "Kick_Hard_.wav").is_file()


DEVICE_PATCH = """<?xml version="1.0" encoding="UTF-8"?>
<document>
    <session version="1">
        <track type="samtrack">
            <params cellname="Sparse" trkgain="0"/>
            <cell type="saminst">
                <params gaindb="0" pitch="0" panpos="0" velscreentrig="100" celldisppos="8"/>
            </cell>
            <cell type="samasst">
                <params filename="BD.wav" samstart="0" samlen="10" loopstart="0" loopend="10"/>
                <slices/>
            </cell>
            <cell type="noteseq">
                <params cellname="Seq 1"/>
                <sequence>
                    <seqevent pos="0" note="36"/>
                </sequence>
            </cell>
            <cell type="saminst">
                <params gaindb="0" pitch="0" panpos="0" celldisppos="12"/>
            </cell>
            <cell type="samasst">
                <params filename="SD.wav" samstart="0" samlen="10" loopstart="0" loopend="10"/>
                <slices/>
            </cell>
        </track>
    </session>
</document>
"""


def test_edit_adds_cells_for_pad_the_device_never_used() -> None:
    # Pad 6 is celldisppos 13, which the device patch does not contain
    sample = {"filename": "New.wav", "samstart": 0, "samlen": 5, "loopstart": 0, "loopend": 5}
    xml, errors = patchedit.edit_oneshot(DEVICE_PATCH, {8: ({"gaindb": -3000}, {}), 13: ({"gaindb": 0}, sample)})
    assert errors == []
    all_cells = patchedit.cells(xml)
    assert [c.type for c in all_cells] == ["saminst", "samasst", "noteseq", "saminst", "samasst", "saminst", "samasst"]
    assert all_cells[0].attrs["gaindb"] == "-3000"
    assert all_cells[-2].attrs["celldisppos"] == "13"
    assert all_cells[-1].attrs["filename"] == "New.wav"
    assert '<seqevent pos="0" note="36"/>' in xml
    assert xml.endswith("        </track>\n    </session>\n</document>\n")


def test_empty_patch_xml_reports_damage(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    patch = build_kit(card, tmp_path)
    (patch / "patch.xml").write_bytes(b"")
    app = create_app(card, [], tmp_path / "copies")
    ref = "UserPatches\\OneShots\\Kit"
    with TestClient(app) as client:
        for url in ("/api/patch", "/api/patch/load"):
            response = client.get(url, params={"ref": ref})
            assert response.status_code == 422
            assert "empty or damaged" in response.json()["detail"]
        body = {"type": "oneshot", "name": "Kit", "tags": [], "pads": [], "base_ref": ref, "mode": "edit"}
        assert client.post("/api/build/plan", json=body).status_code == 422


def test_writes_are_flushed(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    calls: list[int] = []
    monkeypatch.setattr(server, "flush_to_disk", lambda: calls.append(1))
    app = create_app(card, [], tmp_path / "copies")
    with TestClient(app) as client:
        client.get("/api/patches")
        assert calls == []
        client.post("/api/build/plan", json={"type": "oneshot", "name": "X", "tags": [], "pads": []})
        assert calls == [1]


def test_mount_device_matches_exact_mount_point() -> None:
    mounts = (
        "/dev/nvme0n1p2 / btrfs rw 0 0\n"
        "/dev/sdb1 /run/media/me/BB\\0402 exfat rw 0 0\n"
        "/dev/sdc1 /run/media/me/BB2 exfat rw 0 0\n"
    )
    assert eject.mount_device(Path("/run/media/me/BB2"), mounts) == "/dev/sdc1"
    assert eject.mount_device(Path("/run/media/me/BB 2"), mounts) == "/dev/sdb1"
    assert eject.mount_device(Path("/run/media/me/BB2/Patches"), mounts) is None


def test_eject_refuses_folder_that_is_no_drive(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    (card / "bb2-stng.mml").write_text("settings")
    app = create_app(card, [], tmp_path / "copies")
    with TestClient(app) as client:
        response = client.post("/api/card/eject")
        assert response.status_code == 409
        assert "not a separate drive" in response.json()["detail"]
        assert card.is_dir()


def test_restart_and_shutdown_stop_the_server(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(server.threading, "Timer", lambda _delay, fn: type("T", (), {"start": lambda self: fn()})())
    app = create_app(card, [], tmp_path / "copies")
    stops: list[int] = []
    app.state.stop_server = lambda: stops.append(1)
    with TestClient(app) as client:
        info = client.get("/api/info").json()
        assert info["pid"] > 0 and info["started_at"] > 0
        client.post("/api/shutdown")
        assert stops == [1] and not app.state.restart_requested
        client.post("/api/restart")
        assert stops == [1, 1] and app.state.restart_requested
