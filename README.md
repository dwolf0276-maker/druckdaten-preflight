# druckdaten-preflight

Automatische Druckdatenprüfung für Brettspiele (Leitfaden Media Gold) als **Claude-Code-Routine**,
ausgelöst per Klick auf einen **Make-Webhook**. Daten liegen in **Google Drive**.

```
Klick auf Link ──► Make (Webhook, Schlüssel prüfen) ──► POST /routines/{id}/fire ──► Claude-Routine
                                                                                    │
  Google Drive: 01_Eingang/<Auftrag>/  ──── lädt PDFs/ZIP ◄─────────────────────────┤
                02_Berichte/<Auftrag>/Pruefung_<Datum>/  ◄── Bericht + Screens ─────┘
```

## Inhalt
| Pfad | Zweck |
|---|---|
| `CLAUDE.md` | Arbeitsanweisung für die Routine (Ablauf, Bewertungsmaßstab) |
| `preflight/pdfcheck.py` | Messungen: Farbraum, Sonderfarben, Stanzlinien, Schwarzaufbau, Farbauftrag (Rohwerte), Bilder, Beschnitt, Kartenränder |
| `preflight/run.py` | prüft einen Auftragsordner → `befunde.json`, `Pruefbericht_<Nr>.pdf`, `screens/` |
| `preflight/report.py` | baut den PDF-Bericht (auch nach manueller Ergänzung neu) |
| `preflight/gdrive.py` | Drive-Zugriff per Dienstkonto (laden/hochladen) |
| `rules/mediagold.json` | Grenzwerte; weitere Druckereien als eigene Datei anlegen |

Lokal testen: `pip install -r requirements.txt && python -m preflight.run <ordner> <ausgabe>`

## Einrichtung (einmalig)

### 1. Google Drive
1. Ordner anlegen: `Druckdaten-Prüfung/01_Eingang` und `Druckdaten-Prüfung/02_Berichte`.
2. Je Auftrag einen Unterordner in `01_Eingang` anlegen, Name beginnt mit der Auftragsnummer, z. B. `287568_Feuerwehralltag`.
   PDFs oder ZIP hineinlegen, optional `auftrag.json` (Endformate, siehe `CLAUDE.md`).
3. Die Ordner-IDs notieren (stehen in der Adresszeile hinter `/folders/`).

### 2. Google-Dienstkonto (damit die Routine große PDFs direkt laden kann)
1. console.cloud.google.com → Projekt anlegen → „Google Drive API“ aktivieren.
2. „IAM & Verwaltung → Dienstkonten“ → Dienstkonto anlegen → Schlüssel → JSON herunterladen.
3. Den Ordner `Druckdaten-Prüfung` in Drive mit der E-Mail-Adresse des Dienstkontos teilen (**Bearbeiter**).

### 3. Routine anlegen (claude.ai/code/routines)
- **Repository:** dieses Repo.
- **Umgebung:** Netzwerkzugriff für `googleapis.com`, `oauth2.googleapis.com` und PyPI erlauben;
  Umgebungsvariablen `GDRIVE_SA_JSON` (Inhalt der JSON-Schlüsseldatei), `GDRIVE_EINGANG_ID`, `GDRIVE_BERICHTE_ID`.
- **Prompt:** siehe `docs/routine_prompt.md`.
- **Auslöser:** „Add another trigger → API → Generate token“. URL und Token notieren (Token wird nur einmal angezeigt).

### 4. Make-Szenario
Webhook → Filter (Schlüssel) → HTTP-POST an die Routine-URL → Bestätigungsseite. Details: `docs/make_szenario.md`.
Klick-Link: `https://hook.<region>.make.com/<id>?key=<schluessel>&auftrag=287568`
(ohne `auftrag` → alle neuen Aufträge).

## Grenzen
- Kein zertifizierter PDF/X-Preflight; maßgeblich bleibt die Prüfung der Druckerei.
- Endpunkt der Routine ist experimentell; max. 30 Auslösungen pro Stunde je Routine.
