"""Command line entry point.

blackbook [--card PATH] [options]              start the browser UI
blackbook snapshot [--card PATH] [-m TEXT]     create a backup snapshot without UI
"""

from __future__ import annotations

import argparse
import os
import subprocess
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

    detect = not args.card
    card_path = Path(args.card) if args.card else initial_card()

    import uvicorn

    from .server import create_app

    app = create_app(
        card_path,
        [Path(p) for p in args.library],
        Path(args.backup_dir),
        resolve_target(args.backup_target),
        detect_card=detect,
    )
    url = f"http://127.0.0.1:{args.port}/"
    print()
    print(f"blackbook is running. Open this address in your browser: {url}")
    if card_path.is_dir():
        print(f"card: {card_path}")
    elif detect:
        print("No blackbox card found yet. Connect the blackbox 2 over USB and switch it to microSD mode")
        print("(or insert the card into a card reader). blackbook picks it up by itself.")
    else:
        print(f"card not found at {card_path}, waiting for it (switch the blackbox to microSD mode)")
    print("Keep this window open while you use blackbook. Close it to stop blackbook.")
    if not args.no_browser:
        webbrowser.open(url)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning", timeout_graceful_shutdown=5)
    )
    app.state.stop_server = lambda: setattr(server, "should_exit", True)
    server.run()
    if app.state.restart_requested:
        restart(argv)


def restart(argv: list[str]) -> None:
    """Start blackbook again with the same arguments, in the same terminal window."""
    print()
    print("Restarting blackbook ...")
    command = [sys.executable, "-m", "blackbook", *argv]
    if "--no-browser" not in argv:
        command.append("--no-browser")
    if os.name == "nt":
        # Windows has no exec: run the new instance as a child and pass on its exit code
        sys.exit(subprocess.call(command))
    os.execv(sys.executable, command)


def initial_card() -> Path:
    """The last card if it is mounted, else a detected card, else the last path (the server waits for it)."""
    from .carddetect import find_cards, is_card

    stored = settings.get("card_path")
    if stored and is_card(Path(stored)):
        return Path(stored)
    cards = find_cards()
    if cards:
        if len(cards) > 1:
            print("several cards found, using the first: " + ", ".join(str(c) for c in cards))
        settings.set_value("card_path", str(cards[0]))
        return cards[0]
    # Placeholder until the card watcher finds a card
    return Path(stored) if stored else settings.REPO_DIR / ".blackbook" / "no-card"


def snapshot(argv: list[str]) -> None:
    from .snapshot import SnapshotError, SnapshotRepo

    parser = argparse.ArgumentParser(prog="blackbook snapshot", description="create a backup snapshot")
    add_common(parser)
    parser.add_argument("-m", "--message", default="Manual snapshot", help="reason shown in the commit subject")
    args = parser.parse_args(argv)

    if not args.card:
        args.card = settings.get("card_path")
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
