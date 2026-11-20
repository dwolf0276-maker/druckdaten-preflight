"""Abgleich der Druckdaten mit der Spielbeschreibung (spezifikation.json).

Aufruf:
    python -m preflight.spec <spezifikation.json> <befunde.json>
Ergänzt befunde.json um "abgleich" (Tabelle Bestandteil | Soll | Ist | Status) und
gibt eine Kurzfassung aus. Danach Bericht neu bauen (python -m preflight.report …).
Schema der spezifikation.json: docs/spezifikation.md
"""
import json
import re
import sys

TOL = 0.8  # mm Toleranz für Formatvergleiche
STUFE_ORDER = {"FEHLER": 0, "RÜCKFRAGE": 1, "WARNUNG": 2, "HINWEIS": 3, "OK": 4}

TYP_KEYS = {
    "Spielbrett": ["brett", "board", "spielplan", "plan"],
    "Schachtel": ["box", "top", "deckel", "unterteil", "schachtel", "lid", "bottom"],
    "Karten": ["card", "karte", "deck", "face", "reverse"],
    "Spielgeld": ["geld", "money", "note", "schein", "banknote"],
    "Anleitung": ["anleitung", "regel", "rules", "manual", "instruction"],
    "Stanzteile": ["piece", "figur", "token", "marker", "plaett", "stanz"],
}


def _norm(name):
    return re.sub(r"^[0-9a-f]{8}-", "", name.lower())


def _fits(page, endf, bleed):
    """Passt Seitenformat zu Endformat (+Beschnitt)? Liefert (status, überstand_mm)."""
    pw, ph = page
    for ew, eh in ((endf[0], endf[1]), (endf[1], endf[0])):
        bx, by = (pw - ew) / 2, (ph - eh) / 2
        if abs(bx) <= TOL and abs(by) <= TOL:
            return "ohne_beschnitt", 0.0
        if bx >= bleed - TOL and by >= bleed - TOL and abs(bx - by) <= 1.5:
            return "ok", round(min(bx, by), 1)
    return "falsch", None


def _sides(r):
    return r["mess"].get("seite")


def assign(komps, dateien):
    """Ordnet jede Datei genau einem Bestandteil zu (Dateimuster > Typ-Schlüsselwörter > Art)."""
    zu = {k["id"]: [] for k in komps}
    rest = []
    for r in dateien:
        n = _norm(r["datei"])
        best = None
        for k in komps:
            if any(m.lower() in n for m in k.get("dateimuster", [])):
                best = k; break
        if not best:
            for k in komps:
                if any(w in n for w in TYP_KEYS.get(k["typ"], [])):
                    best = k; break
        if not best:
            for k in komps:
                if k["typ"] == r["mess"].get("art"):
                    best = k; break
        (zu[best["id"]] if best else rest).append(r)
    return zu, rest


