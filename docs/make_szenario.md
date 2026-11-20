# Make-Szenario „Druckdaten-Prüfung starten“

Angelegt in Make (Team „My Team“, eu2), Szenario-ID 10196121, Webhook „Druckdaten-Prüfung starten“.
Steht nach dem Anlegen auf **inaktiv**, bis URL und Token eingetragen sind.

## Ablauf
1. **Custom Webhook** – empfängt den Klick. Parameter in der Adresse:
   `key` (Zugangsschlüssel), `auftrag` (optional: Nummer oder Ordnername).
2. **Filter „Schlüssel korrekt“** – nur mit richtigem `key` geht es weiter.
3. **HTTP „Make a request“** – `POST https://api.anthropic.com/v1/claude_code/routines/<trig_…>/fire`
   Header: `Authorization: Bearer <Routine-Token>`, `anthropic-version: 2023-06-01`,
   `anthropic-beta: experimental-cc-routine-2026-04-01`; Body: `{"text": "Auftrag <auftrag|neu>"}`.
4. **Webhook response** – zeigt im Browser „Prüfung gestartet ✓“ mit Link zur laufenden Sitzung
   oder eine Fehlermeldung (401 Token falsch, 404 URL falsch, 429 zu viele Starts).

## Fertigstellen (einmalig)
1. Szenario in Make öffnen → Modul 2 (HTTP):
   - URL: `trig_HIER_EINTRAGEN` durch die Routine-URL aus claude.ai/code/routines ersetzen
   - Header `Authorization`: `TOKEN_HIER_EINTRAGEN` durch das Routine-Token ersetzen (`Bearer ` davor lassen)
2. Modul 1 → „Redetermine data structure“, dann den Klick-Link einmal aufrufen, damit Make `key`/`auftrag` kennt.
3. Szenario speichern und **aktivieren** („Immediately as data arrives“).

## Klick-Links
- Bestimmter Auftrag: `https://hook.eu2.make.com/1ajo05wo3ae0c0m6gc9re896r367q3rm?key=<SCHLÜSSEL>&auftrag=287568`
- Alle neuen Aufträge: `https://hook.eu2.make.com/1ajo05wo3ae0c0m6gc9re896r367q3rm?key=<SCHLÜSSEL>`

Den Schlüssel nicht weitergeben. Neuer Schlüssel: im Filter von Modul 2 ändern.
Jeder Klick startet eine neue Sitzung (keine Doppelklick-Sperre); max. 30 Starts/Stunde je Routine.


# Make-Szenario „Druckdaten-Prüfung – Drive-Proxy“ (ID 10196457, aktiv)
Webhook `https://hook.eu2.make.com/ph9ml11cxqvfmekwqbswjxosupp210s4` – wird nur von der Routine aufgerufen.
- `aktion=api`: Drive-API-Aufruf (nur Pfade unter `/v3/files`) mit der Make-Verbindung „Google Drive connection hey.infigo“,
  Antwort als JSON. Genutzt für: Ordner auflisten, Ordner anlegen, Link-Freigabe setzen/entfernen.
- `aktion=upload`: Datei (base64, max. ca. 3,5 MB) in einen Ordner hochladen (Bericht, Screens, befunde.json).
Gleicher Schlüssel wie beim Start-Szenario; Schlüssel als `MAKE_PROXY_KEY` in der Routine-Umgebung hinterlegen.

# Make-Szenario „Druckdaten-Prüfung – Auftragsdaten aus Xentral“ (ID 10200691, aktiv)
Webhook `https://hook.eu2.make.com/pbgddsxci73db5uwwwsjp59ebenjdwr2` – Aufruf durch die Routine mit
`{"key": …, "auftragsnummer": "286568"}`. Sucht den Verkaufsauftrag per `documentNumber` in Xentral, lädt die
Details (inkl. Positionen) und gibt sie komplett als JSON zurück; 404, wenn nicht gefunden.
