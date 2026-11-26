from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from blackbook import settings, updater
from blackbook.server import create_app


def release_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, text in files.items():
            zf.writestr("nightanvil-blackbook-abc123/" + name, text)
    return buffer.getvalue()


def test_parse_version() -> None:
    assert updater.parse_version("v0.2.0") > updater.parse_version("0.1.9")
    assert updater.parse_version("0.10.0") > updater.parse_version("0.9.1")


def test_install_zip_keeps_local_data(tmp_path: Path) -> None:
    (tmp_path / ".blackbook").mkdir()
    (tmp_path / ".blackbook" / "settings.json").write_text("mine")
    (tmp_path / "README.md").write_text("old")
    data = release_zip({
        "start.sh": "new",
        "README.md": "new readme",
        "src/blackbook/__init__.py": "x",
        ".blackbook/settings.json": "theirs",
    })
    written = updater.install_zip(data, tmp_path)
    assert (tmp_path / "README.md").read_text() == "new readme"
    assert (tmp_path / ".blackbook" / "settings.json").read_text() == "mine"
    assert ".blackbook/settings.json" not in written


def test_install_zip_rejects_foreign_archive(tmp_path: Path) -> None:
    with pytest.raises(updater.UpdateError):
        updater.install_zip(release_zip({"other.txt": "x"}), tmp_path)


def test_check_release_compares_versions(monkeypatch) -> None:
    monkeypatch.setattr(updater, "fetch_json", lambda url: {"tag_name": "v99.0.0", "zipball_url": "z", "html_url": "h"})
    info = updater.check_release()
    assert info["available"] is True and info["latest"] == "99.0.0"

    def offline(url):
        raise OSError("offline")

    monkeypatch.setattr(updater, "fetch_json", offline)
    assert updater.check_release()["available"] is False


def test_folder_picker(card: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    (tmp_path / "pick" / "B").mkdir(parents=True)
    (tmp_path / "pick" / "a").mkdir()
    with TestClient(create_app(card, [], tmp_path / "copies")) as client:
        listing = client.get("/api/fs/dirs", params={"path": str(tmp_path / "pick")}).json()
        assert listing["dirs"] == ["a", "B"]
        created = client.post("/api/fs/mkdir", json={"path": str(tmp_path / "pick"), "name": "new"})
        assert created.status_code == 200 and (tmp_path / "pick" / "new").is_dir()
        assert client.post("/api/fs/mkdir", json={"path": str(tmp_path / "pick"), "name": "../x"}).status_code == 400
        assert client.get("/api/fs/dirs", params={"path": str(card)}).json()["is_card"] is True