def check(spec, befunde):
    rows = []

    def row(bt, soll, ist, stufe, text=""):
        rows.append({"bestandteil": bt, "soll": soll, "ist": ist, "stufe": stufe, "text": text})

    komps = [k for k in spec.get("komponenten", []) if k.get("druckdaten", True)]
    zu, rest = assign(komps, befunde["dateien"])
    bleed_default = 3.0

    for k in komps:
        name = k.get("bezeichnung") or k["typ"]
        files = zu[k["id"]]
        druck = (k.get("druck") or "").replace(" ", "")
        beidseitig = druck.startswith("4/4") or druck.startswith("1/1")
        if not files:
            row(name, "Druckdaten vorhanden", "keine Datei gefunden", "FEHLER",
                "Für diesen Bestandteil liegt keine Druckdatei im Auftragsordner.")
            continue
        flist = ", ".join(f["datei"][-60:] for f in files)

        # --- Format ---
        endf = k.get("endformat_mm")
        if endf and k["typ"] != "Schachtel":
            soll = f"{endf[0]:g} × {endf[1]:g} mm + {bleed_default:g} mm Beschnitt"
            groups = {}
            for f in files:
                pg = tuple(f["mess"]["format_mm"])
                st, ub = _fits(pg, endf, bleed_default)
                if k["typ"] == "Spielbrett" and st == "falsch":
                    ox, oy = (pg[0] - endf[0]) / 2, (pg[1] - endf[1]) / 2
                    if ox >= 3 - TOL and oy >= 3 - TOL and abs(ox - oy) <= 1.5:
                        st, ub = "ok", round(min(ox, oy), 1)
                ist = f"{pg[0]:g} × {pg[1]:g} mm"
                if st == "ok" and ub > 25:
                    key = ("RÜCKFRAGE", ist + f" (Überstand {ub:g} mm)",
                           "Sehr großer Überstand – ist ein Umschlag/Bezug gemeint? Endformat der Druckdatei mit der Druckerei abstimmen.")
                elif st == "ok":
                    key = ("OK", ist + f" (Überstand {ub:g} mm" + (", Umschlag" if ub > 5 else "") + ")", "")
                elif st == "ohne_beschnitt":
                    key = ("FEHLER", ist + " (= Endformat)", "Endformat passt, Beschnitt fehlt.")
                else:
                    key = ("FEHLER", ist, "Format passt nicht zur Spielbeschreibung.")
                groups.setdefault(key, []).append(f["datei"])
            for (stufe, ist, txt), fl in groups.items():
                anz = f"{len(fl)} Datei(en)" if len(fl) > 1 else fl[0][-55:]
                row(name, soll, ist + f" – {anz}", stufe, txt)

        # --- Seiten / Vorder- & Rückseite ---
        if k["typ"] == "Karten":
            fronts = [f for f in files if _sides(f) != "Rückseite"]
            backs = [f for f in files if _sides(f) == "Rückseite"]
            n_front = sum(f["mess"]["seiten"] for f in fronts)
            soll_n = (k.get("karten_pro_deck") or 0) * (k.get("decks") or 1)
            if soll_n:
                stufe = "OK" if n_front == soll_n else "FEHLER"
                row(name, f"{soll_n} Karten (Vorderseiten)", f"{n_front} Seiten in {len(fronts)} Datei(en)", stufe,
                    "" if stufe == "OK" else "Anzahl der Vorderseiten weicht von der bestellten Kartenzahl ab.")
            if beidseitig:
                if not backs:
                    row(name, f"Druck {druck}: Rückseiten-Datei", "fehlt", "FEHLER", "Beidseitiger Druck bestellt, aber keine Rückseiten-Datei.")
                else:
                    n_back = sum(f["mess"]["seiten"] for f in backs)
                    ok = n_back in (1, len(backs), n_front)
                    row(name, f"Druck {druck}: Rückseiten 1× je Deck oder {n_front}×", f"{n_back} Seiten in {len(backs)} Datei(en)",
                        "OK" if ok else "WARNUNG", "" if ok else "Rückseitenzahl passt weder zu „eine Rückseite“ noch zu den Vorderseiten.")
            elif backs:
                row(name, f"Druck {druck} (einseitig)", "Rückseiten-Datei vorhanden", "RÜCKFRAGE", "Einseitig bestellt, aber Rückseiten geliefert.")

        elif k["typ"] == "Spielgeld":
            werte = [str(w).replace(",00", "").replace(".00", "").replace("€", "").strip() for w in k.get("werte", [])]
            gefunden = {}
            for f in files:
                m = re.findall(r"(?<!\d)(\d{1,5})(?!\d)", re.sub(r"^\d{5,7}|[0-9a-f]{8}-", "", _norm(f["datei"])))
                for w in werte:
                    if w in m:
                        gefunden.setdefault(w, []).append(f)
            fehlend = [w for w in werte if w not in gefunden]
            row(name, f"{len(werte)} Werte: " + ", ".join(werte), "vorhanden: " + (", ".join(sorted(gefunden, key=lambda x: float(x))) or "–"),
                "OK" if not fehlend else "FEHLER", ("Es fehlen: " + ", ".join(fehlend)) if fehlend else "")
            if k.get("stueckzahlen"):
                summe = sum(int(v) for v in k["stueckzahlen"].values())
                if k.get("gesamtstueck") and summe != int(k["gesamtstueck"]):
                    row(name, f"Stückelung = {k['gesamtstueck']} Scheine", f"Summe Stückelung {summe}", "RÜCKFRAGE",
                        "Die Stückelung ergibt nicht die genannte Gesamtzahl.")
            if beidseitig:
                einseitig = [f["datei"] for f in files if f["mess"]["seiten"] < 2 and _sides(f) is None]
                if einseitig:
                    row(name, f"Druck {druck}: Vorder- + Rückseite je Wert", "nur 1 Seite: " + ", ".join(einseitig[:4]), "FEHLER")

        elif k["typ"] == "Anleitung":
            n = sum(f["mess"]["seiten"] for f in files)
            soll = k.get("seiten")
            if soll:
                row(name, f"{soll} Seiten", f"{n} Seiten", "OK" if n == soll else "FEHLER",
                    "" if n == soll else "Seitenzahl weicht von der Spielbeschreibung ab.")
            elif n % 4:
                row(name, "Seitenzahl durch 4 teilbar (gefalzt)", f"{n} Seiten", "WARNUNG")

        elif k["typ"] in ("Spielbrett", "Stanzteile") and beidseitig:
            n = sum(f["mess"]["seiten"] for f in files)
            has_back = n >= 2 or any(_sides(f) == "Rückseite" for f in files)
            row(name, f"Druck {druck}: Vorder- und Rückseite", f"{n} Seite(n) in {len(files)} Datei(en)",
                "OK" if has_back else "FEHLER", "" if has_back else "Beidseitiger Druck bestellt, Rückseite fehlt.")

        elif k["typ"] == "Schachtel":
            teile = k.get("teile") or []
            if len(teile) >= 2 and len(files) < len(teile):
                row(name, " + ".join(teile), f"{len(files)} Datei(en): {flist}", "FEHLER", "Nicht für jedes Schachtelteil liegt eine Datei vor.")
            elif teile:
                row(name, " + ".join(teile), f"{len(files)} Datei(en)", "OK", flist)
            if k.get("masse_mm"):
                row(name, "Maße " + " × ".join(f"{v:g}" for v in k["masse_mm"]) + " mm", "Sichtprüfung/Messung an der Stanzkontur",
                    "HINWEIS", "Grundfläche und Höhe an Rill-/Stanzlinien gemessen – siehe manuelle Befunde.")

        # --- Material ---
        papier = (k.get("papier") or "").lower()
        if "ungestrichen" in papier or "offset" in papier or "natur" in papier:
            tacs = [f["mess"].get("tac", {}).get("max", 0) for f in files]
            if tacs and max(tacs) > 280:
                row(name, "Ungestrichenes Papier: Farbauftrag ≤ ca. 280 % empfohlen", f"max. {max(tacs):.0f} %", "HINWEIS",
                    "Leitfaden erlaubt 300 %, auf ungestrichenem Papier besser reduzieren (Trocknung, Durchschlagen).")

    # --- Passform Brett ↔ Schachtel ---
    br = next((k for k in komps if k["typ"] == "Spielbrett" and k.get("gefaltet_mm")), None)
    sc = next((k for k in komps if k["typ"] == "Schachtel" and k.get("masse_mm")), None)
    if br and sc:
        g = sorted(br["gefaltet_mm"])[:2]
        s = sorted(sc["masse_mm"][:2])
        innen = sc.get("masse_sind") == "innen"
        luft = min(s[0] - g[0], s[1] - g[1])
        if innen:
            stufe = "OK" if luft >= 2 else ("WARNUNG" if luft >= 0 else "FEHLER")
            txt = f"Luft je Richtung {luft:.0f} mm (Innenmaß)."
        else:
            stufe = "RÜCKFRAGE" if luft < 6 else "OK"
            txt = (f"Schachtel {s[0]:g} × {s[1]:g} mm, gefaltetes Brett {g[0]:g} × {g[1]:g} mm. "
                   "Sind die Schachtelmaße Außenmaße, passt das Brett nicht (Pappstärke + Spiel). Innen- oder Außenmaß?") if luft < 6 else ""
        row("Passform Brett ↔ Schachtel", f"Brett gefaltet ≤ Innenmaß Schachtel", f"{g[0]:g} × {g[1]:g} in {s[0]:g} × {s[1]:g}", stufe, txt)

    if br and br.get("endformat_mm") and br.get("gefaltet_mm") and br.get("faltungen"):
        e, g = br["endformat_mm"], br["gefaltet_mm"]
        erw = [e[0] / 2, e[1] / 2] if int(br["faltungen"]) >= 2 else [e[0] / 2, e[1]]
        if max(abs(a - b) for a, b in zip(sorted(erw), sorted(g))) > 2:
            row(br.get("bezeichnung") or "Spielbrett", f"{e[0]:g} × {e[1]:g} mm, {br['faltungen']}× gefaltet",
                f"rechnerisch {erw[0]:g} × {erw[1]:g} mm, laut Beschreibung {g[0]:g} × {g[1]:g} mm", "HINWEIS",
                "Abweichung entsteht meist durch Fugen zwischen den Pappteilen/Umschlag – Endformat der Druckdatei mit der Druckerei abstimmen.")

    for r in rest:
        row("(nicht zugeordnet)", "–", r["datei"], "WARNUNG", "Datei passt zu keinem Bestandteil der Spielbeschreibung.")

    rows.sort(key=lambda x: STUFE_ORDER.get(x["stufe"], 9))
    return rows


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    spec = json.load(open(argv[0], encoding="utf-8"))
    bf = json.load(open(argv[1], encoding="utf-8"))
    rows = check(spec, bf)
    bf["abgleich"] = {"quelle": spec.get("quelle", "Spielbeschreibung"), "auftrag": spec.get("auftrag"),
                      "produkt": spec.get("produkt", ""), "zeilen": rows,
                      "ohne_druckdaten": [k.get("bezeichnung") for k in spec.get("komponenten", []) if not k.get("druckdaten", True)]}
    json.dump(bf, open(argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    for r in rows:
        print(f"{r['stufe']:<9} {r['bestandteil'][:28]:<28} Soll: {r['soll'][:45]:<45} Ist: {r['ist'][:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
