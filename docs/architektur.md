# Architektur

## Komponenten

| Komponente | Aufgabe |
|---|---|
| Scanner | liest die Karte ein, baut einen Index aus Projekten, Patches, WAVs und Verweisen |
| Referenzgraph | bildet ab, welche XML-Datei auf welche WAV und welchen Patch-Ordner zeigt |
| Operationen | Umbenennen, Taggen, Verschieben, Löschen als Änderungsplan |
| Patch-Builder | erzeugt `patch.xml` aus eigenen Vorlagen je Patch-Typ und den Eingaben im UI |
| WAV-Modul | liest WAV-Chunks (Format, Frames, Cue-Marker), berechnet Wellenform-Daten für das UI |
| Editor-Bridge | startet externe Editoren, erzeugt Reaper-Projekte, überwacht geänderte WAVs |
| Snapshot-Store | inhaltsadressierter Objektspeicher mit Manifesten, Diff und Wiederherstellung |
| Writer | wendet einen Änderungsplan auf die Karte an |
| API | FastAPI-Endpunkte für das Frontend |
| Frontend | Browser-UI, wird vom Backend ausgeliefert |

## Ablauf einer Änderung

1. Die Operation erzeugt einen Änderungsplan: Dateioperationen und XML-Änderungen.
2. Das Frontend zeigt den Plan als Diff (Dry-Run).
3. Nach Bestätigung legt der Snapshot-Store einen Snapshot der betroffenen Dateien an.
4. Der Writer führt den Plan aus und protokolliert jeden Schritt.
5. Der Scanner aktualisiert den Index.

## Schreibregeln für XML

- Änderungen erfolgen gezielt auf Attributwerten, die übrige Datei bleibt byte-identisch.
- BOM, Einrückung, Leerzeilen und Zeilenenden bleiben erhalten.
- Pfade in XML verwenden immer den Backslash.
- Die vorhandene Form eines Verweises (mit oder ohne führenden Backslash) bleibt erhalten.

## Vorlagen für patch.xml

Der Patch-Builder nutzt eigene Vorlagen im Paket, eine je Patch-Typ. Factory-Patches dienen nur als Referenz zur Prüfung, nicht als ausgelieferte Vorlage. Neu erzeugte Dateien haben UTF-8 mit BOM und LF-Zeilenenden, wie die vom Gerät geschriebenen Dateien. Zu jedem Patch erzeugt der Builder eine `preview.wav` (24 Bit, 48 kHz, stereo).

## Plattformen

- Dateisystempfade intern über `pathlib`, Umwandlung in Karten-Pfade mit Backslash nur an der XML-Grenze.
- Pfadvergleiche case-insensitive, entsprechend FAT32 und exFAT.
- Unter Windows wird die Karte als Laufwerk angesprochen, unter Linux und macOS über den Mountpoint.

## Sicherheit

- Der Server bindet ausschliesslich an `127.0.0.1`.
- Ohne explizite Bestätigung wird nichts geschrieben.
- Backups liegen ausserhalb der Karte.
