"""Google-Drive-Zugriff über den Make-„Drive-Proxy“ (kein Google-Dienstkonto nötig).

Der Proxy ist ein Make-Szenario mit Webhook, das mit der Google-Drive-Verbindung des Nutzers arbeitet:
  aktion=api     → beliebiger Drive-API-Aufruf unter /v3/files (Liste, Ordner anlegen, Freigabe setzen/entfernen)
  aktion=upload  → Datei (base64) in einen Ordner hochladen
Große Dateien werden NICHT durch Make geschleust: Für den Download wird kurz eine Link-Freigabe gesetzt,
die Datei direkt von Google geladen und die Freigabe sofort wieder entfernt.

Umgebungsvariablen (in der Umgebung der Routine):
    MAKE_PROXY_URL   https://hook.eu2.make.com/…
    MAKE_PROXY_KEY   Zugangsschlüssel des Proxys
    DRIVE_EINGANG_ID Ordner-ID von 01_Eingang
    DRIVE_BERICHTE_ID Ordner-ID von 02_Berichte
(alternativ die beiden Ordner-IDs in config/drive.json)

Aufrufe:
    python -m preflight.gdrive list
    python -m preflight.gdrive fetch <auftrag|--neu> <arbeitsordner>
    python -m preflight.gdrive push <auftragsordnername> <ausgabeordner>
"""
import base64
import datetime
import json
import os
import sys
import time

import requests

FOLDER = "application/vnd.google-apps.folder"
DL = "https://drive.usercontent.google.com/download"
MAX_UPLOAD_BYTES = 3_600_000  # Make-Webhooks vertragen ca. 5 MB Nutzlast; base64 macht +33 %


def _cfg(k):
    v = os.environ.get(k)
    if v:
        return v
    p = os.path.join(os.path.dirname(__file__), "..", "config", "drive.json")
    if os.path.exists(p):
        v = json.load(open(p, encoding="utf-8")).get(k)
    if not v:
        sys.exit(f"{k} fehlt (Umgebungsvariable oder config/drive.json).")
    return v


class Drive:
    def __init__(self):
        self.url, self.key = _cfg("MAKE_PROXY_URL"), _cfg("MAKE_PROXY_KEY")

    def _post(self, payload, timeout=170):
        for attempt in range(3):
            r = requests.post(self.url, json=dict(payload, key=self.key), timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1)); continue
            break
        txt = r.text.strip()
        if txt == "Accepted":
            sys.exit("Drive-Proxy hat nicht geantwortet („Accepted“): Schlüssel falsch, Szenario inaktiv oder Fehler in Make.")
        if r.status_code >= 400:
            sys.exit(f"Drive-Proxy Fehler {r.status_code}: {txt[:300]}")
        try:
            return r.json() if txt else {}
        except ValueError:
            sys.exit(f"Drive-Proxy: unerwartete Antwort: {txt[:300]}")

    def api(self, method, url, qs=None, body=None):
        q = [{"key": k, "value": str(v)} for k, v in (qs or {}).items()]
        return self._post({"aktion": "api", "method": method, "url": url, "qs": q, "body": body or {}})

    def children(self, fid):
        out, tok = [], None
        while True:
            qs = {"q": f"'{fid}' in parents and trashed=false", "pageSize": 1000, "supportsAllDrives": "true",
                  "includeItemsFromAllDrives": "true", "fields": "nextPageToken,files(id,name,mimeType,size)"}
            if tok:
                qs["pageToken"] = tok
            j = self.api("GET", "/v3/files", qs)
            out += j.get("files", [])
            tok = j.get("nextPageToken")
            if not tok:
                return out

    def download(self, fid, path):
        perm = self.api("POST", f"/v3/files/{fid}/permissions", {"supportsAllDrives": "true"}, {"role": "reader", "type": "anyone"})
        pid = perm.get("id")
        try:
            with requests.get(DL, params={"id": fid, "export": "download", "confirm": "t"}, stream=True, timeout=900) as r:
                r.raise_for_status()
                if "text/html" in r.headers.get("Content-Type", ""):
                    raise RuntimeError("Google lieferte eine HTML-Seite statt der Datei (Freigabe/Virenscan).")
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
        finally:
            if pid:
                self.api("DELETE", f"/v3/files/{fid}/permissions/{pid}", {"supportsAllDrives": "true"})

    def mkdir(self, name, parent):
        return self.api("POST", "/v3/files", {"supportsAllDrives": "true"},
                        {"name": name, "mimeType": FOLDER, "parents": [parent]})["id"]

    def upload(self, path, parent):
        data = open(path, "rb").read()
        if len(data) > MAX_UPLOAD_BYTES:
            print(f"  ! {os.path.basename(path)} zu groß für den Proxy ({len(data) / 1e6:.1f} MB) – übersprungen", flush=True)
            return None
        return self._post({"aktion": "upload", "parent": parent, "name": os.path.basename(path),
                           "data_b64": base64.b64encode(data).decode("ascii")}).get("id")


