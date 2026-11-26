"""Versioned card backups in a local git repository.

Layout of the backup folder:

    <target>/
    ├── .git/
    ├── .gitattributes
    ├── blackbook-backup.toml    configuration
    └── card/                    mirror of the included card paths
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import subprocess
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "blackbook-backup.toml"
MIRROR = "card"
MTIME_TOLERANCE = 2.0  # FAT32 stores modification times with 2 second resolution

DEFAULT_CONFIG = """\
# blackbook backup configuration

# Paths on the card that are backed up, relative to the card root
include = [
    "Projects",
    "UserPatches",
    "Samples",
    "Patches/patchindex.xml",
    "bb2-stng.mml",
]

# Factory patches (about 8 GB, unchanged, available as download from 1010music)
include_factory = false

# File and folder name patterns that are never backed up
exclude = [
    "*.pk",
    "*.blackbook-tmp",
    ".Trash-*",
    "System Volume Information",
    "$RECYCLE.BIN",
    ".DS_Store",
    "._*",
    "Thumbs.db",
]

# Files the device rewrites on its own (last project, settings). They are backed up
# with the next snapshot, but a change in them alone creates no automatic snapshot
minor = [
    "bb2-stng.mml",
]

# Create a snapshot automatically when the card is connected while blackbook runs
snapshot_on_connect = true

