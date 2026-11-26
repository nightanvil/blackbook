# Changelog

All notable changes to blackbook are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- New icon in the top bar, the help, the browser tab and the README.

### Documentation

- README: blackbook updates itself, stated at the top and in Updating. Windows is tested; macOS is not tested and needs feedback from Mac users.

## [0.1.3] - 2026-11-26

### Documentation

- Help: the Library section explains search, filters, tags, playback, editing and templates.

## [0.1.2] - 2026-11-26

### Changed

- blackbook starts right away, also without a card, and shows the address to open in the browser. A blackbox card that is connected later is picked up by itself.

### Fixed

- Installations from a ZIP show their version next to "blackbook" in the top bar and in the window title. Before, the place stayed empty because there is no git commit to show.

## [0.1.1] - 2026-11-26

### Changed

- The backup folder can no longer be inside the blackbook folder, where an update or a new installation could delete it. The folder picker refuses it, and the Backup tab warns about an existing backup there.
- Updates only replace files that changed, and replace them in one step, so a running start script is not disturbed.

### Documentation

- README and help explain why the backup must stay outside the blackbook folder.
- README: short roadmap table at the top.

## [0.1.0] - 2026-11-26

First public, very early version.

### Added

- Library of factory and user patches with type filter (One-shot, Multisample, Loop, Slicer, Shredder), tag filter and search by name or tag. User patches are listed first, each row shows source, name and type.
- Audition of samples and `preview.wav`.
- Tag editor for user patches, writes `UserPatches/patchindex.xml`.
- Patch builder for one-shot kits (16 pads) and multisample instruments by drag and drop, with key and velocity mapping from file names and a generated `preview.wav`.
- Editing of user patches in place. Only the settings the builder handles change; sequences, modulation and unknown parameters stay untouched. Pads the device never used get new cells.
- Any one-shot or multisample patch, also factory patches, as template for a new user patch.
- Drag and drop of WAV files and folders from the file manager.
- Project overview with missing references and unused WAVs.
- Backup of the card with git snapshots, history, diff and restore of files, folders or everything. Snapshots are taken when the card is connected and before and after blackbook writes; a change of `bb2-stng.mml` alone creates no snapshot.
- Welcome dialog on the first start with backup setup: suggested folder `blackbook-backup` in the documents folder, folder picker, initial snapshot.
- Start scripts `start.sh`, `start.bat` and `start.command`. The first start sets everything up inside the blackbook folder; Python is downloaded privately when missing. On Windows the official portable git (MinGit) is downloaded when git is missing, on Linux and macOS the start script offers the installation.
- Automatic detection of a mounted blackbox card.
- Update check against GitHub releases with in-place update and restart prompt.
- Dark and light theme, built-in help, Ko-fi and GitHub links, running version in the top bar with a restart hint after code changes.

[Unreleased]: https://github.com/nightanvil/blackbook/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/nightanvil/blackbook/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/nightanvil/blackbook/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/nightanvil/blackbook/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/nightanvil/blackbook/releases/tag/v0.1.0
