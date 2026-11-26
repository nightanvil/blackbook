# Kartenformat blackbox 2

Stand: Firmware 1.1, User Manual vom 10.10.2026, Factory Content RC1.

## Verzeichnisse

```
<Karte>/
├── bb2-stng.mml                     globale Einstellungen
├── Projects/
│   └── <Projektname>/
│       ├── project.xml              komplettes Projekt
│       ├── <Aufnahme>.wav           aufgenommene oder gepackte Samples
│       └── <Multisample-Set>/       je Multisample-Set ein Unterordner
├── Patches/                         Factory-Patches
│   ├── patchindex.xml               Tags für den Patch Browser
│   ├── OneShots/<Patch>/
│   ├── SampInst/<Patch>/
│   ├── Loops/<Patch>/
│   ├── Slicer/<Patch>/
│   └── Shredder/<Patch>/
└── UserPatches/                     eigene Patches, gleicher Aufbau wie Patches
    └── patchindex.xml
```

Jeder Patch-Ordner enthält `patch.xml` und alle WAVs, die der Patch nutzt. Zu jeder WAV kann eine `<name>.wav.pk` existieren. Das ist ein Waveform-Cache, der gefahrlos gelöscht werden kann und vom Gerät neu erzeugt wird.

Factory Content RC1: 5 Projekte, 146 Patches, 6805 WAVs, ca. 7,4 GB.

## Patch-Typen

| Ordner | Track-Typ in XML | Anzahl Factory |
|---|---|---|
| OneShots | `samtrack` | 30 |
| SampInst | `multisamtrack` | 82 |
| Loops | `looptrack` | 10 |
| Slicer | `slicertrack` | 14 |
| Shredder | `granslicertrack` | 10 |

Ein Projekt enthält zusätzlich einen `mastrack` (Master mit FX).

## Dateikodierung

| Datei | mit BOM | ohne BOM |
|---|---|---|
| `patchindex.xml` | 1 | 0 |
| `project.xml` | 1 | 4 |
| `patch.xml` | 68 | 78 |

Alle Dateien sind UTF-8 mit LF-Zeilenenden. Das Gerät liest beide Varianten, ein vorhandenes BOM ist daher beim Schreiben beizubehalten, ein fehlendes nicht zu ergänzen.

Pfadtrenner in allen XML-Dateien ist der Backslash, unabhängig vom Betriebssystem des Rechners.

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

- `path` ist relativ zur Kartenwurzel und zeigt auf den Patch-Ordner.
- Die Datei enthält viele Leerzeilen ohne Bedeutung.
- Tags im Factory Content: Atmosphere, Bass, Drum, Foley, Guitar, Keys, Lead, Orchestral, Organ, Pad, Percussion, SFX, Strings, Synth, Vocal.
- Ob das Gerät weitere, frei definierte Tags anzeigt, ist nicht dokumentiert.

## project.xml und patch.xml

Beide Dateien nutzen dasselbe Schema. Ein Patch entspricht einem einzelnen Track.

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

Elemente: `document`, `session`, `track`, `params`, `cell`, `sequence`, `seqevent`, `slices`, `slice`.

Cell-Typen (Auswahl): `saminst`, `samasst`, `loopinst`, `loopgroup`, `slicer`, `granslicer`, `noteseq`, `scene`, `sceneEntry`, FX wie `fxdelay`, `fxeq`, `compressor`.

### Sample-Verweise

Samples werden ausschliesslich über das Attribut `filename` in `<cell type="samasst"><params .../></cell>` referenziert.

| Datei | Form von `filename` | Beispiel |
|---|---|---|
| `patch.xml` | relativ zum Patch-Ordner | `Kick_EDM.wav` |
| `project.xml` | relativ zur Kartenwurzel | `Patches\OneShots\EDM Kit\Kick_EDM.wav` |
| `project.xml` | relativ zur Kartenwurzel mit führendem Backslash | `\Patches\Loops\Female Vocals 1\Bloom_Dm_90BPM_FemaleVocal.wav` |

Beide Formen in `project.xml` kommen im Factory Content vor und werden vom Gerät geladen.

### Längen und Positionen

