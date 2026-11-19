"""PDF-Prüfbericht aus befunde.json (oder dem gleichen Dict)."""
import datetime
import json
import os
import sys

from PIL import Image as PImage
from reportlab.lib import colors
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/", "/Library/Fonts/", "C:/Windows/Fonts/"]


def _fonts():
    for d in _FONT_DIRS:
        if os.path.exists(d + "DejaVuSans.ttf"):
            pdfmetrics.registerFont(TTFont("DV", d + "DejaVuSans.ttf"))
            pdfmetrics.registerFont(TTFont("DVB", d + "DejaVuSans-Bold.ttf"))
            addMapping("DV", 0, 0, "DV"); addMapping("DV", 1, 0, "DVB")
            return "DV", "DVB"
    return "Helvetica", "Helvetica-Bold"


COL = {"FEHLER": "#C62828", "WARNUNG": "#E08A00", "HINWEIS": "#555555", "OK": "#2E7D32", "RÜCKFRAGE": "#555555"}
ORDER = {"FEHLER": 0, "WARNUNG": 1, "RÜCKFRAGE": 2, "HINWEIS": 3, "OK": 4}


def build_report(data, out_pdf, extra=None):
    """extra: optionale Liste manueller Befunde je Datei: {"datei": ..., "stufe": ..., "titel": ..., "text": ..., "screen": ...}"""
    F, FB = _fonts()
    base = ParagraphStyle("b", fontName=F, fontSize=9, leading=12.5, spaceAfter=3)
    small = ParagraphStyle("s", parent=base, fontSize=7.8, leading=10, textColor=colors.HexColor("#444444"))
    h1 = ParagraphStyle("h1", parent=base, fontName=FB, fontSize=16, leading=20, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=base, fontName=FB, fontSize=12, leading=15, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#1F3B5A"))
    cell = ParagraphStyle("c", parent=base, fontSize=8, leading=10.3, spaceAfter=0)
    cellb = ParagraphStyle("cb", parent=cell, fontName=FB)

    def tag(s):
        return f'<font color="{COL.get(s, "#000")}"><b>{s}</b></font>'

    def esc(t):
        return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    extra = extra or data.get("manuell", [])
    files = data["dateien"]
    for e in extra:
        for r in files:
            if r["datei"] == e.get("datei"):
                r["befunde"].append(e)

    def counts(r):
        c = {k: 0 for k in COL}
        for b in r["befunde"]:
            c[b["stufe"]] = c.get(b["stufe"], 0) + 1
        return c

    nF = sum(counts(r)["FEHLER"] for r in files) + sum(1 for c in data.get("uebergreifend", []) if c[0] == "FEHLER")
    nW = sum(counts(r)["WARNUNG"] for r in files) + sum(1 for c in data.get("uebergreifend", []) if c[0] == "WARNUNG")
    urteil = "nicht druckfreigabefähig" if nF else ("druckfähig mit Hinweisen" if nW else "druckfähig")

    story = [Paragraph(f"Prüfbericht Druckdaten – Auftrag {esc(data['auftrag'])}" + (f" ({esc(data['titel'])})" if data.get("titel") else ""), h1),
             Paragraph(f"Prüfgrundlage: {esc(data['regeln'])}. Geprüft am {datetime.date.today():%d.%m.%Y}. "
                       f"{len(files)} Datei(en). Gesamturteil: <b>{urteil}</b> – {nF} Fehler, {nW} Warnungen.", base)]
    if data.get("notizen"):
        story.append(Paragraph("Auftragsnotiz: " + esc(data["notizen"]), small))
    if data.get("zusammenfassung"):
        story.append(Spacer(1, 4))
        for line in data["zusammenfassung"]:
            story.append(Paragraph("•&nbsp;&nbsp;" + esc(line), base))
    story.append(Paragraph("Farbauftrag gemessen an den gelieferten CMYK-Werten (ohne Farbumrechnung). Inhaltliche Richtigkeit liegt beim Auftraggeber.", small))
    story.append(Spacer(1, 6))

    rows = [["Datei", "Format / Seiten", "Fehler", "Warn.", "Wichtigster Befund"]]
    for r in files:
        c = counts(r)
        top = sorted(r["befunde"], key=lambda b: ORDER.get(b["stufe"], 9))
        tb = top[0] if top else {"stufe": "OK", "titel": "–"}
        m = r["mess"]
        rows.append([esc(r["datei"]), f"{m.get('format_mm', ('?', '?'))[0]} × {m.get('format_mm', ('?', '?'))[1]} mm, {m.get('seiten', '?')} S.",
                     str(c["FEHLER"]), str(c["WARNUNG"]), tag(tb["stufe"]) + " " + esc(tb["titel"])])
    t = Table([[Paragraph(x, cellb if i == 0 else cell) for x in row] for i, row in enumerate(rows)],
              colWidths=[50 * mm, 30 * mm, 15 * mm, 15 * mm, 60 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF3")),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B0B8C4")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)

    if data.get("uebergreifend"):
        story.append(Paragraph("Dateiübergreifend", h2))
        for s, ti, tx in data["uebergreifend"]:
            story.append(Paragraph(f"{tag(s)} <b>{esc(ti)}</b> – {esc(tx)}", base))

    for r in files:
        story += [PageBreak(), Paragraph(esc(r["datei"]), h2)]
        m = r["mess"]
        info = [f"Art: {m.get('art')}", f"Format {m.get('format_mm')[0]} × {m.get('format_mm')[1]} mm", f"{m.get('seiten')} Seite(n)"]
        if m.get("endformat_mm"):
            info.append(f"Endformat laut Auftrag {m['endformat_mm'][0]:g} × {m['endformat_mm'][1]:g} mm")
        elif m.get("trimbox_mm"):
            info.append(f"Endformat laut Datei {m['trimbox_mm'][0]} × {m['trimbox_mm'][1]} mm")
        if m.get("icc"):
            info.append("Profil: " + ", ".join(n for _, n in m["icc"]))
        story.append(Paragraph(esc(" · ".join(info)), small))
        shots = []
        for b in sorted(r["befunde"], key=lambda b: ORDER.get(b["stufe"], 9)):
            story.append(Paragraph(f"{tag(b['stufe'])} <b>{esc(b['titel'])}</b> – {esc(b['text'])}", base))
            if b.get("screen") and b["screen"] not in shots:
                shots.append(b["screen"])
        for s in r.get("screens", []):
            if s and s not in shots:
                shots.append(s)
        if r.get("vorschau") and not shots:
            shots.append(r["vorschau"])
        for s in shots:
            if not os.path.exists(s):
                continue
            w, h = PImage.open(s).size
            sc = min(165 * mm / w, 150 * mm / h)
            story.append(KeepTogether([Spacer(1, 4), Image(s, w * sc, h * sc), Paragraph(esc(os.path.basename(s)), small)]))

    def footer(c, d):
        c.saveState(); c.setFont(F, 7); c.setFillColor(colors.HexColor("#777777"))
        c.drawString(20 * mm, 10 * mm, f"Prüfbericht Druckdaten · Auftrag {data['auftrag']}")
        c.drawRightString(190 * mm, 10 * mm, f"Seite {d.page}"); c.restoreState()

    SimpleDocTemplate(out_pdf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                      title=f"Prüfbericht {data['auftrag']}").build(story, onFirstPage=footer, onLaterPages=footer)
    return out_pdf


if __name__ == "__main__":
    # python -m preflight.report befunde.json bericht.pdf  (z. B. nach manueller Ergänzung von "manuell"/"zusammenfassung")
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    print(build_report(d, sys.argv[2]))