def job_folders(d):
    ein = [f for f in d.children(_cfg("DRIVE_EINGANG_ID")) if f["mimeType"] == FOLDER]
    done = {f["name"] for f in d.children(_cfg("DRIVE_BERICHTE_ID")) if f["mimeType"] == FOLDER}
    return ein, done


def fetch_tree(d, fid, dst):
    os.makedirs(dst, exist_ok=True)
    n = 0
    for f in d.children(fid):
        low = f["name"].lower()
        if f["mimeType"] == FOLDER:
            n += fetch_tree(d, f["id"], os.path.join(dst, f["name"]))
        elif low.endswith((".pdf", ".zip")) or low in ("auftrag.json", "regeln.json"):
            print(f"  ↓ {f['name']} ({int(f.get('size', 0)) / 1e6:.1f} MB)", flush=True)
            d.download(f["id"], os.path.join(dst, f["name"]))
            n += 1
    return n


def main(argv):
    d = Drive()
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        ein, done = job_folders(d)
        for f in ein:
            print(("✓ geprüft  " if f["name"] in done else "○ offen    ") + f["name"])
        return 0
    if cmd == "fetch":
        sel, work = argv[1], argv[2]
        ein, done = job_folders(d)
        todo = [f for f in ein if f["name"] not in done] if sel in ("--neu", "neu", "") else \
               [f for f in ein if sel.lower() in f["name"].lower()]
        res = []
        for f in todo:
            print(f"Lade {f['name']} …", flush=True)
            n = fetch_tree(d, f["id"], os.path.join(work, f["name"]))
            res.append({"ordner": f["name"], "pfad": os.path.join(work, f["name"]), "dateien": n})
        print(json.dumps({"auftraege": res}, ensure_ascii=False))
        return 0
    if cmd == "push":
        name, out = argv[1], argv[2]
        ber = _cfg("DRIVE_BERICHTE_ID")
        existing = {f["name"]: f["id"] for f in d.children(ber) if f["mimeType"] == FOLDER}
        job = existing.get(name) or d.mkdir(name, ber)
        run = d.mkdir(f"Pruefung_{datetime.datetime.now():%Y-%m-%d_%H%M}", job)
        n = 0
        for fn in sorted(os.listdir(out)):
            if fn.lower().endswith((".pdf", ".json")):
                n += bool(d.upload(os.path.join(out, fn), run))
        sd = os.path.join(out, "screens")
        if os.path.isdir(sd):
            sid = d.mkdir("screens", run)
            for fn in sorted(os.listdir(sd)):
                if fn.lower().endswith((".png", ".jpg")) and "_vorschau" not in fn:
                    n += bool(d.upload(os.path.join(sd, fn), sid))
        print(json.dumps({"ordner": f"02_Berichte/{name}/Pruefung_…", "hochgeladen": n}, ensure_ascii=False))
        return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
