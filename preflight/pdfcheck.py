"""Technische Druckdatenprüfung einer PDF-Datei.

Liefert eine Liste von Befunden (Fehler / Warnung / Hinweis / OK) plus Messwerte
und erzeugt Kontrollbilder (Screens). Alle Maße in mm.
"""
import collections
import os
import re

import fitz  # PyMuPDF
import numpy as np
import pikepdf
from PIL import Image

MM = 25.4 / 72  # pt -> mm
fitz.TOOLS.mupdf_display_errors(False)

FEHLER, WARNUNG, HINWEIS, OK = "FEHLER", "WARNUNG", "HINWEIS", "OK"


# --------------------------------------------------------------------------- #
# Farbraum-Hilfen
# --------------------------------------------------------------------------- #
def describe_cs(obj):
    try:
        if isinstance(obj, pikepdf.Name):
            return str(obj)[1:]
        if isinstance(obj, pikepdf.Array):
            t = str(obj[0])
            if t == "/ICCBased":
                return "ICC%d" % int(obj[1].N)
            if t == "/Separation":
                return "Sep:" + str(obj[1])[1:]
            if t == "/DeviceN":
                return "DeviceN:" + ",".join(str(x)[1:] for x in obj[1])
            if t == "/Indexed":
                return "Indexed(" + describe_cs(obj[1]) + ")"
            if t == "/Pattern":
                return "Pattern"
            if t in ("/Lab", "/CalRGB", "/CalGray"):
                return t[1:]
            return t[1:]
    except Exception:
        return "unbekannt"
    return str(obj)


def resolve_cs(name, res):
    if isinstance(name, pikepdf.Name):
        n = str(name)
        if n in ("/DeviceRGB", "/DeviceCMYK", "/DeviceGray", "/Pattern"):
            return n[1:]
        try:
            return describe_cs(res.ColorSpace[n])
        except Exception:
            return "unbekannt"
    return describe_cs(name)


def is_rgb(cs):
    return cs in ("DeviceRGB", "ICC3", "CalRGB", "Lab") or cs.startswith("Indexed(DeviceRGB") or cs.startswith("Indexed(ICC3")


class GState:
    __slots__ = ("fcs", "scs", "fc", "sc", "op", "OP", "lw", "scale")

    def __init__(self):
        self.fcs = self.scs = "DeviceGray"
        self.fc = self.sc = (0.0,)
        self.op = self.OP = False
        self.lw = 1.0
        self.scale = 1.0

    def copy(self):
        n = GState()
        for k in self.__slots__:
            setattr(n, k, getattr(self, k))
        return n


class Stats:
    def __init__(self):
        self.cs = collections.Counter()           # alle genutzten Farbräume
        self.text = collections.Counter()         # (cs, farbe, op)
        self.strokes = collections.Counter()      # (cs, farbe, OP)
        self.fills = collections.Counter()        # (cs, farbe, op)
        self.spot_use = collections.defaultdict(collections.Counter)  # name -> {fill/stroke/text: n}
        self.spot_op = collections.defaultdict(collections.Counter)   # name -> {op/noop}
        self.min_lw = 99.0
        self.thin_lines = 0
        self.transparency = collections.Counter()
        self.errors = []


def _cmyk_key(cs, col):
    return (cs, tuple(round(float(x), 3) for x in col))


