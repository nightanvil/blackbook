"""Find a mounted blackbox 2 card without a configured path."""

from __future__ import annotations

import getpass
import os
import string
import sys
from pathlib import Path


def is_card(path: Path) -> bool:
    try:
        return (path / "blackbox2.bin").is_file() or (
            (path / "bb2-stng.mml").is_file() and ((path / "UserPatches").is_dir() or (path / "Patches").is_dir())
        )
    except OSError:
        return False


def mount_points() -> list[Path]:
    """Directories where removable media usually appear on this platform."""
    if sys.platform == "win32":
        return [Path(f"{letter}:\\") for letter in string.ascii_uppercase if letter not in "AB"]
    if sys.platform == "darwin":
        bases = [Path("/Volumes")]
    else:
        try:
            user = getpass.getuser()
        except (KeyError, OSError):
            user = os.environ.get("USER", "")
        bases = [Path("/run/media") / user, Path("/media") / user, Path("/media"), Path("/mnt")]
    result: list[Path] = []
    for base in bases:
        try:
            result += sorted(p for p in base.iterdir() if p.is_dir())
        except OSError:
            continue
    return result


def find_cards() -> list[Path]:
    seen: set[Path] = set()
    cards: list[Path] = []
    for path in mount_points():
        if path not in seen and is_card(path):
            seen.add(path)
            cards.append(path)
    return cards
