# Architecture

## Components

| Component | Responsibility |
|---|---|
| Scanner | reads the card, builds an index of projects, patches, WAVs and references |
| Reference graph | maps which XML file points to which WAV and patch folder |
| Operations | rename, tag, move, delete as a change plan |
| Patch builder | generates `patch.xml` from built-in templates per patch type and the UI input |
| WAV module | reads WAV chunks (format, frames, cue markers), computes waveform data for the UI |
| Editor bridge | launches external editors, generates Reaper projects, watches for changed WAVs |
| Snapshot service | git backup of the card: mirror, commit, history, diff, restore, card connection watcher |
| Eject | flushes all writes and ejects the card through the operating system: `udisksctl` (fallback `gio`) on Linux, `diskutil` on macOS, volume lock, dismount and eject via the Windows API |
| Settings | local settings of the installation in `.blackbook/settings.json` |
| Writer | applies a change plan to the card |
| API | FastAPI endpoints for the frontend |
| Frontend | browser UI served by the backend |

## Change workflow

1. The operation produces a change plan: file operations and XML changes.
2. The frontend shows the plan as a diff (dry run).
3. After confirmation, the snapshot service commits the current card state, if a backup folder is configured.
4. The writer executes the plan and logs every step. After every write request the API calls `os.sync()`, so the data is on the card before the frontend reports success.
5. The scanner updates the index.

## XML write rules

- Changes target attribute values only, the rest of the file stays byte-identical.
- BOM, indentation, blank lines and line endings are preserved.
- Paths in XML always use the backslash.
- The existing form of a reference (with or without leading backslash, `.\` prefix) is preserved.

## patch.xml templates

The patch builder uses its own templates inside the package, one per patch type. Factory patches serve only as a reference for validation and are not shipped as templates. Generated files are UTF-8 with BOM and LF line endings, like the files written by the device. For every patch, the builder generates a `preview.wav` (24 bit, 48 kHz, stereo).

## Platforms

- File system paths are handled with `pathlib` internally; conversion to card paths with backslashes happens only at the XML boundary.
- Path comparisons are case-insensitive, matching FAT32 and exFAT.
- On Windows the card is addressed as a drive, on Linux and macOS via its mount point.
- Eject works only when the card path is the root of a separate drive (mount point or drive letter). A folder copy of a card is never ejected. udisks runs without user interaction, so blackbook never opens a password prompt.

## Security

- The server binds to `127.0.0.1` only.
- Nothing is written without explicit confirmation.
- Backups are stored outside the card; the backup folder must not be located on the card.
- The backup repository has no remote, nothing leaves the machine.