def walk(stream_obj, res, st, gs=None, depth=0):
    if depth > 15:
        return
    gs = gs or GState()
    stack = []
    try:
        ops = pikepdf.parse_content_stream(stream_obj)
    except Exception as e:  # noqa
        st.errors.append(str(e))
        return
    for operands, op in ops:
        o = str(op)
        if o == "q":
            stack.append(gs.copy())
        elif o == "Q":
            if stack:
                gs = stack.pop()
        elif o == "cm":
            try:
                a, b, c, d = [float(x) for x in operands[:4]]
                gs.scale *= max(abs(a * d - b * c), 1e-12) ** 0.5
            except Exception:
                pass
        elif o == "w":
            gs.lw = float(operands[0])
        elif o == "cs":
            gs.fcs = resolve_cs(operands[0], res); st.cs[gs.fcs] += 1
        elif o == "CS":
            gs.scs = resolve_cs(operands[0], res); st.cs[gs.scs] += 1
        elif o == "rg":
            gs.fcs, gs.fc = "DeviceRGB", tuple(float(x) for x in operands); st.cs["DeviceRGB"] += 1
        elif o == "RG":
            gs.scs, gs.sc = "DeviceRGB", tuple(float(x) for x in operands); st.cs["DeviceRGB"] += 1
        elif o == "k":
            gs.fcs, gs.fc = "DeviceCMYK", tuple(float(x) for x in operands); st.cs["DeviceCMYK"] += 1
        elif o == "K":
            gs.scs, gs.sc = "DeviceCMYK", tuple(float(x) for x in operands); st.cs["DeviceCMYK"] += 1
        elif o == "g":
            gs.fcs, gs.fc = "DeviceGray", (float(operands[0]),); st.cs["DeviceGray"] += 1
        elif o == "G":
            gs.scs, gs.sc = "DeviceGray", (float(operands[0]),); st.cs["DeviceGray"] += 1
        elif o in ("sc", "scn"):
            gs.fc = tuple(float(x) for x in operands if not isinstance(x, pikepdf.Name))
            if operands and isinstance(operands[-1], pikepdf.Name):
                gs.fcs = "Pattern"
        elif o in ("SC", "SCN"):
            gs.sc = tuple(float(x) for x in operands if not isinstance(x, pikepdf.Name))
        elif o == "gs":
            try:
                g = res.ExtGState[str(operands[0])]
                if "/OP" in g:
                    gs.OP = bool(g.OP)
                    gs.op = bool(g.get("/op", g.OP))
                elif "/op" in g:
                    gs.op = bool(g.op)
                if "/SMask" in g and str(g.SMask) != "/None":
                    st.transparency["Maske"] += 1
                if "/ca" in g and float(g.ca) < 1:
                    st.transparency["Deckkraft<100%"] += 1
                if "/BM" in g and str(g.BM) not in ("/Normal", "/Compatible"):
                    st.transparency["Füllmethode " + str(g.BM)[1:]] += 1
            except Exception:
                pass
        elif o in ("Tj", "TJ", "'", '"'):
            st.text[_cmyk_key(gs.fcs, gs.fc) + (gs.op,)] += 1
            if gs.fcs.startswith("Sep:"):
                st.spot_use[gs.fcs[4:]]["Text"] += 1
                st.spot_op[gs.fcs[4:]]["op" if gs.op else "noop"] += 1
        elif o in ("S", "s", "B", "B*", "b", "b*"):
            lwmm = gs.lw * gs.scale * MM
            if 0 < lwmm < st.min_lw:
                st.min_lw = lwmm
            if 0 < lwmm < 0.1:
                st.thin_lines += 1
            st.strokes[_cmyk_key(gs.scs, gs.sc) + (gs.OP,)] += 1
            if gs.scs.startswith("Sep:"):
                st.spot_use[gs.scs[4:]]["Kontur"] += 1
                st.spot_op[gs.scs[4:]]["op" if gs.OP else "noop"] += 1
            if o in ("B", "B*", "b", "b*"):
                st.fills[_cmyk_key(gs.fcs, gs.fc) + (gs.op,)] += 1
        elif o in ("f", "F", "f*"):
            st.fills[_cmyk_key(gs.fcs, gs.fc) + (gs.op,)] += 1
            if gs.fcs.startswith("Sep:"):
                st.spot_use[gs.fcs[4:]]["Fläche"] += 1
                st.spot_op[gs.fcs[4:]]["op" if gs.op else "noop"] += 1
        elif o == "Do":
            try:
                x = res.XObject[str(operands[0])]
            except Exception:
                continue
            if x.get("/Subtype") == "/Form":
                walk(x, x.get("/Resources", res), st, gs.copy(), depth + 1)
            elif x.get("/Subtype") == "/Image":
                st.cs["Bild:" + describe_cs(x.get("/ColorSpace", pikepdf.Name("/DeviceGray")))] += 1
        elif o == "INLINE IMAGE":
            try:
                ii = operands[0]
                d = ii.obj if hasattr(ii, "obj") else {}
                cs = d.get("/CS", d.get("/ColorSpace", pikepdf.Name("/DeviceGray")))
                abbr = {"/RGB": "DeviceRGB", "/G": "DeviceGray", "/CMYK": "DeviceCMYK", "/I": "Indexed"}
                c = abbr.get(str(cs)) if isinstance(cs, pikepdf.Name) and str(cs) in abbr else resolve_cs(cs, res)
                st.cs["Inline-Bild:" + c] += 1
            except Exception:
                st.cs["Inline-Bild:unbekannt"] += 1
        elif o == "sh":
            try:
                st.cs["Verlauf:" + describe_cs(res.Shading[str(operands[0])].ColorSpace)] += 1
            except Exception:
                pass


