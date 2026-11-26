# Changelog

All notable changes to blackbook are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Waveform in the WAV tab of a one-shot pad: drag start and end of the part the pad plays.
- Audio editor: trim, delete, silence, fade in and out, reverse, gain and normalize with undo and redo, zoom down to single samples, playback of the selection. Snap to zero puts every edge on a zero crossing, so cuts do not click. The edited sample goes onto the pad and into the patch folder when the patch is saved; the original stays untouched.
- One-shot pad editor with all pad settings of the device in four tabs: Sound (level, pitch, filter, resonance, pan, overdrive, delay, reverb), Setup (reverse, launch, poly, choke group, interpolation), Env/LFO (ADSR, velocity, LFO shape, depth, rate, beat sync, restart) and WAV (start and length).
- Restart and stop buttons at the top right, so blackbook can be controlled without a terminal window. The version at the top left shows the process id (PID), and the red "restart needed" hint restarts blackbook when clicked.
- Eject button at the top right: writes everything to the card and ejects it through the operating system, so the blackbox can be unplugged or leave microSD mode safely.

### Changed

- Restoring from the backup asks in a blackbook dialog instead of a browser dialog.
- New icon in the top bar, the help, the browser tab and the README.

### Fixed

- After every change to the card, blackbook writes all cached data to the card, so removing it right after a save no longer leaves an empty patch.xml.
- A patch with an empty or damaged patch.xml shows an explanation instead of "Internal Server Error".

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
