# Architektur

## Komponenten

| Komponente | Aufgabe |
|---|---|
| Scanner | liest die Karte ein, baut einen Index aus Projekten, Patches, WAVs und Verweisen |
| Referenzgraph | bildet ab, welche XML-Datei auf welche WAV und welchen Patch-Ordner zeigt |
| Operationen | Umbenennen, Taggen, Verschieben, Löschen als Änderungsplan |
| Writer | wendet einen Änderungsplan auf die Karte an |
| API | FastAPI-Endpunkte für das Frontend |
| Frontend | Browser-UI, wird vom Backend ausgeliefert |

## Ablauf einer Änderung

1. Die Operation erzeugt einen Änderungsplan: Dateioperationen und XML-Änderungen.
2. Das Frontend zeigt den Plan als Diff (Dry-Run).
3. Nach Bestätigung sichert der Writer alle betroffenen Dateien in ein Backup-Verzeichnis.
4. Der Writer führt den Plan aus und protokolliert jeden Schritt.
5. Der Scanner aktualisiert den Index.

## Schreibregeln für XML

- Änderungen erfolgen gezielt auf Attributwerten, die übrige Datei bleibt byte-identisch.
- BOM, Einrückung, Leerzeilen und Zeilenenden bleiben erhalten.
- Pfade in XML verwenden immer den Backslash.
- Die vorhandene Form eines Verweises (mit oder ohne führenden Backslash) bleibt erhalten.

## Plattformen

- Dateisystempfade intern über `pathlib`, Umwandlung in Karten-Pfade mit Backslash nur an der XML-Grenze.
- Pfadvergleiche case-insensitive, entsprechend FAT32 und exFAT.
- Unter Windows wird die Karte als Laufwerk angesprochen, unter Linux und macOS über den Mountpoint.

## Sicherheit

- Der Server bindet ausschliesslich an `127.0.0.1`.
- Ohne explizite Bestätigung wird nichts geschrieben.
- Backups liegen ausserhalb der Karte.