def icc_profiles(pdf):
    names = set()
    for o in pdf.objects:
        try:
            if isinstance(o, pikepdf.Stream) and o.get("/N") in (1, 3, 4) and "/Subtype" not in o and "/Width" not in o:
                b = o.read_bytes()
                if b[36:40] != b"acsp":
                    continue
                n = int.from_bytes(b[128:132], "big")
                for i in range(n):
                    e = b[132 + 12 * i:144 + 12 * i]
                    if e[:4] == b"desc":
                        off, ln = int.from_bytes(e[4:8], "big"), int.from_bytes(e[8:12], "big")
                        d = b[off:off + ln]
                        if d[:4] == b"desc":
                            names.add((int(o.N), d[12:12 + int.from_bytes(d[8:12], "big") - 1].decode("latin1")))
                        elif d[:4] == b"mluc":
                            o2, l2 = int.from_bytes(d[20:24], "big"), int.from_bytes(d[24:28], "big")
                            names.add((int(o.N), d[o2:o2 + l2].decode("utf-16-be")))
        except Exception:
            continue
    return sorted(names)


# --------------------------------------------------------------------------- #
# Hauptprüfung
# --------------------------------------------------------------------------- #
def classify(path, page_w, page_h, n_pages, rules):
    name = os.path.basename(path).lower()
    maxedge = rules["playing_cards"]["max_card_edge_mm"]
    if re.search(r"card|karte|deck|face|reverse", name) and max(page_w, page_h) <= maxedge:
        return "Karten"
    if max(page_w, page_h) <= maxedge and n_pages >= 8:
        return "Karten"
    if re.search(r"box|top|deckel|unterteil|schachtel|lid", name):
        return "Schachtel"
    if re.search(r"board|brett|spielplan|plan", name):
        return "Spielbrett"
    if re.search(r"anleitung|rules|manual|regel", name):
        return "Anleitung"
    if re.search(r"piece|figur|token|marker|stanz|plaett", name):
        return "Stanzteile"
    return "Sonstiges"


def side_of(path):
    n = os.path.basename(path).lower()
    if re.search(r"back|reverse|rueck|rück|rs[_\-.]", n):
        return "Rückseite"
    if re.search(r"front|face|vorder|vs[_\-.]", n):
        return "Vorderseite"
    return None


