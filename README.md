# blackbook

Lokaler Organizer für die microSD-Karte des 1010music blackbox 2. Verwaltet Projekte, Patches und Samples, vergibt Tags und benennt Dateien um, wobei alle Verweise in `project.xml`, `patch.xml` und `patchindex.xml` konsistent bleiben.

Status: Konzeptphase, noch kein lauffähiger Code.

## Funktionsumfang (geplant)

- Bibliothek: Übersicht aller Projekte, Patches und Samples mit Filter, Vorhören und Wellenform
- Tagging: Tags für Patches einzeln oder in Masse setzen, schreibt `patchindex.xml`
- Umbenennen: WAVs, Patch-Ordner und Projekte umbenennen, inklusive aller abhängigen XML-Verweise
- Batch-Rename nach frei definierbarem Namensschema
- Recordings aus Projekten als UserPatch übernehmen
- Prüfungen: kaputte Verweise, verwaiste WAVs, Duplikate, Speicherverbrauch
- Sicherheit: Dry-Run mit Diff-Vorschau und Backup vor jedem Schreibvorgang

## Plattformen

| Plattform | Status |
|---|---|
| Linux | Zielplattform |
| Windows | Zielplattform |
| macOS | lauffähig vorgesehen, ohne Tests |

## Technik

- Backend: Python 3.12+, FastAPI
- Frontend: HTML und JavaScript ohne Build-Schritt, ausgeliefert vom Backend
- Start: lokaler Server, Bedienung im Browser unter `http://127.0.0.1`
- Arbeitsverzeichnis: gemountete Karte (blackbox 2 im microSD Mode, Kartenleser) oder ein lokaler Spiegel der Karte

## Verzeichnisstruktur

```
blackbook/
├── docs/
│   ├── kartenformat.md     Aufbau der microSD-Karte und der XML-Dateien
│   └── architektur.md      Aufbau der Anwendung und Schreibregeln
├── src/
│   └── blackbook/          Python-Paket (Backend und ausgeliefertes Frontend)
├── tests/
│   └── fixtures/           eigene, synthetische Testkarten (keine Factory-Inhalte)
├── LICENSE
├── pyproject.toml
└── README.md
```

## Testdaten

Factory-Content von 1010music ist nicht Bestandteil des Repos. Für lokale Tests wird der Pfad zu einer Karte oder einem Spiegel über die Umgebungsvariable `BLACKBOOK_CARD` angegeben. Lokale Kopien unter `card/` oder `testdata/` sind per `.gitignore` ausgeschlossen.

## Hinweis

Inoffizielles Projekt, nicht mit 1010music LLC verbunden. Vor dem ersten Schreibzugriff auf eine Karte ein vollständiges Backup anlegen.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
