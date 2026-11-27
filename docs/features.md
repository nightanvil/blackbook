# Features

Core features of blackbook in order of priority.

## 1. Patch builder

Creates and edits patches on the computer. The result is a patch folder `UserPatches/<Type>/<Name>/` with `patch.xml`, the copied WAVs, a `preview.wav` and an entry in `UserPatches/patchindex.xml`.

### Workflow

1. Choose the patch type: one-shot, multisample, loop, slicer, shredder.
2. Assign WAVs via drag and drop from the file system or the sample browser.
3. Set parameters and audition samples.
4. Enter name and tags.
5. Review the result as file list and XML, then write.

Existing patches are opened from the Patches tab:

| Action | Available for | Result |
|---|---|---|
| Edit in builder | user patches | the patch is changed in place, a snapshot is taken before |
| Use as template | user and factory patches | a new user patch based on the original |

Editing changes only the attributes the builder handles: per pad the parameters listed in `src/blackbook/padparams.py` (level, pitch, filter, resonance, pan, overdrive, sends, reverse, launch, poly, choke group, interpolation, envelope, velocity, LFO), the playback window (`samstart`, `samlen`) and the sample; per zone key and velocity range. Sequences, modulation sources, envelopes, filters and parameters unknown to blackbook stay byte-identical. A pad whose sample is unchanged keeps its trim and loop points. WAV files are never deleted by an edit; replaced samples stay in the patch folder. Factory patches are never overwritten.

### Files from outside the browser

WAV files and folders can be dragged from the file manager into blackbook:

| Drop target | Result |
|---|---|
| pads or zone list of the builder | files are stored in the local inbox `.blackbook/inbox/` and used directly; saving the patch copies them into the patch folder |
| sample browser | files are imported into the folder shown in the browser, on the card or in the inbox; folders are imported with all WAVs they contain |

Imports onto the card are not possible into the card root and the factory `Patches` folder. A snapshot is taken before the first file is written. File names are adjusted to FAT32/exFAT rules, existing files with identical content are reused, other name collisions get a numeric suffix. Files that are not WAV are rejected.

Playback of samples and previews stops with a second click on the same sample, the Stop button in the header or the Escape key.

### Types

| Type | Builder layout |
|---|---|
| One-shot | grid of 16 pads, one WAV per pad with its own parameters (gain, pitch, pan, envelope, choke group, loop mode, reverse) |
| Multisample | automatic key and velocity mapping from file names, editable in a keyboard view |
| Loop | WAV with BPM, loop points and loop groups |
| Slicer | slice points from an even grid, transient detection or cue markers in the WAV |
| Shredder | WAV with granular parameters |

### Multisample mapping

Recognized file name patterns:

| Pattern | Example |
|---|---|
| `<Name>_<Note>_<VelLow>_<VelHigh>.wav` | `Chords_Junos_60_0_127.wav` |
| `<Name>_<NoteName>.wav` | `Piano_C3.wav`, `Piano_F#2.wav` |
| `<Name>_<Note>.wav` | `Bass_36.wav` |

Gaps between samples are filled by a selectable rule: extend upwards, extend downwards or split in the middle. The lowest sample reaches down to note 0, the highest up to note 127.

### Checks before writing

- WAV format: PCM, 16 or 24 bit, 44.1 or 48 kHz, mono or stereo
- file names without characters that FAT32 or exFAT reject
- `samlen`, `loopend` and slice positions within the sample length
- patch name unique within its type folder

## 2. Audio editor

blackbook has its own waveform view and editor for WAV files. No external program is needed.

### Pad preview

Clicking a pad plays it through Web Audio with level (`gaindb`), pitch, pan, reverse and the playback window (`samstart`, `samlen`). Filter, resonance, overdrive, envelope, LFO and the effect sends are not emulated: filter type, overdrive algorithm, envelope curve and LFO rate in Hz are unknown, and an inexact emulation would lead to wrong settings. The Env/LFO tab draws the envelope (attack up to about 9 s, decay and release up to about 38 s according to the manual, curve shape approximated) and the LFO shape with its depth.

### Waveform in the pad editor

The WAV tab of a one-shot pad shows the sample with the playback window. The white lines set `samstart` and `samlen`; the file is not changed. Start and length can also be typed in frames.

### Editing a sample

"Edit audio" opens the editor for the sample of the selected pad. "Edit" next to a sample in the detail of a patch in the Patches tab and in the sample list of a project opens it for a sample on the card.

| Operation | Effect |
|---|---|
| Trim to selection | keeps only the selection |
| Delete | removes the selection |
| Silence | replaces the selection with silence |
| Fade in, fade out | equal power fade over the selection |
| Reverse | selection or whole sample |
| Gain | level change in dB, selection or whole sample |
| Normalize | loudest peak to the given level in dB, selection or whole sample |