def check_pdf(path, rules, shots_dir, endformat=None, tag=None):
    """endformat: (breite_mm, hoehe_mm) laut Auftrag oder None."""
    tag = tag or os.path.splitext(os.path.basename(path))[0]
    R = {"datei": os.path.basename(path), "tag": tag, "befunde": [], "screens": [], "mess": {}}

    def add(level, titel, text, screen=None):
        R["befunde"].append({"stufe": level, "titel": titel, "text": text, "screen": screen})

    try:
        pdf = pikepdf.open(path)
        doc = fitz.open(path)
    except Exception as e:
        add(FEHLER, "Datei nicht lesbar", f"Die PDF-Datei konnte nicht geöffnet werden ({e}).")
        return R

    p0 = doc[0]
    W, H = p0.rect.width * MM, p0.rect.height * MM
    trim = p0.trimbox
    tw, th = trim.width * MM, trim.height * MM
    trim_defined = abs(tw - W) > 0.2 or abs(th - H) > 0.2
    sizes = {(round(p.rect.width * MM, 1), round(p.rect.height * MM, 1)) for p in doc}
    kind = classify(path, W, H, len(doc), rules)
    R["mess"].update(dict(seiten=len(doc), format_mm=(round(W, 1), round(H, 1)), art=kind,
                          trimbox_mm=(round(tw, 1), round(th, 1)) if trim_defined else None,
                          seite=side_of(path), creator=doc.metadata.get("creator")))

    if len(sizes) > 1:
        add(WARNUNG, "Uneinheitliche Seitenformate", f"Die Datei enthält {len(sizes)} verschiedene Seitenformate: {sorted(sizes)}.")

    # ---------- Endformat / Beschnitt ----------
    bleed_req = rules["playing_cards"]["bleed_mm"] if kind == "Karten" else rules["bleed_mm"]
    if endformat:
        ew, eh = endformat
        bx, by = (W - ew) / 2, (H - eh) / 2
        R["mess"]["endformat_mm"] = (ew, eh)
        if min(bx, by) < bleed_req - 0.2:
            add(FEHLER, "Beschnitt fehlt/zu klein",
                f"Endformat {ew:g} × {eh:g} mm, Datei {W:.1f} × {H:.1f} mm → Beschnitt {max(0.0, min(bx, by)):.1f} mm (Soll {bleed_req:g} mm).")
        else:
            add(OK, "Beschnitt", f"Endformat {ew:g} × {eh:g} mm, Überstand je Seite {bx:.1f} × {by:.1f} mm.")
        if trim_defined and (abs(tw - ew) > 0.5 or abs(th - eh) > 0.5):
            add(WARNUNG, "Endformat in Datei weicht ab",
                f"In der Datei ist {tw:.1f} × {th:.1f} mm als Endformat (TrimBox) hinterlegt, Auftrag nennt {ew:g} × {eh:g} mm.")
    elif trim_defined:
        bl = min((W - tw) / 2, (H - th) / 2)
        lvl = OK if bl >= bleed_req - 0.2 else FEHLER
        add(lvl, "Beschnitt (aus Datei)", f"Endformat laut Datei {tw:.1f} × {th:.1f} mm, Beschnitt {bl:.1f} mm (Soll {bleed_req:g} mm).")
        ew, eh = tw, th
    else:
        ew = eh = None
        add(HINWEIS if kind in ("Schachtel", "Stanzteile") else WARNUNG, "Endformat nicht in der Datei hinterlegt",
            f"TrimBox = Seitengröße ({W:.1f} × {H:.1f} mm). Endformat muss der Druckerei separat genannt werden; "
            "Beschnitt kann nur geschätzt werden (siehe Randanalyse).")

    # ---------- Schriften ----------
    not_emb = set()
    for p in doc:
        for f in p.get_fonts():
            if f[1] in ("", "n/a") and f[2] != "Type3":
                not_emb.add(f[3])
    if not_emb:
        add(FEHLER, "Schriften nicht eingebettet", ", ".join(sorted(not_emb)))
    else:
        add(OK, "Schriften", "Alle Schriften eingebettet bzw. in Pfade umgewandelt.")

    # ---------- Inhalt analysieren ----------
    st = Stats()
    for page in pdf.pages:
        walk(page.obj, page.obj.get("/Resources"), st)
    iccs = icc_profiles(pdf)
    R["mess"]["icc"] = iccs
    R["mess"]["transparenz"] = dict(st.transparency)

    rgb = sorted({c for c in st.cs if is_rgb(c.split(":", 1)[-1])})
    if rgb:
        add(FEHLER, "RGB-Farben enthalten", "Gefundene Farbräume: " + ", ".join(rgb) +
            ". Laut Leitfaden nur CMYK. „Inline-Bild“ = kleines eingebettetes Bild direkt im Seiteninhalt (oft Schatten-/Effektreste aus Logos).")
    else:
        add(OK, "Farbraum", "Nur CMYK/Graustufen" + (f" (Profil: {', '.join(n for _, n in iccs)})" if iccs else "") + ".")

    # Sonderfarben
    hints = rules["dielines"]["spot_name_hints"]
    for spot, use in st.spot_use.items():
        low = spot.lower()
        if low in ("all", "none", "black", "cyan", "magenta", "yellow"):
            continue
        technical = any(h in low for h in hints)
        ops = st.spot_op[spot]
        if technical:
            if ops.get("noop"):
                add(FEHLER, f"Technische Farbe „{spot}“ nicht überdruckend",
                    f"{ops['noop']} Objekte in „{spot}“ stehen nicht auf Überdrucken → würden Druckfarben aussparen.")
            else:
                add(OK, f"Stanze/Technik „{spot}“", "Sonderfarbe, überdruckend (" + ", ".join(f"{k} {v}" for k, v in use.items()) + ").")
        elif "pantone" in low or "hks" in low:
            only_strokes = set(use) == {"Kontur"}
            add(FEHLER, f"Sonderfarbe „{spot}“",
                ("Nur als Linien verwendet – vermutlich Stanz-/Rilllinien unter Pantone-Namen. Wird als Druckfarbe interpretiert; "
                 "als „Stanze“/„Rillung“ benennen." if only_strokes else
                 "Wird als eigene Druckplatte ausgegeben. Falls kein Sonderfarbdruck beauftragt ist → in CMYK umwandeln.")
                + " Nutzung: " + ", ".join(f"{k} {v}" for k, v in use.items()))
        else:
            add(FEHLER, f"Sonderfarbe „{spot}“ ergibt zusätzliche Druckplatte",
                "Nutzung: " + ", ".join(f"{k} {v}" for k, v in use.items()) + ". Falls nicht als Sonderfarbe beauftragt → in CMYK umwandeln.")

    # Stanzkonturen in Prozessfarben (Heuristik): großflächige reine Konturpfade in Prozessfarbe
    has_technical = any(any(h in s.lower() for h in hints) for s in st.spot_use)
    die_candidates = find_process_dielines(doc) if kind in ("Schachtel", "Stanzteile", "Sonstiges") else []
    if die_candidates and not has_technical:
        add(FEHLER, "Stanz-/Hilfslinien vermutlich in Prozessfarben",
            "Lange, ungefüllte Konturpfade in Druckfarben gefunden (" + "; ".join(die_candidates[:4]) +
            "). Falls das Stanz-/Rilllinien sind: als Sonderfarbe „Stanze“ anlegen und auf Überdrucken stellen – sonst werden sie mitgedruckt.")
    elif die_candidates and has_technical:
        add(HINWEIS, "Weitere lange Konturlinien in Prozessfarbe",
            "Neben der Stanzfarbe gibt es lange Konturpfade in Druckfarben (" + "; ".join(die_candidates[:3]) + "). Bitte prüfen, ob Hilfslinien.")
    elif kind in ("Schachtel", "Stanzteile") and not has_technical:
        add(WARNUNG, "Keine Stanzkontur erkannt", "Für Schachteln/Stanzteile wurde keine Stanzfarbe gefunden.")

    # Schwarzer Text
    pure_noop = sum(v for (cs, col, op), v in st.text.items() if _is_pure_k(cs, col) and not op)
    rich_txt = {}
    for (cs, col, op), v in st.text.items():
        if len(col) == 4 and col[3] >= 0.9 and sum(col[:3]) > 0.05:
            rich_txt[_fmt_cmyk(col)] = rich_txt.get(_fmt_cmyk(col), 0) + v
    if rich_txt:
        add(FEHLER, "Schwarzer Text vierfarbig aufgebaut",
            "Text in " + ", ".join(f"{k} ({v}×)" for k, v in rich_txt.items()) + ". Leitfaden: reines K100, überdruckend.")
    if pure_noop:
        add(WARNUNG, "Schwarzer Text überdruckt nicht", f"{pure_noop} Textobjekte in K100 ohne Überdrucken.")
    k_fill_noop = sum(v for (cs, col, op), v in st.fills.items() if _is_pure_k(cs, col) and not op)
    if k_fill_noop and not st.text:
        add(HINWEIS, "Schwarz (K100) überdruckt nicht",
            f"{k_fill_noop} K100-Flächen ohne Überdrucken (Schrift ggf. in Pfade umgewandelt). Leitfaden verlangt bei Text Überdrucken.")

    # Vektor-Farbwerte > TAC
    tmax = rules["colour"]["tac_max_percent"]
    hi = collections.Counter()
    for D in (st.fills, st.strokes, st.text):
        for (cs, col, op), v in D.items():
            if len(col) == 4 and sum(col) * 100 > tmax + rules["colour"]["tac_tolerance_percent"]:
                hi[_fmt_cmyk(col)] += v
    R["mess"]["vektor_ueber_tac"] = dict(hi.most_common(6))

    if st.min_lw < rules["min_line_width_mm"]:
        add(WARNUNG, "Sehr dünne Linien", f"Dünnste Linie {st.min_lw:.3f} mm; {st.thin_lines} Linien unter 0,1 mm (Haarlinien können wegbrechen).")

    # ---------- Bilder ----------
    imgs = check_images(doc, rules)
    R["mess"]["bilder"] = imgs["n"]
    for lvl, txt in imgs["befunde"]:
        add(lvl, "Bildauflösung", txt)
    if not imgs["befunde"] and imgs["n"]:
        add(OK, "Bildauflösung", f"{imgs['n']} Bilder, alle ≥ {rules['images']['warn_below_ppi']} ppi effektiv.")

    # ---------- Farbauftrag (Rohwerte, ohne Farbumrechnung) + Randanalyse ----------
    tac = measure_tac(doc, rules, shots_dir, tag)
    R["mess"]["tac"] = tac
    per_page = tac["flaeche_mm2"] / max(1, len(tac["seiten"]))
    if per_page > rules["colour"]["tac_warn_min_area_mm2_per_page"]:
        txt = (f"Max. {tac['max']:.0f} %, Fläche über {tmax} %: {tac['flaeche_mm2']:.1f} mm² auf {len(tac['seiten'])} Seite(n)")
        if len(doc) > 1:
            txt += f" (Ø {tac['flaeche_mm2'] / max(1, len(tac['seiten'])):.1f} mm² je betroffene Seite)"
        if hi:
            txt += ". Häufigste Farbwerte über Grenze: " + ", ".join(list(hi)[:3])
        lvl = FEHLER if per_page > rules["colour"]["tac_error_min_area_mm2_per_page"] else WARNUNG
        add(lvl, f"Gesamtfarbauftrag über {tmax} %", txt + ("." if lvl == FEHLER else ". Kleine Fläche – Grenzfall, trotzdem korrigieren."), tac.get("screen"))
    else:
        add(OK, "Gesamtfarbauftrag", f"Max. {tac['max']:.0f} % (Grenze {tmax} %).")

    edge = analyse_edges(doc, rules, kind, ew, eh, W, H, shots_dir, tag)
    R["mess"]["rand"] = edge["mess"]
    for b in edge["befunde"]:
        add(*b)
    ov = overlay_trim(doc, ew, eh, W, H, kind, rules, shots_dir, tag) if ew else None
    R["screens"] = [s for s in [tac.get("screen")] + edge.get("screens", []) + [ov] if s]
    pv = os.path.join(shots_dir, f"{tag}_vorschau.png")
    z = min(1400 / p0.rect.width, 4)
    p0.get_pixmap(matrix=fitz.Matrix(z, z)).save(pv)
    R["vorschau"] = pv
    if st.transparency:
        add(HINWEIS, "Transparenzen", "Live-Transparenzen enthalten (" + ", ".join(f"{k} {v}" for k, v in st.transparency.items()) +
            "). Für moderne RIPs unkritisch; bei PDF/X-1a-Workflow vorher reduzieren.")
    if not iccs:
        add(HINWEIS, "Kein Farbprofil", "Kein ICC-Profil/OutputIntent enthalten – Druckbedingung mit der Druckerei abstimmen.")
    return R


