# spezifikation.json – Soll-Daten aus der Spielbeschreibung

Quelle: Auftrag in Xentral (Positionstexte), geholt mit `python -m preflight.xentral <nr> <ordner>`.
Claude liest `xentral_auftrag.json` und schreibt daraus `spezifikation.json` in den Ausgabeordner.
Nur übernehmen, was im Auftrag steht – nichts ergänzen. Unklares in `"unklar"` notieren.

## Felder je Komponente
| Feld | Bedeutung |
|---|---|
| `id` | kurzer Schlüssel (`brett`, `schachtel`, `karten1`, `geld`, `anleitung`, …) |
| `typ` | `Spielbrett` · `Schachtel` · `Karten` · `Spielgeld` · `Anleitung` · `Stanzteile` · `Sonstiges` |
| `bezeichnung` | Text aus dem Auftrag |
| `druckdaten` | `false` für Teile ohne Druck (Holzfiguren, Würfel, Einleger Standard …) |
| `endformat_mm` | `[Breite, Höhe]` laut Auftrag (Karten 58×88 → `[58, 88]`) |
| `gefaltet_mm`, `faltungen` | Spielbrett: gefaltetes Maß und Anzahl Faltungen |
| `masse_mm`, `masse_sind` | Schachtel: `[B, T, H]`; `"innen"`/`"aussen"`/`"unbekannt"` |
| `teile` | Schachtel: z. B. `["Deckel", "Unterteil"]` (Stülpdeckel = 2 Teile) |
| `druck` | `"4/4"`, `"4/0"`, … (Lack separat in `veredelung`) |
| `seiten` | Anleitung: Seitenzahl |
| `karten_pro_deck`, `decks` | Karten |
| `werte`, `stueckzahlen`, `gesamtstueck` | Spielgeld: Werte und Stückelung |
| `papier` | `"gestrichen"`, `"ungestrichen"`, `"Karton"`, … plus Originaltext in `material` |
| `dateimuster` | optional: Teile des Dateinamens, die zu dieser Komponente gehören |

Weitere Felder: `"inhalt_ausstattung"` (alles, was die Anleitung erwähnen darf: Figuren, Würfel, Häuser …),
`"unklar"` (Liste von Fragen).

## Beispiel (Auftrag 286568 „Let's get rich“)
```json
{
 "auftrag": "286568", "quelle": "Xentral", "produkt": "Individuelles Spiel Let´s get rich",
 "komponenten": [
  {"id": "brett", "typ": "Spielbrett", "bezeichnung": "Spielbrett / Spielplan", "endformat_mm": [460, 460],
   "gefaltet_mm": [235, 235], "faltungen": 2, "druck": "4/4", "veredelung": "Dispersionslack",
   "material": "1,5 mm Graupappe, bezogen mit 115 gsm Leinenpapier", "papier": "Leinenpapier (strukturiert)"},
  {"id": "schachtel", "typ": "Schachtel", "bezeichnung": "Stülpdeckelkarton", "masse_mm": [235, 235, 52],
   "masse_sind": "unbekannt", "teile": ["Deckel", "Unterteil"], "druck": "4/0", "veredelung": "Dispersionslack",
   "material": "1,2 mm Graupappe, einseitig 115 gsm Leinenpapier", "papier": "Leinenpapier (strukturiert)"},
  {"id": "karten", "typ": "Karten", "bezeichnung": "Frage- und Eventkarten", "endformat_mm": [58, 88],
   "karten_pro_deck": 110, "decks": 1, "druck": "4/4", "veredelung": "Lack",
   "material": "270 gsm Quartettkarten-Karton", "papier": "Karton gestrichen"},
  {"id": "geld", "typ": "Spielgeld", "bezeichnung": "Spielgeld (170 Noten)", "endformat_mm": [100, 50], "druck": "4/4",
   "werte": [5, 10, 20, 50, 100, 500], "stueckzahlen": {"5": 20, "10": 20, "20": 30, "50": 30, "100": 40, "500": 30},
   "gesamtstueck": 170, "material": "80 gsm Offsetpapier", "papier": "ungestrichen"},
  {"id": "anleitung", "typ": "Anleitung", "bezeichnung": "Spielanleitung", "endformat_mm": [148, 210], "seiten": 4,
   "druck": "4/4", "material": "115 gsm Bilderdruck", "papier": "gestrichen", "hinweis": "DIN A4 gefalzt auf A5"},
  {"id": "holz", "typ": "Sonstiges", "bezeichnung": "Holzteile", "druckdaten": false}
 ],
 "inhalt_ausstattung": ["6 Halma-Kegel 12 × 24 mm", "2 Augenwürfel 16 mm", "30 Häuser", "10 Hotels",
                        "Spielgeld 5/10/20/50/100/500", "110 Frage- und Eventkarten"],
 "unklar": ["Sind 235 × 235 × 52 mm Innen- oder Außenmaß der Schachtel?"]
}
```