- Undo and redo up to 50 steps.
- Mouse wheel zooms around the pointer, Shift+wheel scrolls; at close zoom the single samples are drawn.
- Space plays the selection or from the cursor.
- **Snap to zero** (on by default): selection edges and the playback window land on the nearest zero crossing of the channel sum, so cuts and pad starts do not click.

### Saving

From the pad editor, "Use edited sample" writes the result as `<name>_edit.wav` into the local inbox (`.blackbook/inbox/edits/`) and puts it on the pad. Saving the patch copies it into the patch folder. The original file on the card is not changed. The edited file keeps bit depth, sample rate and channels of the original; samples outside the edited range are written back bit-identical.

From the Patches tab and from projects the editor writes to the card:

- **Save as new file** writes `<name>_edit.wav` (or `_edit_2` and so on) next to the original. Factory samples (below `Patches/`) go to `Samples/Edited/` instead. No patch or project changes.
- **Overwrite original** replaces the WAV in place. Before writing, blackbook lists every `patch.xml` and `project.xml` (autosave folders included) that references the file and what changes in each. Factory samples cannot be overwritten.

Overwriting keeps every chunk of the file except the audio byte-identical and in its order. Positions follow the edit: a frame behind a deleted part moves forward by the deleted length, a frame inside a deleted or trimmed part moves to the cut. This applies to

- `samstart`, `samlen`, `loopstart`, `loopend` and `<slice pos>` of every `samasst` cell that points to the file,
- cue points (`cue `) and loop points (`smpl`) inside the WAV.

If the part a pad played or a loop spanned is removed completely, the pad plays the whole sample and the loop spans the played part. Other attributes and cells stay byte-identical, line endings and the BOM of the XML files stay as they are. The cache file `<name>.wav.pk` is deleted; the blackbox rebuilds it. A snapshot is taken before and after the write if the backup is set up, and the previous versions of all changed files are copied to the local backup folder.

### Planned

- An external editor (Reaper, Audacity and others) via a configurable launch command, using the same reference update.

## 3. Backup with diff and delta

Versioned backups of the card in a local git repository outside the card. Git stores every file content once (deduplication), so a snapshot only adds what changed (delta). The repository has no remote.

### Backup folder

```
<backup folder>/
├── .git/                    history of all snapshots
├── .gitattributes           card files are stored byte-identical
├── blackbook-backup.toml    configuration
└── card/                    mirror of the backed up card paths at the latest snapshot
```

The folder is chosen in the Backup view or via `--backup-target`. The choice is stored in `.blackbook/settings.json` of the installation.

### Configuration

`blackbook-backup.toml` in the backup folder:

| Key | Default | Meaning |
|---|---|---|
| `include` | `Projects`, `UserPatches`, `Samples`, `Patches/patchindex.xml`, `bb2-stng.mml` | card paths that are backed up |
| `include_factory` | `false` | also back up the factory `Patches` folder (about 8 GB) |
| `exclude` | `*.pk`, `.Trash-*`, `System Volume Information`, ... | file and folder name patterns that are skipped |
| `snapshot_on_connect` | `true` | snapshot when the card is connected while blackbook runs |
| `snapshot_before_write` | `true` | snapshot before blackbook writes to the card |

The configuration is part of every snapshot.

### Snapshot

1. Included card files are compared with the mirror by size and modification time. Files with equal size and a time difference above 2 seconds (FAT32 resolution) are compared by SHA-256.
2. New and changed files are copied, files missing on the card are removed from the mirror.
3. A commit is created. Subject: reason and counts (`Card connected: 3 added, 1 modified, 0 deleted`). Body: changed files per project, patch or sample folder.

Triggers: button in the Backup view, `blackbook snapshot`, card connection, before every write of blackbook. A snapshot without changes creates no commit.

### History and diff

The Backup view lists all snapshots. A snapshot shows its changed files grouped by project, patch or sample folder with status added, modified or deleted. XML, `.mml` and `.toml` files show a line diff.

### Restore

| Scope | Action |
|---|---|
| file | restores the file from the snapshot; a deleted file from the snapshot before |
| folder (project, patch, sample folder) | "Restore state": folder as in the snapshot; "Restore before": folder as before the snapshot |
| everything | all backed up paths as in the snapshot |

Within the restored scope the card matches the snapshot exactly: files that do not exist in the snapshot are deleted. Before every restore a snapshot of the current state is created, after it a snapshot with the subject `Restore <scope> from <commit>`.

Restoring a single WAV brings back only the file. Before the restore blackbook lists every patch and project that references it (`src/blackbook/references.py`) and notes when the restored length is shorter than a `samlen` in those files. References are not adjusted; restoring the whole patch or project folder keeps them consistent. When a patch is loaded whose file is shorter than its `samlen`, the builder shortens start and length to the file and says so.

### Instance lock

`.git/blackbook-instance.json` in the backup folder holds host, process id and a heartbeat of the blackbook using the backup, renewed every minute and removed on exit. Another instance refuses snapshots and restores while the heartbeat is younger than 5 minutes. The file lives inside `.git`, so it is never part of a snapshot but is synchronized with the folder.

