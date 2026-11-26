"""Command line entry point.

blackbook [--card PATH] [options]              start the browser UI
blackbook snapshot [--card PATH] [-m TEXT]     create a backup snapshot without UI
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

from . import settings

REPO_DIR = settings.REPO_DIR


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--card",
        default=os.environ.get("BLACKBOOK_CARD"),
        help="path to the mounted card or a mirror (default: $BLACKBOOK_CARD)",
    )
    parser.add_argument(
        "--backup-target",
        default=os.environ.get("BLACKBOOK_BACKUP_TARGET"),
        help="git backup folder (default: $BLACKBOOK_BACKUP_TARGET or the folder chosen in the UI)",
    )


def resolve_target(value: str | None) -> Path | None:
    if value:
        return Path(value).expanduser()
    stored = settings.get("backup_target")
    return Path(stored) if stored else None


def serve(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="blackbook", description="blackbox 2 card toolkit")
    add_common(parser)
    parser.add_argument(
        "--library",
        action="append",
        default=[],
        help="additional local sample folder for the browser, can be given multiple times",
    )
    parser.add_argument(
        "--backup-dir",
        default=os.environ.get("BLACKBOOK_BACKUP_DIR", str(REPO_DIR / "backups")),
        help="folder for copies of modified card files (default: <repo>/backups)",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)

    if not args.card:
        parser.error("--card or BLACKBOOK_CARD is required")

    import uvicorn

    from .server import create_app

    app = create_app(
        Path(args.card),
        [Path(p) for p in args.library],
        Path(args.backup_dir),
        resolve_target(args.backup_target),
    )
    url = f"http://127.0.0.1:{args.port}/"
    print(f"blackbook running at {url}")
    if not Path(args.card).is_dir():
        print(f"card not found at {args.card}, waiting for it (switch the blackbox to microSD mode)")
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


def snapshot(argv: list[str]) -> None:
    from .snapshot import SnapshotError, SnapshotRepo

    parser = argparse.ArgumentParser(prog="blackbook snapshot", description="create a backup snapshot")
    add_common(parser)
    parser.add_argument("-m", "--message", default="Manual snapshot", help="reason shown in the commit subject")
    args = parser.parse_args(argv)

    if not args.card:
        parser.error("--card or BLACKBOOK_CARD is required")
    target = resolve_target(args.backup_target)
    if target is None:
        parser.error("--backup-target is required until a backup folder is chosen in the UI")

    card = Path(args.card)
    if not card.is_dir():
        sys.exit(f"card not found: {card}")
    try:
        commit = SnapshotRepo(target).snapshot(card, args.message)
    except SnapshotError as exc:
        sys.exit(f"snapshot failed: {exc}")
    if commit is None:
        print("no changes since the last snapshot")
    else:
        print(f"{commit.id[:10]} {commit.subject}")
        if commit.body:
            print(commit.body)


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "snapshot":
        snapshot(argv[1:])
    else:
        serve(argv)


if __name__ == "__main__":
    main()
