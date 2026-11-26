# blackbook

Werkzeug für die microSD-Karte des 1010music blackbox 2. Baut Patches am Rechner, bindet einen externen Audio-Editor ein, sichert die Karte versioniert und organisiert Projekte, Patches und Samples. Alle Verweise in `project.xml`, `patch.xml` und `patchindex.xml` bleiben dabei konsistent.

Status: Konzeptphase, noch kein lauffähiger Code.

## Funktionsumfang (geplant)

- Patch-Builder: OneShot-, Multisample-, Loop-, Slicer- und Shredder-Patches am Rechner erstellen und bearbeiten, inklusive Tags
- Externer Editor: WAVs in Reaper oder einem anderen Editor bearbeiten, Längen und Verweise werden automatisch nachgezogen
- Backup: inkrementelle Snapshots mit Deduplizierung, Diff zwischen beliebigen Ständen, Wiederherstellung bis auf Dateiebene
- Organisation: Bibliothek mit Vorhören, Tagging in Masse, Umbenennen inklusive Verweise, Batch-Rename, Prüfungen
- Sicherheit: Dry-Run mit Diff-Vorschau und Snapshot vor jedem Schreibvorgang

Details in [docs/funktionen.md](docs/funktionen.md).

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

## Einrichtung

Der Bootstrap legt die gesamte Toolchain im Repo an. Systemweit wird nichts installiert. Voraussetzung ist ein beliebiges Python ab 3.8 zum Starten des Bootstraps, auf allen Plattformen derselbe Befehl.

| Ordner | Inhalt |
|---|---|
| `.tools/uv/` | Paketmanager uv, als Release von GitHub geladen und per SHA-256 geprüft |
| `.tools/python/` | Python-Interpreter, von uv verwaltet |
| `.tools/cache/` | Download-Cache |
| `.venv/` | virtuelle Umgebung mit allen Abhängigkeiten |

```
python bootstrap.py            # Laufzeit-Abhängigkeiten
python bootstrap.py --dev      # zusätzlich pytest und ruff
python bootstrap.py --clean    # .tools und .venv vorher löschen
```

Unter Linux und macOS heisst der Befehl je nach System `python3`.

Der Bootstrap ist wiederholbar und ergänzt nur, was fehlt oder veraltet ist. Abhängigkeiten stehen in `requirements.txt` (Laufzeit) und `requirements-dev.txt` (Entwicklung). Versionen von uv und Python sind im Kopf von `bootstrap.py` festgelegt.

`.tools/` und `.venv/` enthalten plattformspezifische Binärdateien. Wird das Repo zwischen Rechnern synchronisiert (zum Beispiel per Syncthing), sind beide Ordner von der Synchronisation auszuschliessen und auf jedem Rechner einzeln per Bootstrap anzulegen.

## Verzeichnisstruktur

```
blackbook/
├── docs/
│   ├── funktionen.md       Patch-Builder, externer Editor, Backup, Organisation
│   ├── kartenformat.md     Aufbau der microSD-Karte und der XML-Dateien
│   └── architektur.md      Aufbau der Anwendung und Schreibregeln
├── src/
│   └── blackbook/          Python-Paket (Backend und ausgeliefertes Frontend)
├── tests/
│   └── fixtures/           eigene, synthetische Testkarten (keine Factory-Inhalte)
├── bootstrap.py            Einrichtung der Toolchain im Repo
├── requirements.txt        Laufzeit-Abhängigkeiten
├── requirements-dev.txt    Entwicklungs-Abhängigkeiten
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
