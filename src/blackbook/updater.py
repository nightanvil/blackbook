"""Update check against GitHub releases and in-place update of a downloaded installation."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import __version__, settings

REPO = "nightanvil/blackbook"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"

# Folders of an installation that hold local data or platform binaries; an update never touches them
KEEP = {".blackbook", ".tools", ".venv", "backups", "local", "abnahme", ".git"}


class UpdateError(Exception):
    pass


def parse_version(text: str) -> tuple[int, ...]:
    parts = []
    for piece in text.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_git_checkout(root: Path = settings.REPO_DIR) -> bool:
    return (root / ".git").exists()


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "blackbook-update-check", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def check_git(root: Path = settings.REPO_DIR) -> dict:
    """Development checkout: count commits on the upstream branch that are not here yet."""

    def git(*args: str) -> str:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            raise UpdateError(result.stderr.strip() or "git failed")
        return result.stdout.strip()

    try:
        git("fetch", "--quiet")
        behind = int(git("rev-list", "--count", "HEAD..@{u}"))
    except (OSError, subprocess.SubprocessError, UpdateError, ValueError) as exc:
        return {"mode": "git", "available": False, "error": str(exc)}
    return {"mode": "git", "available": behind > 0, "behind": behind, "current": __version__}


def check_release() -> dict:
    try:
        latest = fetch_json(LATEST_URL)
    except Exception as exc:  # noqa: BLE001 - no network, rate limit or no release yet
        return {"mode": "release", "available": False, "current": __version__, "error": str(exc)}
    tag = latest.get("tag_name", "")
    return {
        "mode": "release",
        "current": __version__,
        "latest": tag.lstrip("vV"),
        "available": bool(tag) and parse_version(tag) > parse_version(__version__),
        "url": latest.get("html_url", ""),
        "zip_url": latest.get("zipball_url", ""),
    }


def check() -> dict:
    return check_git() if is_git_checkout() else check_release()


def install_zip(data: bytes, root: Path = settings.REPO_DIR) -> list[str]:
    """Copy the files of a release archive over the installation, keeping local data."""
    written: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.infolist():
                try:
                    (tmp_dir / member.filename).resolve().relative_to(tmp_dir.resolve())
                except ValueError as exc:
                    raise UpdateError("unexpected path in the update: " + member.filename) from exc
            zf.extractall(tmp_dir)
        # GitHub archives contain one top-level folder
        tops = [p for p in tmp_dir.iterdir()]
        source = tops[0] if len(tops) == 1 and tops[0].is_dir() else tmp_dir
        if not (source / "start.sh").is_file() or not (source / "src" / "blackbook").is_dir():
            raise UpdateError("the download does not look like a blackbook release")
        for path in sorted(source.rglob("*")):
            rel = path.relative_to(source)
            if rel.parts[0] in KEEP or path.is_dir():
                continue
            target = root / rel
            data_new = path.read_bytes()
            if target.is_file() and target.read_bytes() == data_new:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Write next to the target and swap, so a running start script keeps reading its old file
            tmp_file = target.with_name(target.name + ".blackbook-update")
            tmp_file.write_bytes(data_new)
            shutil.copymode(path, tmp_file)
            os.replace(tmp_file, target)
            written.append(rel.as_posix())
    return written


def apply_release() -> dict:
    if is_git_checkout():
        raise UpdateError("this is a development checkout, update it with git pull")
    info = check_release()
    if not info.get("available"):
        raise UpdateError("no newer release available")
    request = urllib.request.Request(info["zip_url"], headers={"User-Agent": "blackbook-update-check"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    written = install_zip(data)
    return {"version": info["latest"], "files": len(written)}
