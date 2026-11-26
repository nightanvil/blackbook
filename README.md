# blackbook

Toolkit for the microSD card of the 1010music blackbox 2. Builds patches on the computer, integrates an external audio editor, keeps versioned backups of the card and organizes projects, patches and samples. All references in `project.xml`, `patch.xml` and `patchindex.xml` stay consistent.

Status: concept phase, no working code yet.

## Features (planned)

- Patch builder: create and edit one-shot, multisample, loop, slicer and shredder patches on the computer, including tags
- External editor: edit WAVs in Reaper or another editor, lengths and references are updated automatically
- Backup: incremental, deduplicated snapshots, diff between any two states, restore down to single files
- Organization: library with audition, bulk tagging, renaming with reference updates, batch rename, consistency checks
- Safety: dry run with diff preview and a snapshot before every write

Details in [docs/features.md](docs/features.md).

## Platforms

| Platform | Status |
|---|---|
| Linux | target platform |
| Windows | target platform |
| macOS | expected to work, untested |

## Technology

- Backend: Python 3.12+, FastAPI
- Frontend: HTML and JavaScript without a build step, served by the backend
- Runs as a local server, used in the browser at `http://127.0.0.1`
- Works on the mounted card (blackbox 2 in microSD mode, card reader) or a local mirror of the card

## Setup

The bootstrap installs the complete toolchain inside the repository. Nothing is installed system-wide. Running the bootstrap requires any Python 3.8 or newer; the command is the same on every platform.

| Directory | Content |
|---|---|
| `.tools/uv/` | uv package manager, downloaded from GitHub releases and verified via SHA-256 |
| `.tools/python/` | Python interpreter managed by uv |
| `.tools/cache/` | download cache |
| `.venv/` | virtual environment with all dependencies |

```
python bootstrap.py            # runtime dependencies
python bootstrap.py --dev      # additionally pytest and ruff
python bootstrap.py --clean    # remove .tools and .venv first
```

On Linux and macOS the command may be `python3`.

The bootstrap is repeatable and only adds what is missing or outdated. Dependencies are listed in `requirements.txt` (runtime) and `requirements-dev.txt` (development). The uv and Python versions are pinned at the top of `bootstrap.py`.

`.tools/` and `.venv/` contain platform-specific binaries. If the repository is synchronized between machines (for example with Syncthing), exclude both directories from synchronization and run the bootstrap on each machine.

## Repository layout

```
blackbook/
├── docs/
│   ├── features.md         patch builder, external editor, backup, organization
│   ├── card-format.md      structure of the microSD card and its XML files
│   └── architecture.md     application structure and write rules
├── src/
│   └── blackbook/          Python package (backend and served frontend)
├── tests/
│   └── fixtures/           own synthetic test cards (no factory content)
├── bootstrap.py            toolchain setup inside the repository
├── requirements.txt        runtime dependencies
├── requirements-dev.txt    development dependencies
├── LICENSE
├── pyproject.toml
└── README.md
```

## Test data

1010music factory content is not part of the repository. For local tests, the path to a card or a mirror is set via the environment variable `BLACKBOOK_CARD`. Local copies under `card/` or `testdata/` are excluded via `.gitignore`.

## Disclaimer

Unofficial project, not affiliated with 1010music LLC. Make a full backup of the card before the first write access.

## License

MIT, see [LICENSE](LICENSE).
