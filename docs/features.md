# Features

Core features of blackbook in order of priority.

## 1. Patch builder

Creates and edits patches on the computer. The result is a patch folder `UserPatches/<Type>/<Name>/` with `patch.xml`, the copied WAVs, a `preview.wav` and an entry in `UserPatches/patchindex.xml`.

### Workflow

1. Choose the patch type: one-shot, multisample, loop, slicer, shredder.
2. Assign WAVs via drag and drop from the file system or the library.
3. Set parameters and audition samples.
4. Enter name and tags.
5. Review the result as file list and XML, then write.

Existing patches are opened from the library:

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

### Waveform in the pad editor

The WAV tab of a one-shot pad shows the sample with the playback window. The white lines set `samstart` and `samlen`; the file is not changed. Start and length can also be typed in frames.

### Editing a sample

"Edit audio" opens the editor for the sample of the selected pad.

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

"Use edited sample" writes the result as `<name>_edit.wav` into the local inbox (`.blackbook/inbox/edits/`) and puts it on the pad. Saving the patch copies it into the patch folder. The original file on the card is not changed. The edited file keeps bit depth, sample rate and channels of the original; samples outside the edited range are written back bit-identical.

### Planned

- Editing samples from the library and from projects, with the choice to overwrite the original: blackbook then lists every patch and project using the file and adjusts `samlen`, `loopstart`, `loopend` and slice positions.
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

## 4. Organization

- library with filters, audition and waveform
- tags for single patches or in bulk
- renaming of WAVs, patches and projects including all references
- batch rename by naming scheme
- turn recordings from projects into user patches
- checks: broken references, orphaned WAVs, duplicates, storage usage
