# Funktionen

Kernfunktionen von blackbook in der Reihenfolge ihrer Priorität.

## 1. Patch-Builder

Erstellt und bearbeitet Patches am Rechner. Ergebnis ist ein Patch-Ordner unter `UserPatches/<Typ>/<Name>/` mit `patch.xml`, den kopierten WAVs und einem Eintrag in `UserPatches/patchindex.xml`.

### Ablauf

1. Patch-Typ wählen: OneShot, Multisample, Loop, Slicer, Shredder.
2. WAVs per Drag and Drop aus dem Dateisystem oder der Bibliothek zuweisen.
3. Parameter setzen, Samples vorhören.
4. Name und Tags vergeben.
5. Vorschau des Ergebnisses als Dateiliste und XML, dann Schreiben.

Bestehende Patches (Factory und User) lassen sich als Vorlage öffnen und unter neuem Namen speichern. Factory-Patches werden nie überschrieben.

### Typen

| Typ | Aufbau im Builder |
|---|---|
| OneShot | Raster mit 16 Pads, je Pad ein WAV und eigene Parameter (Gain, Pitch, Pan, Hüllkurve, Choke-Gruppe, Loop-Modus, Reverse) |
| Multisample | automatisches Key- und Velocity-Mapping aus Dateinamen, manuell korrigierbar in einer Tastatur-Ansicht |
| Loop | WAV mit BPM, Loop-Punkten und Loop-Gruppen |
| Slicer | Slice-Punkte aus gleichmässigem Raster, Transienten-Erkennung oder Cue-Markern im WAV |
| Shredder | WAV mit Granular-Parametern |

### Multisample-Mapping

Erkannte Dateinamenmuster:

| Muster | Beispiel |
|---|---|
| `<Name>_<Note>_<VelVon>_<VelBis>.wav` | `Chords_Junos_60_0_127.wav` |
| `<Name>_<Notenname>.wav` | `Piano_C3.wav`, `Piano_F#2.wav` |
| `<Name>_<Note>.wav` | `Bass_36.wav` |

Lücken zwischen Samples werden nach einer wählbaren Regel aufgefüllt: Bereich nach oben verlängern, nach unten verlängern oder in der Mitte teilen. Das tiefste Sample reicht bis Note 0, das höchste bis Note 127.

### Prüfungen vor dem Schreiben

- WAV-Format: PCM, 16 oder 24 Bit, 44,1 oder 48 kHz, mono oder stereo
- Dateinamen ohne Zeichen, die FAT32 oder exFAT nicht erlauben
- `samlen`, `loopend` und Slice-Positionen innerhalb der Sample-Länge
- Name des Patches eindeutig innerhalb des Typ-Ordners

## 2. Externer Audio-Editor

Öffnet ein WAV aus der Bibliothek, einem Patch oder einem Projekt in einem externen Editor und übernimmt das Ergebnis automatisch.

### Ablauf

1. Aktion "In Editor öffnen" auf einem WAV.
2. blackbook legt eine Sicherung des Originals an und startet den Editor.
3. Ein Dateiwächter erkennt das geschriebene WAV.
4. blackbook liest Länge und Format neu ein und passt alle Verweise an, die das WAV betreffen.
5. Die zugehörige `.wav.pk` wird gelöscht, das Gerät erzeugt sie neu.

### Anpassung bei geänderter Länge

Betroffen sind alle `samasst`-Einträge in `patch.xml` und `project.xml`, die auf das WAV zeigen.

| Attribut | Regel |
|---|---|
| `samlen` | neue Länge in Frames |
| `samstart`, `loopstart`, `loopend` | bei Wert gleich alter Länge auf neue Länge, sonst auf neue Länge begrenzt |
| `<slice pos>` | auf neue Länge begrenzt, wahlweise aus Cue-Markern des WAV neu gesetzt |

Vor dem Schreiben zeigt blackbook die betroffenen Dateien und Änderungen an.

### Reaper

Für Reaper erzeugt blackbook eine Projektdatei (`.rpp`) im Arbeitsverzeichnis:

- Das Original-WAV liegt als Arbeitskopie im Arbeitsverzeichnis und ist als Item eingebunden.
- Ziel des Renderns ist der Originalpfad auf der Karte, mit Format und Samplerate des Originals.
- Marker im Reaper-Projekt werden als Cue-Marker in das WAV geschrieben und dienen dem Slicer als Slice-Punkte.

Ein Render-Durchlauf in Reaper schreibt das WAV direkt an seinen Platz, der Dateiwächter übernimmt den Rest.

### Andere Editoren

Jeder Editor, der WAVs destruktiv bearbeitet und an Ort und Stelle speichert (zum Beispiel Audacity, Tenacity, ocenaudio), wird über einen konfigurierbaren Startbefehl eingebunden. Platzhalter `{file}` steht für den Pfad des WAV.

## 3. Backup mit Diff und Delta

Versionierte Sicherungen der Karte ausserhalb der Karte, mit Vergleich zwischen beliebigen Ständen.

### Speicherformat

```
<Backup-Verzeichnis>/
├── objects/
│   └── ab/cdef0123...       Dateiinhalt, benannt nach SHA-256
└── snapshots/
    └── 2026-11-26T19-30-00.json
```

- Jeder Dateiinhalt wird genau einmal gespeichert. Ein Snapshot speichert nur Inhalte, die im Objektspeicher noch fehlen (Delta).
- Ein Snapshot ist ein Manifest mit Pfad, Grösse, Änderungszeit und Hash jeder Datei.
- `.wav.pk` ist ausgeschlossen.
- Erkennung geänderter Dateien über Grösse und Änderungszeit, im Zweifel über den Hash. FAT32 speichert Änderungszeiten nur auf 2 Sekunden genau.

### Zeitpunkte

- manuell
- automatisch vor jedem Schreibvorgang von blackbook
- optional beim Erkennen einer eingesteckten Karte

### Diff

Vergleich zwischen zwei Snapshots oder zwischen Snapshot und aktueller Karte:

| Ebene | Inhalt |
|---|---|
| Dateien | hinzugefügt, gelöscht, geändert, verschoben (gleicher Hash, anderer Pfad) |
| XML | Textdiff und strukturierter Diff: geänderte Attribute je Track und Cell, geänderte Tags |
| WAV | Länge, Format, Kanäle, optional Wellenform-Überlagerung |
| Zusammenfassung | je Projekt und Patch: was sich seit dem letzten Snapshot geändert hat |

### Wiederherstellen

- ganzer Snapshot
- einzelnes Projekt oder einzelner Patch inklusive referenzierter WAVs
- einzelne Datei

Vor dem Wiederherstellen entsteht automatisch ein Snapshot des aktuellen Stands.

### Aufbewahrung

Konfigurierbare Regel, zum Beispiel alle Snapshots der letzten 7 Tage, danach einer pro Woche. Objekte ohne Verweis aus einem Snapshot werden beim Aufräumen entfernt.

## 4. Organisation

- Bibliothek mit Filter, Vorhören und Wellenform
- Tags einzeln oder in Masse setzen
- Umbenennen von WAVs, Patches und Projekten inklusive aller Verweise
- Batch-Rename nach Namensschema
- Recordings aus Projekten als UserPatch übernehmen
- Prüfungen: kaputte Verweise, verwaiste WAVs, Duplikate, Speicherverbrauch