def _is_pure_k(cs, col):
    return len(col) == 4 and col[3] >= 0.99 and sum(col[:3]) < 0.01


def _fmt_cmyk(col):
    return "C%d M%d Y%d K%d (%d %%)" % tuple([round(x * 100) for x in col] + [round(sum(col) * 100)])


def find_process_dielines(doc):
    """Sucht Farben, in denen ausschließlich lange, ungefüllte Linien über große Teile des Bogens laufen."""
    p = doc[0]
    Wp, Hp = p.rect.width, p.rect.height
    groups = collections.defaultdict(lambda: {"n": 0, "len": 0.0, "x0": 1e9, "y0": 1e9, "x1": -1e9, "y1": -1e9, "w": []})
    for d in p.get_drawings():
        if d.get("type") != "s" or not d.get("color") or d.get("fill"):
            continue
        w = (d.get("width") or 0) * MM
        if w < 0.1 or w > 1.2:
            continue
        L = 0.0
        for it in d["items"]:
            pts = [q for q in it[1:] if isinstance(q, fitz.Point)]
            if it[0] == "re":
                r = it[1]; L += 2 * (r.width + r.height)
            for a, b in zip(pts, pts[1:]):
                L += abs(b - a)
        g = groups[tuple(round(c * 5) / 5 for c in d["color"])]
        r = d["rect"]
        g["n"] += 1; g["len"] += L * MM; g["w"].append(w)
        g["x0"], g["y0"] = min(g["x0"], r.x0), min(g["y0"], r.y0)
        g["x1"], g["y1"] = max(g["x1"], r.x1), max(g["y1"], r.y1)
    out = []
    for c, g in groups.items():
        cov_w, cov_h = (g["x1"] - g["x0"]) / Wp, (g["y1"] - g["y0"]) / Hp
        if g["len"] > 250 and cov_w > 0.5 and cov_h > 0.5 and g["n"] >= 3:
            out.append(f"{g['n']} Linien, zusammen {g['len'] / 1000:.1f} m, Stärke {min(g['w']):.2f}–{max(g['w']):.2f} mm, "
                       f"über {cov_w * 100:.0f} × {cov_h * 100:.0f} % des Bogens (Vorschaufarbe RGB {c[0]:.2f}/{c[1]:.2f}/{c[2]:.2f})")
    return out


