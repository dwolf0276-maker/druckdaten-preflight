"""Google-Drive-Anbindung per Dienstkonto (Service Account).

Umgebungsvariablen:
    GDRIVE_SA_JSON      Inhalt der Dienstkonto-Schlüsseldatei (JSON, roh oder base64)
    GDRIVE_EINGANG_ID   Ordner-ID von 01_Eingang
    GDRIVE_BERICHTE_ID  Ordner-ID von 02_Berichte

Aufrufe:
    python -m preflight.gdrive list                       # Auftragsordner + Status anzeigen
    python -m preflight.gdrive fetch <auftrag|--neu> <arbeitsordner>
    python -m preflight.gdrive push <auftragsordnername> <ausgabeordner>
"""
import base64
import datetime
import json
import os
import sys

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER = "application/vnd.google-apps.folder"
COMMON = {"supportsAllDrives": "true"}


def _creds():
    raw = os.environ.get("GDRIVE_SA_JSON", "").strip()
    if not raw:
        sys.exit("GDRIVE_SA_JSON fehlt.")
    if not raw.startswith("{"):
        raw = base64.b64decode(raw).decode("utf-8")
    c = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=["https://www.googleapis.com/auth/drive"])
    c.refresh(Request())
    return c


class Drive:
    def __init__(self):
        self.c = _creds()

    def _h(self):
        if not self.c.valid:
            self.c.refresh(Request())
        return {"Authorization": f"Bearer {self.c.token}"}

    def children(self, folder_id):
        out, tok = [], None
        while True:
            p = dict(COMMON, q=f"'{folder_id}' in parents and trashed=false", pageSize=1000,
                     fields="nextPageToken,files(id,name,mimeType,size,modifiedTime)", includeItemsFromAllDrives="true")
            if tok:
                p["pageToken"] = tok
            r = requests.get(f"{API}/files", headers=self._h(), params=p, timeout=60)
            r.raise_for_status()
            j = r.json()
            out += j.get("files", [])
            tok = j.get("nextPageToken")
            if not tok:
                return out

    def download(self, fid, path):
        with requests.get(f"{API}/files/{fid}", headers=self._h(), params=dict(COMMON, alt="media"), stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)

    def mkdir(self, name, parent):
        r = requests.post(f"{API}/files", headers=self._h(), params=COMMON,
                          json={"name": name, "mimeType": FOLDER, "parents": [parent]}, timeout=60)
        r.raise_for_status()
        return r.json()["id"]

    def upload(self, path, parent, mime):
        meta = {"name": os.path.basename(path), "parents": [parent]}
        files = {"metadata": ("metadata", json.dumps(meta), "application/json; charset=UTF-8"),
                 "file": (os.path.basename(path), open(path, "rb"), mime)}
        r = requests.post(UPLOAD, headers=self._h(), params=dict(COMMON, uploadType="multipart"), files=files, timeout=600)
        r.raise_for_status()
        return r.json()["id"]


def _env(k):
    v = os.environ.get(k)
    if not v:
        sys.exit(f"{k} fehlt.")
    return v


def job_folders(d):
    ein = [f for f in d.children(_env("GDRIVE_EINGANG_ID")) if f["mimeType"] == FOLDER]
    done = {f["name"] for f in d.children(_env("GDRIVE_BERICHTE_ID")) if f["mimeType"] == FOLDER}
    return ein, done


def fetch_tree(d, fid, dst):
    os.makedirs(dst, exist_ok=True)
    n = 0
    for f in d.children(fid):
        low = f["name"].lower()
        if f["mimeType"] == FOLDER:
            n += fetch_tree(d, f["id"], os.path.join(dst, f["name"]))
        elif low.endswith((".pdf", ".zip")) or low == "auftrag.json":
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
        if sel == "--neu":
            todo = [f for f in ein if f["name"] not in done]
        else:
            todo = [f for f in ein if sel.lower() in f["name"].lower()]
        if not todo:
            print(json.dumps({"auftraege": []}))
            return 0
        res = []
        for f in todo:
            print(f"Lade {f['name']} …", flush=True)
            n = fetch_tree(d, f["id"], os.path.join(work, f["name"]))
            res.append({"ordner": f["name"], "pfad": os.path.join(work, f["name"]), "dateien": n})
        print(json.dumps({"auftraege": res}, ensure_ascii=False))
        return 0
    if cmd == "push":
        name, out = argv[1], argv[2]
        ber = _env("GDRIVE_BERICHTE_ID")
        existing = {f["name"]: f["id"] for f in d.children(ber) if f["mimeType"] == FOLDER}
        job = existing.get(name) or d.mkdir(name, ber)
        run = d.mkdir(f"Pruefung_{datetime.datetime.now():%Y-%m-%d_%H%M}", job)
        up = []
        for fn in sorted(os.listdir(out)):
            p = os.path.join(out, fn)
            if fn.lower().endswith(".pdf"):
                up.append(d.upload(p, run, "application/pdf"))
            elif fn.lower().endswith(".json"):
                up.append(d.upload(p, run, "application/json"))
        sd = os.path.join(out, "screens")
        if os.path.isdir(sd):
            sid = d.mkdir("screens", run)
            for fn in sorted(os.listdir(sd)):
                if fn.lower().endswith(".png") and not fn.endswith("_vorschau.png"):
                    up.append(d.upload(os.path.join(sd, fn), sid, "image/png"))
        print(json.dumps({"ordner": f"02_Berichte/{name}/{os.path.basename(run)}", "hochgeladen": len(up)}, ensure_ascii=False))
        return 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