`samstart`, `samlen`, `loopstart`, `loopend` und `<slice pos>` sind Angaben in Sample-Frames. Beispiel: `Chords_Junos_24_0_127.wav` hat 118461 Frames bei 44,1 kHz stereo, die zugehörige Cell hat `samlen="118461"`.

Diese Werte stehen auch in jeder `project.xml`, die das WAV nutzt. Eine Änderung der WAV-Länge betrifft damit alle referenzierenden Dateien.

### OneShot-Patches

Ein OneShot-Patch hat 16 Pads. Jedes Pad ist eine `saminst`-Cell mit `celldisppos` 0 bis 15, gefolgt von einer `samasst`-Cell mit dem WAV. Ein Pad ohne Sample hat keine `samasst`-Cell.

### Multisample-Patches

Jedes WAV ist eine `samasst`-Cell mit Key- und Velocity-Bereich:

```xml
<params filename="Chords_Junos_25_0_127.wav" rootnote="25"
        keyrangebottom="25" keyrangetop="25"
        velrangebottom="0" velrangetop="128" ... />
```

- Notennummern 0 bis 127 (MIDI).
- Obergrenze der Velocity ist im Factory Content 128, nicht 127.
- Das tiefste Sample reicht bis Note 0, das höchste bis Note 127.
- Factory-Dateinamen folgen dem Muster `<Name>_<Note>_<VelVon>_<VelBis>.wav`.

### WAV-Dateien im Factory Content

- PCM 24 Bit überwiegt, dazu 16 Bit.
- Samplerate 44,1 und 48 kHz, mono und stereo.
- 1269 Dateien haben einen `JUNK`-Chunk vor dem `fmt`-Chunk. WAVs sind daher chunkweise zu lesen, nicht über feste Header-Offsets.

### Parameterwerte

Parameter sind Ganzzahlen in geräteinternen Einheiten, zum Beispiel `gaindb="6800"`, `trkgain="-9200"`, `envsus="1000"`. Die Umrechnung in die am Gerät angezeigten Werte ist nicht dokumentiert.

### Abhängigkeiten beim Umbenennen

| Umbenannt wird | Anzupassen |
|---|---|
| WAV in einem Patch-Ordner | `patch.xml` des Patches, alle `project.xml` mit Verweis auf die Datei |
| WAV in einem Projektordner | `project.xml` des Projekts |
| Patch-Ordner | Eintrag in `patchindex.xml`, alle `project.xml` mit Verweisen in den Ordner |
| Projektordner | alle Verweise in der eigenen `project.xml`, die in den Projektordner zeigen |
| Track-Name | `cellname` im `params` des Tracks, keine Dateioperation |

## Verhalten des Geräts

- Rename WAV am Gerät benennt nur Dateien im Projektordner um. Liegt die Datei woanders, kopiert das Gerät sie unter neuem Namen in den Projektordner.
- Pack kopiert alle referenzierten WAVs und Patches in den Projektordner und schreibt die Verweise um.
- Clean löscht WAVs im Projektordner, auf die kein Verweis mehr existiert, auch unbenutzte Aufnahmen.
- Patches aus bento nutzen dasselbe Format, die Tags werden aber nicht übernommen.

## Offene Fragen

- Standardbenennung neuer Aufnahmen und Form ihrer Verweise in `project.xml`
- Form der Verweise nach Pack (vermutlich `Projects\<Projektname>\...`)
- Aufbau von `UserPatches/patchindex.xml` im Detail
- Toleranz des Geräts gegenüber geänderter Attributreihenfolge, Einrückung, Zeilenenden und fehlendem BOM
- Unterstützung frei definierter Tags
- Gross- und Kleinschreibung bei Pfaden (FAT32 und exFAT sind case-insensitive, Linux-Dateisysteme eines Spiegels nicht)
- Umrechnung der Parameterwerte in Anzeigewerte (dB, Prozent, Millisekunden)
- Unterstützte WAV-Formate über den Factory Content hinaus (32 Bit Float, 96 kHz)
- Verwendung von Cue-Markern im WAV durch das Gerät
- Maximale Länge von Datei- und Patch-Namen