def check_images(doc, rules):
    res = {"n": 0, "befunde": []}
    low = []
    seen = set()
    for i, p in enumerate(doc):
        for im in p.get_image_info(xrefs=True):
            if not im.get("xref"):
                continue  # synthetische/innere Bilder (Masken, Effekte) – Farbraum wird über den Inhaltsstrom geprüft
            b = fitz.Rect(im["bbox"])
            area = b.width * b.height * MM * MM
            if area < rules["images"]["ignore_smaller_than_mm2"]:
                continue
            t = im["transform"]
            sx, sy = (t[0] ** 2 + t[1] ** 2) ** .5, (t[2] ** 2 + t[3] ** 2) ** .5
            if not sx or not sy:
                continue
            ppi = min(im["width"] / (sx / 72), im["height"] / (sy / 72))
            key = (im.get("xref"), round(ppi))
            if key in seen:
                continue
            seen.add(key)
            res["n"] += 1
            if ppi < rules["images"]["warn_below_ppi"]:
                low.append((ppi, i + 1, [round(v * MM) for v in b], im.get("colorspace")))
    for ppi, pg, bb, ncomp in sorted(low)[:10]:
        lvl = FEHLER if ppi < rules["images"]["error_below_ppi"] else WARNUNG
        if ncomp == 1:
            lvl = HINWEIS  # Graustufen meist Schatten/Effekte
        kind = {1: "Graustufen (oft Schatten/Effekt)", 3: "RGB", 4: "CMYK"}.get(ncomp, "")
        res["befunde"].append((lvl, f"Seite {pg}: Bild {kind} mit ca. {ppi:.0f} ppi effektiv, Position x {bb[0]}–{bb[2]} / y {bb[1]}–{bb[3]} mm."))
    return res


