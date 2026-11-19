"""Prüft alle PDFs eines Auftragsordners und erzeugt Bericht + Screens.

Aufruf:
    python -m preflight.run <eingangsordner> <ausgabeordner> [--rules rules/mediagold.json]

Optional im Eingangsordner: auftrag.json, z. B.
    {"auftrag": "287568", "titel": "Feuerwehralltag",
     "endformate": {"Game_Board": [470, 470], "Cards": [58, 88]},
     "notizen": "Brett kaschiert mit Umschlag"}
Die Schlüssel in "endformate" werden als Teilstring (ohne Groß-/Kleinschreibung) im Dateinamen gesucht.
"""
import argparse
import json
import os
import re
import sys
import zipfile

from . import pdfcheck
from .report import build_report


def collect_pdfs(folder, work):
    pdfs = []
    for root, _, files in os.walk(folder):
        for f in sorted(files):
            p = os.path.join(root, f)
            if f.lower().endswith(".zip"):
                dst = os.path.join(work, "_entpackt", os.path.splitext(f)[0])
                os.makedirs(dst, exist_ok=True)
                with zipfile.ZipFile(p) as z:
                    for m in z.namelist():
                        if m.lower().endswith(".pdf") and not m.startswith("__MACOSX"):
                            z.extract(m, dst)
                pdfs += collect_pdfs(dst, work)
            elif f.lower().endswith(".pdf"):
                pdfs.append(p)
    return pdfs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("eingang")
    ap.add_argument("ausgabe")
    ap.add_argument("--rules", default=os.path.join(os.path.dirname(__file__), "..", "rules", "mediagold.json"))
    a = ap.parse_args(argv)

    rules = json.load(open(a.rules, encoding="utf-8"))
    os.makedirs(a.ausgabe, exist_ok=True)
    shots = os.path.join(a.ausgabe, "screens")
    os.makedirs(shots, exist_ok=True)

    job = {}
    jf = os.path.join(a.eingang, "auftrag.json")
    if os.path.exists(jf):
        job = json.load(open(jf, encoding="utf-8"))
    auftrag = job.get("auftrag") or (re.search(r"\d{5,7}", os.path.basename(os.path.abspath(a.eingang))) or [None])[0] or os.path.basename(os.path.abspath(a.eingang))
    endf = {k.lower(): v for k, v in job.get("endformate", {}).items()}

    pdfs = [p for p in collect_pdfs(a.eingang, a.ausgabe) if "_bericht" not in p.lower()]
    if not pdfs:
        print("Keine PDF-Dateien gefunden.", file=sys.stderr)
        return 2
    results = []
    for p in pdfs:
        name = os.path.basename(p)
        ef = next((tuple(v) for k, v in endf.items() if k in name.lower()), None)
        tag = re.sub(r"^[0-9a-f]{8}-", "", os.path.splitext(name)[0])[:60]
        print(f"Prüfe {name} …", flush=True)
        results.append(pdfcheck.check_pdf(p, rules, shots, endformat=ef, tag=tag))

    # Dateiübergreifend: Karten Vorder-/Rückseite paarweise?
    cross = []
    cards = [r for r in results if r["mess"].get("art") == "Karten"]
    if cards:
        def stem(n):
            n = re.sub(r"^[0-9a-f]{8}-", "", n.lower())
            return re.sub(r"(front|back|face|reverse|vorderseite|rueckseite|rückseite)", "", n)
        groups = {}
        for r in cards:
            groups.setdefault(stem(r["datei"]), []).append(r)
        for g, rs in groups.items():
            sides = {r["mess"].get("seite") for r in rs}
            if "Rückseite" not in sides:
                cross.append(("FEHLER", "Rückseiten-Datei fehlt", f"Zu „{rs[0]['datei']}“ gibt es keine Rückseiten-Datei (Leitfaden: je Deck Vorder- und Rückseite)."))
            if "Vorderseite" not in sides and "Rückseite" in sides:
                cross.append(("FEHLER", "Vorderseiten-Datei fehlt", f"Zu „{rs[0]['datei']}“ gibt es keine Vorderseiten-Datei."))
            if len(rs) == 2 and rs[0]["mess"]["seiten"] != rs[1]["mess"]["seiten"] and min(r["mess"]["seiten"] for r in rs) > 1:
                cross.append(("WARNUNG", "Seitenzahl Vorder-/Rückseite unterschiedlich",
                              f"{rs[0]['datei']}: {rs[0]['mess']['seiten']} S., {rs[1]['datei']}: {rs[1]['mess']['seiten']} S."))

    data = {"auftrag": str(auftrag), "titel": job.get("titel", ""), "notizen": job.get("notizen", ""),
            "regeln": rules["name"], "dateien": results, "uebergreifend": cross}
    json.dump(data, open(os.path.join(a.ausgabe, "befunde.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    pdf = build_report(data, os.path.join(a.ausgabe, f"Pruefbericht_{auftrag}.pdf"))
    n_f = sum(b["stufe"] == "FEHLER" for r in results for b in r["befunde"]) + sum(c[0] == "FEHLER" for c in cross)
    n_w = sum(b["stufe"] == "WARNUNG" for r in results for b in r["befunde"]) + sum(c[0] == "WARNUNG" for c in cross)
    print(json.dumps({"auftrag": auftrag, "dateien": len(results), "fehler": n_f, "warnungen": n_w, "bericht": pdf}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
