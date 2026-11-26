"""Copies of files before blackbook modifies them, stored outside the card."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


class Backup:
    """One backup session per server start, located at <base>/<timestamp>/."""

    def __init__(self, base: Path, card_root: Path):
        self.card_root = card_root
        self.dir = base / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.journal = self.dir / "journal.json"

    def _log(self, action: str, path: Path) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        entries = json.loads(self.journal.read_text()) if self.journal.exists() else []
        entries.append(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "action": action,
                "path": path.relative_to(self.card_root).as_posix(),
            }
        )
        self.journal.write_text(json.dumps(entries, indent=2))

    def save(self, path: Path) -> None:
        """Copy an existing card file before it is modified. Only the first version is kept."""
        if not path.exists():
            self._log("create", path)
            return
        target = self.dir / "files" / path.relative_to(self.card_root)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        self._log("modify", path)

    def record_created(self, path: Path) -> None:
        self._log("create", path)