def measure_tac(doc, rules, shots_dir, tag):
    """Farbauftrag aus den gelieferten Werten (ICC-Umrechnung aus)."""
    fitz.TOOLS.set_aa_level(0)
    fitz.TOOLS.set_icc(False)
    big = doc[0].rect.width * MM > 300
    dpi = 72 if big else 200
    lim = rules["colour"]["tac_max_percent"] + rules["colour"]["tac_tolerance_percent"]
    mx, total, pages, worst = 0.0, 0.0, [], (0, -1)
    for i, p in enumerate(doc):
        pm = p.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), colorspace=fitz.csCMYK, alpha=False)
        t = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w, 4).astype(np.int32).sum(2) * (100 / 255)
        a = float((t > lim).sum()) * (25.4 / dpi) ** 2
        mx = max(mx, float(t.max()))
        if a > 0.2:
            total += a
            pages.append(i + 1)
            if a > worst[0]:
                worst = (a, i)
    fitz.TOOLS.set_icc(True)
    out = {"max": mx, "flaeche_mm2": total, "seiten": pages}
    if worst[1] >= 0 and total / max(1, len(pages)) > rules["colour"]["tac_warn_min_area_mm2_per_page"]:
        p = doc[worst[1]]
        z = min(1600 / p.rect.width, 6)
        fitz.TOOLS.set_icc(False)
        pm = p.get_pixmap(matrix=fitz.Matrix(z, z), colorspace=fitz.csCMYK, alpha=False)
        t = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w, 4).astype(np.int32).sum(2) * (100 / 255)
        fitz.TOOLS.set_icc(True)
        rgb = np.array(Image.frombytes("RGB", (pm.w, pm.h), p.get_pixmap(matrix=fitz.Matrix(z, z)).samples)).copy()
        rgb[t > lim] = [255, 0, 255]
        fn = os.path.join(shots_dir, f"{tag}_S{worst[1] + 1}_Farbauftrag_ueber_{rules['colour']['tac_max_percent']}.png")
        Image.fromarray(rgb).save(fn)
        out["screen"] = fn
    return out


