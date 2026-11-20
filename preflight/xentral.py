"""Auftragsdaten (Spielbeschreibung/Ausstattung) aus Xentral holen – über den Make-Webhook
„Druckdaten-Prüfung – Auftragsdaten aus Xentral“.

Aufruf:
    python -m preflight.xentral <auftragsnummer> <zielordner>
Schreibt <zielordner>/xentral_auftrag.json (komplette Auftragsdaten inkl. Positionen) und gibt die
Positionstexte lesbar aus. Daraus erstellt Claude die spezifikation.json (siehe docs/spezifikation.md).
"""
import json
import os
import re
import sys

import requests

from .gdrive import _cfg


def _texts(obj, path=""):
    """Alle längeren Textfelder (Beschreibungen) rekursiv einsammeln."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _texts(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _texts(v, f"{path}[{i}]")
    elif isinstance(obj, str) and len(obj) > 25 and not re.fullmatch(r"[\w\-:.+ ]+", obj[:40] + "x"):
        out.append((path, obj))
    elif isinstance(obj, str) and len(obj) > 60:
        out.append((path, obj))
    return out


def fetch(nr, dst):
    url = _cfg("MAKE_XENTRAL_URL")
    r = requests.post(url, json={"key": _cfg("MAKE_PROXY_KEY"), "auftragsnummer": str(nr)}, timeout=120)
    if r.status_code == 404:
        sys.exit(f"Auftrag {nr} in Xentral nicht gefunden.")
    if r.text.strip() == "Accepted":
        sys.exit("Xentral-Webhook hat nicht geantwortet („Accepted“): Schlüssel falsch oder Szenario inaktiv.")
    r.raise_for_status()
    data = r.json()
    os.makedirs(dst, exist_ok=True)
    fn = os.path.join(dst, "xentral_auftrag.json")
    json.dump(data, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Gespeichert: {fn}")
    for p, t in _texts(data):
        if any(s in p.lower() for s in ("address", "email", "phone", "iban", "street")):
            continue
        print(f"\n--- {p} ---\n{t[:4000]}")
    return fn


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    fetch(sys.argv[1], sys.argv[2])
