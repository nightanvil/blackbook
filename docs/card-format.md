# blackbox 2 card format

Based on firmware 1.1, user manual dated 2026-10-10, factory content RC1 and a card in use (exFAT, 128 GB) as of 2026-11-26.

## Directories

```
<card>/
├── bb2-stng.mml                     global settings
├── blackbox2.bin                    firmware file for updates
├── Projects/
│   ├── <project name>/
│   │   ├── project.xml              complete project
│   │   ├── RC000001.wav             recordings, numbered sequentially
│   │   ├── <name>.wav               renamed recordings and copied samples
│   │   └── <multisample set>/       one subfolder per multisample set
│   └── <project name> - autosave/   automatic backup, same structure
├── Samples/                         user-created sample library, arbitrary subfolders
├── Patches/                         factory patches
│   ├── patchindex.xml               tags for the patch browser
│   ├── OneShots/<patch>/
│   ├── SampInst/<patch>/
│   ├── Loops/<patch>/
│   ├── Slicer/<patch>/
│   └── Shredder/<patch>/
└── UserPatches/                     own patches, same structure as Patches
    ├── patchindex.xml
    └── <type>/<patch>/
        ├── patch.xml
        ├── preview.wav              audition file for the patch browser
        └── <sample>.wav
```

Every patch folder contains `patch.xml` and all WAVs the patch uses. Each WAV may have a matching `<name>.wav.pk`. This is a waveform cache that can be deleted safely; the device recreates it.

Factory content RC1: 5 projects, 146 patches, 6805 WAVs, about 7.4 GB.

Foreign entries on a card in use, ignored by blackbook: `.Trash-1000/` (trash folder of Linux file managers, occupies space on the card), `System Volume Information/` (Windows), files of other sampler formats such as `.nki`, `.exs`, `.kt3`, `.geist`.

## Patch types

| Folder | Track type in XML | Factory count |
|---|---|---|
| OneShots | `samtrack` | 30 |
| SampInst | `multisamtrack` | 82 |
| Loops | `looptrack` | 10 |
| Slicer | `slicertrack` | 14 |
| Shredder | `granslicertrack` | 10 |

A project additionally contains a `mastrack` (master with FX).

## File encoding

Factory content:

| File | with BOM | without BOM |
|---|---|---|
| `patchindex.xml` | 1 | 0 |
| `project.xml` | 1 | 4 |
| `patch.xml` | 68 | 78 |

All files are UTF-8 with LF line endings. The device reads both variants. Files written by the device itself: `project.xml`, `patch.xml` and `bb2-stng.mml` have a BOM, `UserPatches/patchindex.xml` has none.

The path separator in all XML files is the backslash, regardless of the computer's operating system.

## patchindex.xml

```xml
<patchmetadata version="1">
    <patch path="Patches\OneShots\EDM Kit">
        <tag>Drum</tag>
        <tag>Percussion</tag>
        <tag>Synth</tag>
    </patch>
</patchmetadata>
```

- `path` is relative to the card root and points to the patch folder, also in `UserPatches/patchindex.xml` (`UserPatches\Shredder\VOICE GLITCH`).
- A patch without tags has no entry.
- The file contains many meaningless blank lines.
- Tags in the factory content: Atmosphere, Bass, Drum, Foley, Guitar, Keys, Lead, Orchestral, Organ, Pad, Percussion, SFX, Strings, Synth, Vocal.
- Whether the device shows additional, user-defined tags is not documented.

## project.xml and patch.xml

Both files share the same schema. A patch corresponds to a single track.

```xml
<document>
    <session version="1">
        <track type="samtrack">
            <params cellname="Vinyl Kit 1" trkgain="-9200" ... />
            <cell type="saminst">
                <params gaindb="6800" ... />
            </cell>
            <cell type="samasst">
                <params filename="Patches\OneShots\Vinyl Kit 1\Kick Dark Hard_Vinyl1.wav"
                        samstart="0" samlen="19050" loopstart="0" loopend="19050" ... />
                <slices/>
            </cell>
        </track>
    </session>
</document>
```

Elements: `document`, `session`, `track`, `params`, `cell`, `sequence`, `seqevent`, `slices`, `slice`.

Cell types (selection): `saminst`, `samasst`, `loopinst`, `loopgroup`, `slicer`, `granslicer`, `noteseq`, `scene`, `sceneEntry`, FX such as `fxdelay`, `fxeq`, `compressor`.

### Sample references

Samples are referenced exclusively via the `filename` attribute in `<cell type="samasst"><params .../></cell>`.

| File | Form of `filename` | Example |
|---|---|---|
| `patch.xml` | relative to the patch folder | `Kick_EDM.wav` |
| `project.xml` | relative to the card root | `Patches\OneShots\EDM Kit\Kick_EDM.wav` |
| `project.xml` | relative to the card root with leading backslash | `\Patches\Loops\Female Vocals 1\Bloom_Dm_90BPM_FemaleVocal.wav` |
| `project.xml` | relative to the project folder | `.\RC000010.wav` |

References relative to the card root point into `Patches`, `UserPatches` or `Samples`. The device loads all forms.

