# Arbeitsstand Druckdaten-Prüfung

Stand: 20.11.2026 · Repo: `dwolf0276-maker/druckdaten-preflight` (Branch `main`)

## Ablauf in einem Satz
Druckdaten in Drive `01_Eingang/<Auftragsnr>_<Name>/` ablegen → Chrome-Schaltfläche „Druckdaten prüfen“
(Auftragsnr. eingeben) → Make startet die Claude-Routine → Routine holt Daten + Xentral-Auftrag, prüft,
legt Bericht + Screens in `02_Berichte/<Ordner>/Pruefung_<Datum>/` ab, Push-Nachricht.

## Bausteine
| Baustein | Wo | Zweck |
|---|---|---|
| Routine „Druckdatenprüfung MediaGolf“ (`trig_01MP1gZhEiNB6xpvq7PLuv9Q`) | claude.ai/code/routines | führt `CLAUDE.md` aus; API-Auslöser mit Token |
| Make „Druckdaten-Prüfung starten (Webhook → Claude-Routine)“ (ID 10196121) | Make, Team „My Team“ | Klick-Webhook → Schlüssel prüfen → Routine starten → Bestätigungsseite |
| Make „Druckdaten-Prüfung – Drive-Proxy“ (ID 10196457) | Make | Drive-Zugriff für die Routine (Liste, Ordner, Freigabe, Upload) über Verbindung „Google Drive connection hey.infigo“ |
| Make „Druckdaten-Prüfung – Auftragsdaten aus Xentral“ (ID 10200691) | Make | liefert den Xentral-Verkaufsauftrag (inkl. Positionen) per Auftragsnummer |
| Drive-Ordner `01_Eingang` / `02_Berichte` | Konto hey.infigo@gmail.com | IDs in `config/drive.json` |
| Chrome-Schaltfläche | Lesezeichen (Einrichtungsdatei `druckdaten-schaltflaeche.html`) | fragt Auftragsnr. ab, ruft den Start-Webhook auf |

## Geheimnisse – wo sie liegen (nicht ins Repo schreiben!)
- **Zugangsschlüssel der Webhooks** (`key`): Filter in allen drei Make-Szenarien, Umgebungsvariable
  `MAKE_PROXY_KEY` der Routine, Chrome-Lesezeichen.
- **Routine-Token** (`sk-ant-oat01-…`): nur im HTTP-Modul des Start-Szenarios.
- **Xentral-Token**: in den HTTP-Modulen des Xentral-Szenarios.

Schlüssel tauschen: in den drei Make-Filtern + `MAKE_PROXY_KEY` der Routine ändern, neue Schaltfläche verteilen.
Routine-Token tauschen: Routine bearbeiten → API → „Generate token“ → in Make eintragen (`Bearer ` davor).

## Prüfumfang
- Technisch (Skript `preflight/run.py`): Farbraum/RGB, Sonderfarben, Stanzlinien, Schwarzaufbau/Überdrucken,
  Farbauftrag an Rohwerten, Bildauflösung, Schriften, Beschnitt, Kartenränder, Inhalt im Rand.
- Spielbeschreibung (`preflight/spec.py`): Bestandteile vorhanden, Formate, 4/4 vs. 4/0, Kartenzahl, Geldwerte,
  Seitenzahl Anleitung, Schachtelteile, Passform Brett ↔ Schachtel, Material-Hinweise.
- Sichtprüfung durch Claude (`CLAUDE.md` Schritt 6): Endformat/Sicherheitsabstand, Rillungen, Stanzabstände,
  Anleitung ↔ Ausstattung, Schachtelmaße.

## Getestet / offen
- ✅ Prüfskripte und Bericht mit Aufträgen 285568 (Stromopoly) und 287568 (Feuerwehralltag) lokal getestet.
- ✅ Abgleich mit Spielbeschreibung mit Beispiel „Let's get rich“ getestet (Testdaten).
- ⏳ Erster echter Lauf über Schaltfläche → Make → Routine → Drive (Netzwerkzugriff der Routine, Drive-Proxy).
- ⏳ Xentral-Abruf mit echtem Auftrag (welches Feld die Spielbeschreibung enthält).
- ⏳ Upload-Grenze des Drive-Proxys (ca. 3,5 MB je Datei) im Echtbetrieb beobachten.

## Änderungsprotokoll
| Datum | Änderung |
|---|---|
| 19.11.2026 | Prüfskripte, Regeln Media Gold, Bericht, Routine, Make-Start-Szenario, Drive-Proxy, Chrome-Schaltfläche |
| 20.11.2026 | Abgleich mit Spielbeschreibung aus Xentral (Make-Szenario + `xentral.py` + `spec.py`) |

## So werden Anpassungen gemacht
1. Neuer Chat mit Claude: „Wir arbeiten an `dwolf0276-maker/druckdaten-preflight`“ + was geändert werden soll
   (bei Fehlprüfungen: Link zum Bericht bzw. zur Routine-Sitzung und die betroffene PDF).
2. Claude ändert Code/Regeln/`CLAUDE.md`, testet lokal mit Beispiel-PDFs, aktualisiert diese Datei
   (Änderungsprotokoll, Getestet/offen) und lädt alles auf `main` hoch.
3. Die Routine nutzt beim nächsten Lauf automatisch den neuen Stand – nichts weiter zu tun.
4. Make-Änderungen macht Claude direkt über die Make-Anbindung und trägt sie hier ein.
5. Rückgängig machen: jede Änderung ist ein Commit auf GitHub und kann zurückgesetzt werden.
