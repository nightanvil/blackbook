# Changelog

All notable changes to blackbook are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Audio editor for samples on the card: **Edit** next to every sample in the patch list and in the new sample list of a project. **Save as new file** writes `<name>_edit.wav` next to the original (factory samples go to `Samples/Edited`). **Overwrite original** replaces the file and first lists every patch and project that uses it; start, length, loop and slice positions there move with the edit, as do cue and loop points inside the WAV. The `.wav.pk` cache file is deleted. Factory samples are never overwritten.
- Projects: click a project to see its tracks, sequences and samples. Play samples and open them in the audio editor.
- Step sequencer for one-shot tracks in projects: one row per pad, one column per step, eight sequence slots. Velocity, probability, offset and length per note; name, step length, step count (or Open), quant size and snap per sequence. Play loops the sequence with the pad sounds. Save to card writes only the changed sequences into project.xml.
- MIDI in and MIDI out channel per track in projects.
- Project list with search, sorting (name, last change, tempo) and filters (track type, autosave copies, missing samples). Each project shows its tracks as color bars with type icons.
- Pads tab in a project: edit the pads of a one-shot track right in the project with the pad editor and sample browser from Build. The pads are drawn compact there.
- Sequencer: drag notes sideways on a grid down to 10 ticks and up or down to another pad. With Snap off notes can sit up to half a step off the grid.
- Sequencer: the "Drag grid" for moving notes is remembered per project.
- Sequencer: the offset of a note is shown as on the device, -47 to +47, instead of in ticks.
- Sequencer: an LED per pad lights up in the track color when the pad plays. Click mutes the pad for listening, Ctrl+click solos it; nothing of it is saved.
- Euclidean generator per pad in the sequencer, opened with a small ring-of-dots icon.
- Sequencer: paint notes by dragging, remove them by dragging with the right mouse button. Velocity lane under the grid. Row tools on right-click (shift, copy, paste, clear, humanize, quantize) and sequence tools in a menu (copy, paste, clear, humanize, quantize). Space plays and stops. Metronome for listening with its own volume. Humanize per pad with an intensity from 1 to 10.
- Undo and redo for sequence and MIDI changes in a project: buttons next to Discard, Ctrl+Z and Ctrl+Shift+Z, up to 100 steps. Each pad has its own settings; opening the generator changes nothing until a value is changed or Apply is clicked. Presets for common patterns: 4/4, Offbeat, Backbeat, 8ths, 16ths, Tresillo, Cinquillo, Bossa, 7 in 16, Clear.
- Number fields can be changed by pressing and dragging up or down, with a vertical slider next to the field. Fields with few values move slower, so they do not jump.
- Double click on a field sets its default, a second double click brings back the previous value: sequence settings, note values, Euclid and pad parameters.
- Project cards show tempo, references and missing samples as icons in fixed columns.

### Changed

- Projects is the first tab, with the projects listed on the left. The tracks of a project look like the Tracks screen of the device: track colors, type icons, sample count, and a Config box with the MIDI channels.
- Library is now called Patches, as on the device.
- The top bar no longer lets the volume slider overlap the tabs in windows narrower than 1400 pixels.
- On very wide screens the UI keeps a width of 1680 pixels and sits in the middle. Pads and pad editor are at most 960 pixels wide, so the sound settings stay in two columns below the pads. The project detail is one centered column: header, tracks, tabs, sample browser, pads and pad editor share the same edges, with space between pads and pad editor.

### Fixed

- After an update or a restart the browser always loads the current page and scripts instead of an older cached copy.
- Sequencer playback picks up changes ahead of the playhead in the same pass instead of the next one.
- Switching to another project opens its Sequences tab.

- Tracks of a project are numbered as on the device. The order in project.xml differs from the track positions.

### Documentation

- Card format: encoding of sequences, events and MIDI channels as measured on the device.

## [0.2.0] - 2026-11-26

### Added

- One-shot pad editor with all pad settings of the device in four tabs: Sound (level, pitch, filter, resonance, pan, overdrive, delay, reverb), Setup (reverse, launch, poly, choke group, interpolation), Env/LFO (ADSR, velocity, LFO shape, depth, rate, beat sync, restart) and WAV (start and length).
- Audio editor: trim, delete, silence, fade in and out, reverse, gain and normalize with undo and redo, zoom down to single samples, playback of the selection. Snap to zero puts every edge on a zero crossing, so cuts do not click. The edited sample goes onto the pad and into the patch folder when the patch is saved; the original stays untouched.
- Waveform in the WAV tab of a one-shot pad: drag start and end of the part the pad plays.
- Pad preview: clicking a pad or its play button plays it with level, pitch, pan, reverse, start and length. Filter, resonance, overdrive, envelope, LFO and the effect sends are not emulated and are heard on the device only.
- Envelope and LFO graphics in the Env/LFO tab. The envelope times follow the device manual, the curve shape is an approximation.
- Pads: drag a pad onto another pad to move it, a filled pad swaps places. Copy, Paste and Clear as on the device (also Ctrl+C, Ctrl+V, Ctrl+X); Clear keeps the pad in the clipboard, Paste brings it back.
- Eject at the top right: writes everything to the card and ejects it through the operating system, so the blackbox can be unplugged or leave microSD mode safely.
- Restart and stop buttons at the top right, so blackbook can be controlled without a terminal window. The version at the top left shows the process id (PID), and the red "restart needed" hint restarts blackbook when clicked.
- Header: loop switch and volume slider for all playback. Card state and eject are icons: green connected, red not connected, grey ejected.
- Sample browser: play and stop button in every row, and a Preview switch to stop rows from playing when clicked.
- Pad editor and audio editor show the full path of the sample.
- Restoring a single WAV from the backup explains that only the file comes back and lists the patches and projects that use it, with a note when the length no longer fits.
- Backup events are collapsed, scrollable and filterable, so the snapshot history stays in view.
- The backup folder is locked to one running blackbook. A second instance, for example on another computer sharing the folder through sync, gets a clear message instead of writing to the same backup.

### Changed

- All one-shot pad settings are confirmed on the device; the ? marks are gone. New pads get `velscreentrig="100"` like pads saved on the device.
- The edit notice in the builder appears once when a patch is loaded: Keep editing, Save as new patch instead, or Discard and start empty. After a save the editing continues without asking again.
- Sliders run the full width without a box around them; number fields fit values like -24.00.
- The header adapts to narrow windows. Playback stops with the play buttons or Escape; the stop button in the header is gone.
- Starting a new build shows the sample browser at the top of the card.
- Restoring from the backup asks in a blackbook dialog instead of a browser dialog.
- New icon in the top bar, the help, the browser tab and the README.

### Fixed

- A pad whose file on the card is shorter than the patch expects (for example after restoring a WAV) no longer blocks saving: start and length are shortened to the file and blackbook says so.
- After every change to the card, blackbook writes all cached data to the card, so removing it right after a save no longer leaves an empty patch.xml.
- A patch with an empty or damaged patch.xml shows an explanation instead of "Internal Server Error".

### Documentation

- README: screenshots of the library, builder, pad editor and audio editor.
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

[Unreleased]: https://github.com/nightanvil/blackbook/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/nightanvil/blackbook/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/nightanvil/blackbook/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/nightanvil/blackbook/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/nightanvil/blackbook/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/nightanvil/blackbook/releases/tag/v0.1.0