An empty pad slot appears either without a `samasst` cell or as a `samasst` whose `filename` points to the folder (`UserPatches\OneShots\FIRST\`) with `samlen="0"`.

### Lengths and positions

`samstart`, `samlen`, `loopstart`, `loopend` and `<slice pos>` are given in sample frames. Example: `Chords_Junos_24_0_127.wav` has 118461 frames at 44.1 kHz stereo; the corresponding cell has `samlen="118461"`.

These values also appear in every `project.xml` that uses the WAV. A change of the WAV length therefore affects all referencing files.

### One-shot patches

A one-shot patch has 16 pads. Each pad is a `saminst` cell with `celldisppos` 0 to 15, followed by a `samasst` cell with the WAV.

The device shows the pads in two rows of eight. Pad 1 is bottom left, numbering continues to the right and then in the upper row:

| Row on the device | Pad numbers | `celldisppos` |
|---|---|---|
| top | 9 to 16 | 0 to 7 |
| bottom | 1 to 8 | 8 to 15 |

Factory patches store the cells in the order 8, 0, 9, 1, ..., 15, 7.

### Multisample patches

Each WAV is a `samasst` cell with a key and velocity range:

```xml
<params filename="Chords_Junos_25_0_127.wav" rootnote="25"
        keyrangebottom="25" keyrangetop="25"
        velrangebottom="0" velrangetop="128" ... />
```

- Note numbers 0 to 127 (MIDI).
- The velocity upper bound in the factory content is 128, not 127.
- The lowest sample reaches down to note 0, the highest up to note 127.
- Factory file names follow the pattern `<Name>_<Note>_<VelLow>_<VelHigh>.wav`.

### WAV files in the factory content

- Mostly PCM 24 bit, some 16 bit.
- Sample rates 44.1 and 48 kHz, mono and stereo.
- 1269 files have a `JUNK` chunk before the `fmt` chunk. WAVs must be parsed chunk by chunk, not via fixed header offsets.

### preview.wav

When saving a patch, the device creates a `preview.wav` in the patch folder: PCM 24 bit, 48 kHz, stereo, length depending on the patch (observed 1 to 16 seconds). The patch browser plays it when preview is enabled. Factory patches have no `preview.wav`.

### Parameter values

Parameters are integers in device-internal units, for example `gaindb="6800"`, `trkgain="-9200"`, `envsus="1000"`.

| Attribute | Unit | Verified |
|---|---|---|
| `gaindb` | thousandths of dB (`-6300` = -6.3 dB) | yes, compared with the device display |
| `pitch` | thousandths of semitones (`2230` = +2.23) | derived from files only |
| `dualfilcutoff` | tenths of percent, -1000 (low-pass closed) to 1000 (high-pass closed), 0 open | range from the manual |
| `res`, `overdrive`, `fx1send`, `fx2send` | tenths of percent, 0 to 1000 | range from the manual; `fx1send` as delay and `fx2send` as reverb is assumed |
| `panpos` | -1000 (left) to 1000 (right) | derived from files only |
| `envattack`, `envdecay`, `envsus`, `envrel`, `velamount`, `lfoamount`, `lforate` | tenths of percent, 0 to 1000 | range from the manual |
| `samtrigtype` | launch: 0 Trigger, 1 Gate, 2 Toggle | assumed from the manual order |
| `polymode` | 0 Mono, 1 Poly 2, 2 Poly 4, 3 Poly 6, 4 Poly 8, 5 Poly X | assumed from the manual order |
| `chokegrp` | 0 None, 1 to 4 groups A to D | 0 and 1 seen in files |
| `interpqual` | 0 Normal, 1 HighQ | assumed |
| `lfowave` | 0 Rev Saw to 8 Random in the manual order | assumed, 0 and 8 seen in files |
| `lfobeatsync`, `lfokeytrig` | beat sync and restart, 0 off, 1 on | assumed |
| `lforatebeatsync` | 0 = 8 bars to 14 = 1/64 in the manual order | assumed, 0 and 6 seen in files |
| `samstart`, `samlen` | playback start and length in frames (`samasst`) | yes |

The ranges and the assumed encodings are kept in `src/blackbook/padparams.py`.

### Dependencies when renaming

| Renamed item | Must be updated |
|---|---|
| WAV in a patch folder | `patch.xml` of the patch, every `project.xml` referencing the file |
| WAV in a project folder | `project.xml` of the project |
| Patch folder | entry in `patchindex.xml`, every `project.xml` referencing files in the folder |
| Project folder | all references in its own `project.xml` that point into the project folder |
| Track name | `cellname` in the track's `params`, no file operation |

## Device behavior

- Recordings are named `RC` plus a six-digit number (`RC000001.wav`) and stored in the project folder. The number continues per project, including across Save As.
- Save Patch copies all used WAVs into the patch folder, creates `preview.wav` and, if tags were chosen, writes an entry into `UserPatches/patchindex.xml`. The project keeps referencing the original WAVs.
- Projects can reference WAVs that do not exist on the card. Example: the factory project `0-Renew` references `Choir-Emul-73.wav` and higher, while the factory patch `Choir` on the card only holds 40 files.
- Next to a project, a folder `<project name> - autosave` is created with its own `project.xml` and its own copies of the recordings.
- `bb2-stng.mml` stores the last loaded project in the element `<preset name="...">`.
- Rename WAV on the device renames only files inside the project folder. If the file lives elsewhere, the device copies it under the new name into the project folder.
- Pack copies all referenced WAVs and patches into the project folder and rewrites the references.
- Clean deletes WAVs in the project folder that are no longer referenced, including unused recordings.
- Patches from bento use the same format, but tags are not carried over.

## Open questions

- Form of the references after Pack
- When the device writes an autosave and whether it prefers it when loading
- Whether `preview.wav` may be missing and whether an externally generated preview is accepted
- Tolerance of the device towards changed attribute order, indentation, line endings and a missing BOM
- Support for user-defined tags
- Case sensitivity of paths (FAT32 and exFAT are case-insensitive, Linux file systems of a mirror are not)
- Conversion of parameter values other than gain to display values
- Supported WAV formats beyond the factory content (32-bit float, 96 kHz)
- Use of cue markers in the WAV by the device
- Maximum length of file and patch names