# Create a snapshot automatically before blackbook writes to the card
snapshot_before_write = true
"""

GITATTRIBUTES = """\
# Card files are stored byte-identical
* -text
*.wav binary
*.xml diff
*.mml diff
"""


class SnapshotError(Exception):
    pass


@dataclass
class Config:
    include: list[str]
    include_factory: bool
    exclude: list[str]
    snapshot_on_connect: bool
    snapshot_before_write: bool
    minor: list[str]

    @classmethod
    def load(cls, path: Path) -> Config:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        defaults = tomllib.loads(DEFAULT_CONFIG)
        merged = {**defaults, **data}
        return cls(
            include=[str(p) for p in merged["include"]],
            include_factory=bool(merged["include_factory"]),
            exclude=[str(p) for p in merged["exclude"]],
            snapshot_on_connect=bool(merged["snapshot_on_connect"]),
            snapshot_before_write=bool(merged["snapshot_before_write"]),
            minor=[str(p) for p in merged["minor"]],
        )

    def roots(self) -> list[str]:
        roots = [p.strip("/\\").replace("\\", "/") for p in self.include]
        if self.include_factory and "Patches" not in roots:
            roots.append("Patches")
        return [r for r in dict.fromkeys(roots) if r]

    def excluded(self, name: str) -> bool:
        return any(fnmatch.fnmatch(name, pattern) for pattern in self.exclude)

    def is_minor(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in self.minor)


@dataclass
class SyncResult:
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.modified or self.deleted)


@dataclass
class Commit:
    id: str
    date: str
    subject: str
    body: str


@dataclass
class FileChange:
    status: str
    path: str


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def same_file(src: Path, dst: Path) -> bool:
    if not dst.is_file():
        return False
    s, d = src.stat(), dst.stat()
    if s.st_size != d.st_size:
        return False
    if abs(s.st_mtime - d.st_mtime) <= MTIME_TOLERANCE:
        return True
    return file_hash(src) == file_hash(dst)


def summarize(paths: list[str]) -> dict[str, int]:
    """Group card paths by project or patch folder."""
    groups: dict[str, int] = {}
    for path in paths:
        parts = path.split("/")
        if parts[0] == "Projects" and len(parts) > 2:
            key = "/".join(parts[:2])
        elif parts[0] in ("UserPatches", "Patches") and len(parts) > 3:
            key = "/".join(parts[:3])
        elif parts[0] == "Samples" and len(parts) > 2:
            key = "/".join(parts[:2])
        else:
            key = path
        groups[key] = groups.get(key, 0) + 1
    return groups


class SnapshotRepo:
    def __init__(self, target: Path):
        self.target = target.resolve()
        self.mirror = self.target / MIRROR
        self.lock = threading.Lock()

    # ---------- setup ----------

    @property
    def config_path(self) -> Path:
        return self.target / CONFIG_NAME

    @property
    def initialized(self) -> bool:
        return (self.target / ".git").is_dir() and self.config_path.is_file()

    def init(self) -> None:
        if shutil.which("git") is None:
            raise SnapshotError("git is not installed or not on PATH")
        self.target.mkdir(parents=True, exist_ok=True)
        if not (self.target / ".git").is_dir():
            self.git("init", "--quiet", "--initial-branch=main")
            # Audio does not compress well, fast compression keeps snapshots quick
            self.git("config", "core.compression", "1")
            self.git("config", "core.autocrlf", "false")
        if not self.config_path.exists():
            self.config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
        attributes = self.target / ".gitattributes"
        if not attributes.exists():
            attributes.write_text(GITATTRIBUTES, encoding="utf-8")
        self.mirror.mkdir(exist_ok=True)

    def config(self) -> Config:
        return Config.load(self.config_path)

    # ---------- git ----------

    def git(self, *args: str, binary: bool = False) -> str | bytes:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
        identity: list[str] = []
        if args and args[0] == "commit":
            # Fallback identity for machines without a git user configuration
            for key, value in (("user.name", "blackbook"), ("user.email", "blackbook@localhost")):
                probe = subprocess.run(["git", "-C", str(self.target), "config", key], capture_output=True, check=False)
                if not probe.stdout.strip():
                    identity += ["-c", f"{key}={value}"]
        result = subprocess.run(
            ["git", "-C", str(self.target), *identity, *args], capture_output=True, env=env, check=False
        )
        if result.returncode != 0:
            raise SnapshotError(result.stderr.decode("utf-8", "replace").strip() or f"git {args[0]} failed")
        return result.stdout if binary else result.stdout.decode("utf-8", "replace")

    def has_commits(self) -> bool:
        try:
            self.git("rev-parse", "--verify", "--quiet", "HEAD")
            return True
        except SnapshotError:
            return False

    # ---------- sync ----------

    def card_files(self, card_root: Path, config: Config) -> dict[str, Path]:
        """Collect all included card files as {card relative posix path: path}."""
        files: dict[str, Path] = {}
        for root in config.roots():
            start = card_root / root
            if start.is_file():
                if not config.excluded(start.name):
                    files[root] = start
                continue
            if not start.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(start):
                dirnames[:] = sorted(d for d in dirnames if not config.excluded(d))
                for name in sorted(filenames):
                    if config.excluded(name):
                        continue
                    path = Path(dirpath) / name
                    files[path.relative_to(card_root).as_posix()] = path
        return files

    def mirror_files(self, config: Config) -> dict[str, Path]:
        files: dict[str, Path] = {}
        if not self.mirror.is_dir():
            return files
        for root in config.roots():
            start = self.mirror / root
            if start.is_file():
                files[root] = start
            elif start.is_dir():
                for path in start.rglob("*"):
                    if path.is_file():
                        files[path.relative_to(self.mirror).as_posix()] = path
        return files

    def sync_from_card(self, card_root: Path) -> SyncResult:
        config = self.config()
        source = self.card_files(card_root, config)
        existing = self.mirror_files(config)
        result = SyncResult()

        for rel, src in source.items():
            dst = self.mirror / rel
            if rel not in existing:
                result.added.append(rel)
            elif same_file(src, dst):
                continue
            else:
                result.modified.append(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        for rel, path in existing.items():
            if rel not in source:
                path.unlink()
                result.deleted.append(rel)
        self._remove_empty_dirs()
        return result

    def _remove_empty_dirs(self) -> None:
        for dirpath, _, _ in sorted(os.walk(self.mirror), key=lambda e: -len(e[0])):
            path = Path(dirpath)
            if path != self.mirror and not any(path.iterdir()):
                path.rmdir()

    # ---------- snapshots ----------

    def snapshot(self, card_root: Path, reason: str = "Snapshot", automatic: bool = False) -> Commit | None:
        """Mirror the card and commit. Returns None when nothing changed.

        An automatic snapshot whose changes are all minor files leaves them
        uncommitted in the mirror, the next snapshot includes them.
        """
        with self.lock:
            if not self.initialized:
                self.init()
            self.sync_from_card(card_root)
            self.git("add", "--all", ".")
            status = self.git("status", "--porcelain")
            if not status.strip():
                return None
            out = self.git("diff", "--cached", "--name-status", "-z", "--no-renames", "--relative=" + MIRROR)
            fields = [f for f in out.split("\0") if f]
            staged = list(zip(fields[0::2], fields[1::2]))
            if automatic and staged and all(self.config().is_minor(path) for _, path in staged):
                return None

            added = sum(1 for st, _ in staged if st == "A")
            deleted = sum(1 for st, _ in staged if st == "D")
            modified = len(staged) - added - deleted
            groups = summarize([path for _, path in staged])
            subject = f"{reason}: {added} added, {modified} modified, {deleted} deleted"
            lines = [f"{key} ({count})" for key, count in sorted(groups.items())]
            if len(lines) > 60:
                lines = [*lines[:60], f"... and {len(lines) - 60} more"]
            body = "\n".join(lines)
            self.git("commit", "--quiet", "-m", subject, "-m", body or "configuration")
            return self.log(1)[0]

    def log(self, limit: int = 100) -> list[Commit]:
        if not self.has_commits():
            return []
        out = self.git("log", f"-{limit}", "--format=%H%x1f%aI%x1f%s%x1f%b%x1e")
        commits = []
        for record in out.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            commit_id, date, subject, body = (record.split("\x1f") + ["", "", "", ""])[:4]
            commits.append(Commit(commit_id, date, subject, body.strip()))
        return commits

    def changes(self, commit: str) -> list[FileChange]:
        out = self.git("show", "--format=", "--name-status", "--no-renames", commit, "--", MIRROR)
        changes = []
        for line in out.splitlines():
            if "\t" in line:
                status, path = line.split("\t", 1)
                changes.append(FileChange(status[0], path.removeprefix(MIRROR + "/")))
        return changes

    def file_diff(self, commit: str, path: str) -> str:
        return self.git("show", "--format=", commit, "--", f"{MIRROR}/{path}")

    def files_at(self, commit: str, prefix: str = "") -> list[str]:
        spec = f"{MIRROR}/{prefix.strip('/')}" if prefix.strip("/") else MIRROR
        out = self.git("ls-tree", "-r", "--name-only", commit, "--", spec)
        return [line.removeprefix(MIRROR + "/") for line in out.splitlines() if line]

    # ---------- restore ----------

    def restore(self, card_root: Path, commit: str, prefix: str = "") -> dict[str, list[str]]:
        """Restore a file, a folder or the whole backup scope from a commit onto the card.

        The current card state is committed first. Within the restored scope the card
        afterwards matches the commit exactly: files missing in the commit are deleted.
        """
        commit = self.git("rev-parse", "--verify", commit + "^{commit}").strip()
        self.snapshot(card_root, f"Before restore of {prefix or 'everything'} from {commit[:10]}")

        with self.lock:
            config = self.config()
            prefix = prefix.strip("/")
            # A scope missing in the commit restores to "absent": its files are removed
            wanted = self.files_at(commit, prefix)

            restored: list[str] = []
            for rel in wanted:
                data = self.git("show", f"{commit}:{MIRROR}/{rel}", binary=True)
                dst = card_root / rel
                if dst.is_file() and dst.read_bytes() == data:
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
                restored.append(rel)

            # Remove card files inside the restored scope that the commit does not contain
            removed: list[str] = []
            wanted_set = set(wanted)
            for rel, path in self.card_files(card_root, config).items():
                in_scope = not prefix or rel == prefix or rel.startswith(prefix + "/")
                if in_scope and rel not in wanted_set:
                    path.unlink()
                    removed.append(rel)

        self.snapshot(card_root, f"Restore {prefix or 'everything'} from {commit[:10]}")
        return {"restored": restored, "removed": removed}

    # ---------- info ----------

    def status(self) -> dict:
        info: dict = {
            "target": str(self.target),
            "initialized": self.initialized,
            "commits": 0,
            "last": None,
            "size_bytes": 0,
        }
        if not self.initialized:
            return info
        if self.has_commits():
            info["commits"] = int(self.git("rev-list", "--count", "HEAD").strip())
            last = self.log(1)[0]
            info["last"] = {"id": last.id, "date": last.date, "subject": last.subject}
        git_dir = self.target / ".git"
        info["size_bytes"] = sum(p.stat().st_size for p in git_dir.rglob("*") if p.is_file())
        return info
