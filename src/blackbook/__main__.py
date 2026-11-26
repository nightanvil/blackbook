"""Command line entry point: python -m blackbook --card <path>."""

from __future__ import annotations

import argparse
import os
import webbrowser
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(prog="blackbook", description="blackbox 2 card toolkit")
    parser.add_argument(
        "--card",
        default=os.environ.get("BLACKBOOK_CARD"),
        help="path to the mounted card or a mirror (default: $BLACKBOOK_CARD)",
    )
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
    args = parser.parse_args()

    if not args.card:
        parser.error("--card or BLACKBOOK_CARD is required")

    import uvicorn

    from .server import create_app

    app = create_app(Path(args.card), [Path(p) for p in args.library], Path(args.backup_dir))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"blackbook running at {url}")
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
