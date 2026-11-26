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

Existing patches (factory and user) can be opened as a template and saved under a new name. Factory patches are never overwritten.

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

## 2. External audio editor

Opens a WAV from the library, a patch or a project in an external editor and applies the result automatically.

### Workflow

1. Action "Open in editor" on a WAV.
2. blackbook creates a snapshot of the original and starts the editor.
3. A file watcher detects the written WAV.
4. blackbook reads length and format again and updates all references to the WAV.
5. The matching `.wav.pk` is deleted; the device recreates it.

### Updates on changed length

All `samasst` entries in `patch.xml` and `project.xml` that point to the WAV are affected.

| Attribute | Rule |
|---|---|
| `samlen` | new length in frames |
| `samstart`, `loopstart`, `loopend` | value equal to the old length becomes the new length, otherwise clamped to the new length |
| `<slice pos>` | clamped to the new length, optionally replaced by the cue markers of the WAV |

Before writing, blackbook shows the affected files and changes.

### Reaper

For Reaper, blackbook generates a project file (`.rpp`) in a working directory:

- A working copy of the original WAV is placed in the working directory and inserted as an item.
- The render target is the original path on the card, with the format and sample rate of the original.
- Markers in the Reaper project are written as cue markers into the WAV and serve as slice points for the slicer.

A render in Reaper writes the WAV directly to its place, the file watcher handles the rest.

### Other editors

Any editor that edits WAVs destructively and saves in place (for example Audacity, Tenacity, ocenaudio) is integrated via a configurable launch command. The placeholder `{file}` stands for the path of the WAV.

## 3. Backup with diff and delta

Versioned backups of the card, stored outside the card, with comparison between any two states.

### Storage format

```
<backup directory>/
├── objects/
│   └── ab/cdef0123...       file content, named by SHA-256
└── snapshots/
    └── 2026-11-26T19-30-00.json
```

- Every file content is stored exactly once. A snapshot only stores content that is missing from the object store (delta).
- A snapshot is a manifest with path, size, modification time and hash of every file.
- `.wav.pk` files are excluded.
- Changed files are detected via size and modification time, and via hash in case of doubt. FAT32 stores modification times with a resolution of 2 seconds.

### Triggers

- manual
- automatic before every write by blackbook
- optional when a card is inserted

### Diff

Comparison between two snapshots or between a snapshot and the current card:

| Level | Content |
|---|---|
| Files | added, deleted, modified, moved (same hash, different path) |
| XML | text diff and structural diff: changed attributes per track and cell, changed tags |
| WAV | length, format, channels, optional waveform overlay |
| Summary | per project and patch: changes since the previous snapshot |

### Restore

- complete snapshot
- single project or patch including referenced WAVs
- single file

Before a restore, a snapshot of the current state is created automatically.

### Retention

Configurable rule, for example every snapshot of the last 7 days and one per week after that. Objects no longer referenced by any snapshot are removed during cleanup.

## 4. Organization

- library with filters, audition and waveform
- tags for single patches or in bulk
- renaming of WAVs, patches and projects including all references
- batch rename by naming scheme
- turn recordings from projects into user patches
- checks: broken references, orphaned WAVs, duplicates, storage usage