## 4. Projects

Projects is the first tab. The projects on the card are listed on the left as cards: name, the four tracks as small color bars with type icons, tempo, number of references, missing samples and when the project was last changed. Icons show tempo (metronome), sample references (waveform) and missing samples (red waveform) in fixed columns. Search finds projects by project or track name; the list can be sorted by name, last change or tempo and filtered by track type, autosave copies and missing samples. Clicking a project shows the number of WAVs in its folder, references, missing samples and unused files, and below:

- **Tracks** in the style of the Tracks screen of the device: four cards in the track colors of the device (cyan, orange, green, magenta by position), with name, an icon for the track type, the number of samples and sequences with notes. The cards follow the track position on the device (`celldisppos` of the track), not the order in the file. Instead of the level meters each card has a **Config** box with MIDI In and MIDI Out channel (None or 1 to 16); changing a channel writes `midiinchan` or `midioutchan` of that track. The bar below shows project name, tempo and swing.
Below the tracks three tabs show the selected track:

- **Sequences** of the selected track, the eight slots as tabs. For one-shot tracks a step editor shows one row per pad and one column per step. Settings per sequence: name, Step Len, Step Count (or Open), Quant Size and Snap. Per note: velocity, probability, offset and length in steps. The offset is shown as on the device, -47 to +47 with 10 ticks per unit (a step has 960 ticks); the file stores ticks. Quant Size on the device sets when a launched sequence starts and loops, it does not move notes. Notes sit on the step grid (Snap) plus their offset. The grid for dragging ("Drag grid") is remembered per project in the browser, like volume and loop in the header. Notes can be dragged sideways on a grid of a step, 1/2, 1/4, 1/8 step or freely in single offset units (10 ticks), and up or down to another pad. With Snap on a note sits up to 470 ticks (the range of the Offset knob) from its step, with Snap off up to half a step, as notes recorded on the device. Each pad row starts with an LED in the track color that lights up when the pad sounds during playback; it is shown only for pads with a sample. Clicking the LED mutes the pad for listening here (grey LED, name struck through), Ctrl+click plays only this pad (solo). Mute and solo are not written to the card. The button with the ring of dots next to it opens a Euclidean generator: hits, pattern length, rotation and velocity. Opening it changes nothing; the pattern replaces the notes of that pad as soon as a value is changed or Apply is clicked, and repeats over the whole sequence. Every pad has its own settings, which are remembered while blackbook runs. Presets set common patterns in one click: 4/4, Offbeat, Backbeat, 8ths, 16ths, Tresillo (3 in 8), Cinquillo (5 in 8), Bossa (5 in 16), 7 in 16 and Clear. The E buttons are drawn in the accent color, the one of the open generator filled. Sequences of other track types are shown with their number of notes, editing follows later.
- **Pads** of a one-shot track, with the pad grid, pad editor and sample browser of the builder. Samples on the card are referenced where they are (relative to the card root); samples from the inbox or a library are copied into the project folder and referenced as `.\name.wav`, like recordings. Only the `saminst` and `samasst` cells of changed pads change; the patches in Patches stay as they are.
- **Samples** of the project with playback and the audio editor.

### Number fields

Every number field can also be changed by pressing and dragging up or down. A vertical slider next to the field shows the value. The whole range takes 16 pixels per value, at least 120 and at most 400 pixels, so fields with few values do not jump; Shift moves five times finer. A click without dragging places the cursor for typing.

Double click on a field with a default (sequence settings, note values, Euclid, pad parameters) sets the default; a second double click brings back the value it had before.

### Playback

Play runs the sequence of a one-shot track in a loop through Web Audio. It schedules only the next 120 milliseconds from the current notes, so a note added or moved ahead of the playhead is heard in the same pass. It follows Step Len, Step Count, velocity, probability, offset and the pad's level, pitch, pan, reverse, start and length. Choke groups cut the other pads of the group. Swing delays every second step by (swing / 50 - 1) steps, an approximation of the device. The tempo field sets the tempo for playback only; the project tempo on the device does not change. Filter, envelope, LFO, effects and automation are not played.

### Saving

"Save to card" writes only the changed tracks: their MIDI channels, changed pads, the `<params>` of the changed `noteseq` cells and their `<sequence>` element. A sequence in an empty slot is added as a new `noteseq` cell after the existing ones. Unknown attributes of events, automation and everything else in the project stay byte-identical, as do line endings and the BOM. The autosave copy of the project (`<name> - autosave`) is not changed. A snapshot is taken before and after if the backup is set up.

Sequences are stored in the project. The device ignores sequences in a `patch.xml` when a patch is loaded onto an existing track, so blackbook edits them in projects only.

## 5. Organization

- patch list with filters, audition and waveform
- tags for single patches or in bulk
- renaming of WAVs, patches and projects including all references
- batch rename by naming scheme
- turn recordings from projects into user patches
- checks: broken references, orphaned WAVs, duplicates, storage usage
