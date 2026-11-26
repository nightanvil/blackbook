# Development

Technical details for running blackbook from the command line and working on the code. The user guide is in the [README](../README.md).

## Command line

```
.venv/bin/blackbook --card /run/media/<user>/BB2                # Linux
.venv\Scripts\blackbook --card E:\                              # Windows
.venv/bin/blackbook --card <card> --library ~/Samples/Drums     # additional sample folder
```

The browser opens at `http://127.0.0.1:8765/`. The card path can also be set via `BLACKBOOK_CARD`.

Snapshot without UI, for example from a script or cron job:

```
.venv/bin/blackbook snapshot --card <card> -m "After session"
```

| Option | Meaning |
|---|---|
| `--card` | mounted card or a mirror of it |
| `--library` | local sample folder shown in the builder's browser, repeatable; samples are copied into the patch |
| `--backup-target` | git backup folder, also selectable in the UI; default is the last chosen folder |
| `--backup-dir` | folder for copies of modified card files, default `backups/` in the repository |
| `--port` | port of the local server, default 8765 |
| `--no-browser` | do not open the browser |

### Write behavior

- New patches are created as new folders below `UserPatches/<type>/`. Existing folders are never overwritten.
- Every write is reviewed in a dialog first: target folder, copied files, warnings, generated `patch.xml`.
- Before `patchindex.xml` is modified, the original is copied to `backups/<session>/files/`. `backups/<session>/journal.json` lists every created folder and modified file.
- Factory patches and factory tags are read only.
- Gain is stored in thousandths of dB (verified on the device) and pitch in thousandths of semitones (derived from existing files).
- While the blackbox is not in microSD mode, the card is not available. The header shows the connection state; saving is disabled until the card is back. On reconnection the library reloads and, if configured, a snapshot captures the changes made on the device.

## Technology

- Backend: Python 3.12+, FastAPI
- Frontend: HTML and JavaScript without a build step, served by the backend
- Runs as a local server, used in the browser at `http://127.0.0.1`
- Works on the mounted card (blackbox 2 in microSD mode, card reader) or a local mirror of the card

## Setup

The start scripts `start.sh`, `start.command` and `start.bat` call `bootstrap.py --if-needed` and then start blackbook. `--if-needed` returns at once when `.venv` matches the pinned versions and requirement files.


The bootstrap installs the complete toolchain inside the repository. Nothing is installed system-wide. Running the bootstrap requires any Python 3.8 or newer; the command is the same on every platform. The backup requires `git` on the `PATH` (on Windows: Git for Windows).

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
├── src/blackbook/
│   ├── __main__.py         command line entry point
│   ├── server.py           FastAPI application and API
│   ├── card.py             reading patches, projects and sample folders
│   ├── cardpath.py         card references, case-insensitive path resolution, name rules
│   ├── patchindex.py       format-preserving patchindex.xml updates
│   ├── wav.py              RIFF chunk parser, audio reading, 24 bit writer
│   ├── mapping.py          multisample key and velocity mapping
│   ├── templates.py        patch.xml generation
│   ├── builder.py          change plans and writing of new patches
│   ├── backup.py           copies of modified files and journal
│   ├── snapshot.py         git backup: mirror, commits, diff, restore
│   ├── settings.py         local settings in .blackbook/settings.json
│   └── static/             browser UI (HTML, CSS, JavaScript)
├── tests/                  pytest suite with synthetic test cards (no factory content)
├── bootstrap.py            toolchain setup inside the repository
├── requirements.txt        runtime dependencies
├── requirements-dev.txt    development dependencies
├── LICENSE
├── pyproject.toml
└── README.md
```

## Test data

1010music factory content is not part of the repository. For local tests, the path to a card or a mirror is set via the environment variable `BLACKBOOK_CARD`. Local copies under `card/` or `testdata/` are excluded via `.gitignore`.
