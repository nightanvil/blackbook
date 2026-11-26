from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from blackbook import settings
from blackbook.server import create_app
from blackbook.snapshot import SnapshotRepo

from .conftest import make_wav


@pytest.fixture
def repo(tmp_path: Path) -> SnapshotRepo:
    return SnapshotRepo(tmp_path / "backup")


def touch_later(path: Path) -> None:
    """Move the modification time forward beyond the FAT tolerance."""
    stamp = time.time() + 10
    os.utime(path, (stamp, stamp))


def test_first_snapshot_respects_include_and_exclude(card: Path, repo: SnapshotRepo) -> None:
    (card / "Projects" / "Song" / "RC000001.wav.pk").write_bytes(b"cache")
    (card / ".Trash-1000").mkdir()
    (card / ".Trash-1000" / "x.wav").write_bytes(b"x")
    (card / "bb2-stng.mml").write_text("settings")

    commit = repo.snapshot(card, "Initial")
    assert commit is not None
    assert commit.subject.startswith("Initial: ")

    files = set(repo.files_at("HEAD"))
    assert "Projects/Song/project.xml" in files
    assert "Samples/Pack/BD.wav" in files
    assert "Patches/patchindex.xml" in files
    assert "bb2-stng.mml" in files
    assert not any(f.endswith(".pk") for f in files)
    assert not any(f.startswith("Patches/OneShots") for f in files)
    assert not any("Trash" in f for f in files)
    assert (repo.target / "blackbook-backup.toml").is_file()


def test_no_changes_returns_none(card: Path, repo: SnapshotRepo) -> None:
    repo.snapshot(card)
    assert repo.snapshot(card) is None


def test_detects_add_modify_delete(card: Path, repo: SnapshotRepo) -> None:
    repo.snapshot(card, "Initial")
    project = card / "Projects" / "Song"
    make_wav(project / "RC000003.wav")
    xml = project / "project.xml"
    xml.write_text(xml.read_text(encoding="utf-8-sig").replace("BD.wav", "SD.wav"), encoding="utf-8")
    touch_later(xml)
    (project / "RC000002.wav").unlink()

    commit = repo.snapshot(card, "Session")
    assert commit.subject == "Session: 1 added, 1 modified, 1 deleted"
    assert "Projects/Song (3)" in commit.body
    changes = {c.path: c.status for c in repo.changes(commit.id)}
    assert changes == {
        "Projects/Song/RC000003.wav": "A",
        "Projects/Song/project.xml": "M",
        "Projects/Song/RC000002.wav": "D",
    }
    assert "SD.wav" in repo.file_diff(commit.id, "Projects/Song/project.xml")


def test_same_size_different_content_is_detected(card: Path, repo: SnapshotRepo) -> None:
    repo.snapshot(card)
    wav = card / "Samples" / "Pack" / "BD.wav"
    data = bytearray(wav.read_bytes())
    data[-1] ^= 0xFF
    wav.write_bytes(bytes(data))
    touch_later(wav)
    commit = repo.snapshot(card)
    assert [c.path for c in repo.changes(commit.id)] == ["Samples/Pack/BD.wav"]


def test_restore_folder_is_exact(card: Path, repo: SnapshotRepo) -> None:
    first = repo.snapshot(card, "Initial")
    project = card / "Projects" / "Song"
    original_xml = (project / "project.xml").read_bytes()
    (project / "project.xml").write_text("broken", encoding="utf-8")
    (project / "RC000001.wav").unlink()
    make_wav(project / "RC000099.wav")
    repo.snapshot(card, "Broken")

    result = repo.restore(card, first.id, "Projects/Song")
    assert (project / "project.xml").read_bytes() == original_xml
    assert (project / "RC000001.wav").is_file()
    assert not (project / "RC000099.wav").exists()
    assert sorted(result["restored"]) == ["Projects/Song/RC000001.wav", "Projects/Song/project.xml"]
    assert result["removed"] == ["Projects/Song/RC000099.wav"]

    subjects = [c.subject for c in repo.log()]
    assert subjects[0].startswith("Restore Projects/Song from")
    # Unaffected files outside the scope stay untouched
    assert (card / "Samples" / "Pack" / "BD.wav").is_file()


def test_restore_single_deleted_file(card: Path, repo: SnapshotRepo) -> None:
    first = repo.snapshot(card)
    target = card / "Samples" / "Pack" / "SD.wav"
    content = target.read_bytes()
    target.unlink()
    repo.snapshot(card)
    repo.restore(card, first.id, "Samples/Pack/SD.wav")
    assert target.read_bytes() == content


def test_restore_scope_absent_in_commit_removes_it(card: Path, repo: SnapshotRepo) -> None:
    first = repo.snapshot(card)
    make_wav(card / "Samples" / "New" / "x.wav")
    repo.snapshot(card)
    result = repo.restore(card, first.id, "Samples/New")
    assert result["removed"] == ["Samples/New/x.wav"]
    assert not (card / "Samples" / "New" / "x.wav").exists()


