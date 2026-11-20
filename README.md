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
| `preflight/xentral.py` | holt den Auftrag (Spielbeschreibung) aus Xentral über Make |
| `preflight/spec.py` | Abgleich Druckdaten ↔ Spielbeschreibung (Bestandteile, Formate, 4/4, Stückzahlen, Geldwerte, Passform) |
| `preflight/gdrive.py` | Drive-Zugriff über den Make-Drive-Proxy (laden/hochladen) |
| `docs/stand.md` | **Arbeitsstand, Bausteine, offene Punkte, Änderungsprotokoll – bei jeder Anpassung aktualisieren** |
| `rules/mediagold.json` | Grenzwerte; weitere Druckereien als eigene Datei anlegen |

Lokal testen: `pip install -r requirements.txt && python -m preflight.run <ordner> <ausgabe>`

## Einrichtung (einmalig)

### 1. Google Drive
1. Ordner anlegen: `Druckdaten-Prüfung/01_Eingang` und `Druckdaten-Prüfung/02_Berichte`.
2. Je Auftrag einen Unterordner in `01_Eingang` anlegen, Name beginnt mit der Auftragsnummer, z. B. `287568_Feuerwehralltag`.
   PDFs oder ZIP hineinlegen, optional `auftrag.json` (Endformate, siehe `CLAUDE.md`).
3. Die Ordner-IDs notieren (stehen in der Adresszeile hinter `/folders/`).

### 2. Drive-Zugriff über Make (kein Google-Dienstkonto)
Das Make-Szenario **„Druckdaten-Prüfung – Drive-Proxy“** (aktiv) nutzt die bestehende Make-Verbindung
„Google Drive connection hey.infigo“. Die Ordner `Druckdaten-Prüfung/01_Eingang` und `02_Berichte` müssen
in diesem Google-Konto liegen (oder mit ihm geteilt sein). Ordner-IDs in `config/drive.json` eintragen.
Große PDFs laufen nicht durch Make: Für den Download wird kurz eine Link-Freigabe gesetzt, die Datei direkt
von Google geladen und die Freigabe sofort wieder entfernt.

### 3. Routine anlegen (claude.ai/code/routines)
- **Repository:** dieses Repo.
- **Umgebung:** Netzwerkzugriff für `hook.eu2.make.com`, `drive.usercontent.google.com` und PyPI erlauben;
  Umgebungsvariable `MAKE_PROXY_KEY` (Zugangsschlüssel des Proxys).
- **Prompt:** siehe `docs/routine_prompt.md`.
- **Auslöser:** „Add another trigger → API → Generate token“. URL und Token notieren (Token wird nur einmal angezeigt).

### 4. Make-Szenario
Start: Webhook → Filter (Schlüssel) → HTTP-POST an die Routine-URL → Bestätigungsseite.
Drive-Proxy: Webhook → Router (API-Aufruf / Upload) → Antwort. Details: `docs/make_szenario.md`.
Klick-Link: `https://hook.<region>.make.com/<id>?key=<schluessel>&auftrag=287568`
(ohne `auftrag` → alle neuen Aufträge).

## Grenzen
- Kein zertifizierter PDF/X-Preflight; maßgeblich bleibt die Prüfung der Druckerei.
- Endpunkt der Routine ist experimentell; max. 30 Auslösungen pro Stunde je Routine.