def analyse_edges(doc, rules, kind, ew, eh, W, H, shots_dir, tag):
    """Ränder: wie weit liegt Farbe vom Seitenrand / vom Endformat entfernt?"""
    res = {"befunde": [], "mess": {}, "screens": []}
    dpi = 60 if W > 300 else 300
    k = 25.4 / dpi
    margins, edge_ink = [], []
    sample = range(len(doc)) if len(doc) <= 60 else list(range(0, len(doc), max(1, len(doc) // 60)))
    for i in sample:
        p = doc[i]
        pm = p.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), colorspace=fitz.csCMYK, alpha=False)
        a = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w, 4).astype(np.int32).sum(2) > 12
        e = max(1, int(1 / k))
        ring = np.concatenate([a[:e].ravel(), a[-e:].ravel(), a[:, :e].ravel(), a[:, -e:].ravel()])
        edge_ink.append(float(ring.mean()))
        ys, xs = np.nonzero(a)
        if len(xs):
            margins.append((i + 1, xs.min() * k, ys.min() * k, W - (xs.max() + 1) * k, H - (ys.max() + 1) * k))
    if not margins:
        return res
    ink_at_edge = np.mean(edge_ink) > 0.3
    res["mess"]["farbe_am_rand_anteil"] = round(float(np.mean(edge_ink)), 2)
    m_all = np.array([m[1:] for m in margins])
    typical = np.median(m_all, axis=0)
    res["mess"]["typischer_weissrand_mm"] = [round(float(x), 1) for x in typical]

    if kind == "Karten":
        safety = rules["playing_cards"]["safety_mm_white_border"]
        if not ink_at_edge and min(typical) > 1:
            # weißer Rand um die Karte
            if ew is None:
                res["befunde"].append((FEHLER, "Karten ohne Beschnitt",
                                       f"Datei {W:.1f} × {H:.1f} mm mit weißem Rand ca. {min(typical):.1f}–{max(typical):.1f} mm → offenbar Endformat ohne Beschnitt. "
                                       f"Leitfaden: {rules['playing_cards']['bleed_mm']:g} mm Beschnitt auch bei weißem Rand."))
                inner = typical
            elif abs(ew - W) < 0.3 and abs(eh - H) < 0.3:
                inner = typical
            else:
                inner = typical - np.array([(W - ew) / 2, (H - eh) / 2, (W - ew) / 2, (H - eh) / 2])
            if min(inner) < safety - 0.2:
                res["befunde"].append((WARNUNG, "Weißer Kartenrand zu schmal",
                                       f"Rand im Endformat ca. {min(inner):.1f} mm, Leitfaden {safety:g} mm bei weißem Rand."))
            else:
                res["befunde"].append((OK, "Kartenrand", f"Weißer Rand ca. {min(inner):.1f} mm im Endformat (Soll ≥ {safety:g} mm)."))
            # Ausreißer: Inhalt ragt in den Rand
            out = [(m[0], min(m[1:])) for m in margins if min(m[1:]) < min(typical) - 0.4]
            if out:
                pg = out[0][0]
                fn = os.path.join(shots_dir, f"{tag}_S{pg}_Inhalt_im_Rand.png")
                doc[pg - 1].get_pixmap(matrix=fitz.Matrix(5, 5)).save(fn)
                res["screens"].append(fn)
                res["befunde"].append((FEHLER, "Inhalt ragt in den weißen Rand",
                                       "Seiten: " + ", ".join(f"{p} ({d:.1f} mm)" for p, d in out[:15]) + ". Meist Text, der aus dem Farbfeld läuft.", fn))
        elif ink_at_edge and ew is None:
            res["befunde"].append((HINWEIS, "Karten randabfallend",
                                   "Farbe läuft bis an den Seitenrand – Beschnitt vorhanden oder Endformat = Datei. Endformat bestätigen lassen."))
    else:
        if ew is not None and ink_at_edge:
            bx, by = (W - ew) / 2, (H - eh) / 2
            res["mess"]["ueberstand_mm"] = (round(bx, 1), round(by, 1))
        if not ink_at_edge and kind in ("Anleitung", "Sonstiges") and ew is None:
            res["befunde"].append((HINWEIS, "Weißer Seitenrand", "Kein randabfallendes Motiv erkannt – Beschnitt ggf. nicht nötig."))
    return res


def overlay_trim(doc, ew, eh, W, H, kind, rules, shots_dir, tag):
    """Kontrollbild: Endformat (schwarz) und Sicherheitsabstand (blau) über Seite 1."""
    if ew is None or (abs(ew - W) < 0.3 and abs(eh - H) < 0.3):
        return None
    from PIL import ImageDraw
    p = doc[0]
    z = min(1600 / p.rect.width, 6)
    pm = p.get_pixmap(matrix=fitz.Matrix(z, z))
    im = Image.frombytes("RGB", (pm.w, pm.h), pm.samples)
    d = ImageDraw.Draw(im)
    s = pm.w / W
    safety = rules["playing_cards"]["safety_mm_white_border"] if kind == "Karten" else rules["safety_mm"]
    for off, col in ((0, (0, 0, 0)), (safety, (0, 110, 255))):
        x0, y0 = ((W - ew) / 2 + off) * s, ((H - eh) / 2 + off) * s
        d.rectangle([x0, y0, pm.w - x0, pm.h - y0], outline=col, width=2)
    fn = os.path.join(shots_dir, f"{tag}_Endformat_und_Sicherheitsabstand.png")
    im.save(fn)
    return fn