def test_api_backup_flow_and_snapshot_before_write(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    (card / "bb2-stng.mml").write_text("settings")
    app = create_app(card, [], tmp_path / "copies")
    with TestClient(app) as client:
        assert client.get("/api/backup/status").json()["initialized"] is False
        assert client.put("/api/backup/target", json={"path": str(card / "inside")}).status_code == 400

        status = client.put("/api/backup/target", json={"path": str(tmp_path / "bk")}).json()
        assert status["initialized"] is True
        assert settings.get("backup_target") == str((tmp_path / "bk").resolve())

        # Setting the folder takes the first snapshot
        assert status["commits"] == 1
        assert client.get("/api/backup/log").json()[0]["subject"].startswith("Initial snapshot:")
        assert client.post("/api/backup/snapshot", json={"message": "Again"}).json()["commit"] is None

        body = {
            "type": "oneshot",
            "name": "Kit",
            "tags": ["Drum"],
            "pads": [{"slot": 0, "source": "card:Samples/Pack/BD.wav"}],
        }
        make_wav(card / "Projects" / "Song" / "RC000005.wav")
        assert client.post("/api/build/apply", json=body).status_code == 200

        log = client.get("/api/backup/log").json()
        assert log[1]["subject"].startswith("Before creating UserPatches\\OneShots\\Kit: 1 added")
        changes = client.get("/api/backup/commit", params={"id": log[1]["id"]}).json()
        assert changes == [{"status": "A", "path": "Projects/Song/RC000005.wav"}]
        assert log[0]["subject"].startswith("After creating UserPatches\\OneShots\\Kit:")
        after = {c["path"] for c in client.get("/api/backup/commit", params={"id": log[0]["id"]}).json()}
        assert "UserPatches/OneShots/Kit/patch.xml" in after
        status = client.get("/api/backup/status").json()
        assert status["events"][0]["text"].startswith("Snapshot created (After creating")
        assert status["size_bytes"] == status["history_bytes"] + status["mirror_bytes"] > 0

        config = client.get("/api/backup/config").json()["text"]
        assert "include_factory = false" in config
        assert client.put("/api/backup/config", json={"text": "include = ["}).status_code == 400


def test_server_starts_without_card(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    app = create_app(tmp_path / "absent", [], tmp_path / "copies")
    with TestClient(app) as client:
        assert client.get("/api/card/status").json() == {"present": False}
        assert client.get("/api/patches").json() == []
        assert client.get("/api/projects").json() == []


def test_automatic_snapshot_skips_minor_changes_alone(card: Path, repo: SnapshotRepo) -> None:
    settings_file = card / "bb2-stng.mml"
    settings_file.write_text('<preset name="A"/>', encoding="utf-8")
    repo.snapshot(card, "Initial")
    settings_file.write_text('<preset name="B"/>', encoding="utf-8")
    touch_later(settings_file)
    assert repo.snapshot(card, "Card connected", automatic=True) is None
    assert repo.snapshot(card, "Card connected", automatic=True) is None

    make_wav(card / "Projects" / "Song" / "RC000003.wav")
    commit = repo.snapshot(card, "Card connected", automatic=True)
    changes = {c.path for c in repo.changes(commit.id)}
    assert changes == {"bb2-stng.mml", "Projects/Song/RC000003.wav"}


def test_manual_snapshot_keeps_minor_changes(card: Path, repo: SnapshotRepo) -> None:
    settings_file = card / "bb2-stng.mml"
    settings_file.write_text('<preset name="A"/>', encoding="utf-8")
    repo.snapshot(card, "Initial")
    settings_file.write_text('<preset name="B"/>', encoding="utf-8")
    touch_later(settings_file)
    assert repo.snapshot(card, "Manual") is not None


def test_card_present_survives_refused_mount_point(tmp_path: Path, monkeypatch) -> None:
    from blackbook import server

    def refuse(self) -> bool:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "is_file", refuse)
    snapshots = server.SnapshotService(server.Card(tmp_path), None)
    assert snapshots.card_present() is False


def test_info_reports_code_commit(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    with TestClient(create_app(card, [], tmp_path / "copies")) as client:
        info = client.get("/api/info").json()
    assert info["commit"] == info["current_commit"]


def test_backup_setup_uses_suggested_folder(card: Path, tmp_path: Path, monkeypatch) -> None:
    from blackbook import server

    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(server, "default_target", lambda: tmp_path / "Documents" / "blackbook-backup")
    (card / "bb2-stng.mml").write_text("settings")
    with TestClient(create_app(card, [], tmp_path / "copies")) as client:
        info = client.get("/api/info").json()
        assert info["backup_ready"] is False
        assert info["suggested_backup"].endswith("blackbook-backup")
        status = client.post("/api/backup/setup").json()
        assert status["initialized"] is True and status["commits"] == 1
        assert client.get("/api/info").json()["backup_ready"] is True


def test_backup_in_used_folder_gets_subfolder(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    documents = tmp_path / "Documents"
    documents.mkdir()
    (documents / "letter.txt").write_text("private")
    with TestClient(create_app(card, [], tmp_path / "copies")) as client:
        status = client.put("/api/backup/target", json={"path": str(documents)}).json()
    assert status["target"] == str((documents / "blackbook-backup").resolve())
    assert sorted(p.name for p in documents.iterdir()) == ["blackbook-backup", "letter.txt"]


def test_backup_inside_program_folder_is_refused(card: Path, tmp_path: Path, monkeypatch) -> None:
    program = tmp_path / "blackbook"
    program.mkdir()
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "REPO_DIR", program)
    with TestClient(create_app(card, [], tmp_path / "copies")) as client:
        refused = client.put("/api/backup/target", json={"path": str(program / "backup")})
        assert refused.status_code == 400 and "blackbook folder" in refused.json()["detail"]
        assert client.get("/api/fs/dirs", params={"path": str(program)}).json()["is_program"] is True
        assert client.put("/api/backup/target", json={"path": str(tmp_path / "outside")}).status_code == 200
