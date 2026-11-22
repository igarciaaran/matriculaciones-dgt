#!/usr/bin/env python3
"""Descarga los microdatos diarios de matriculaciones de la DGT y los agrega en data/YYYYMM.json.

Uso:
  python3 update_dgt.py                      # añade los días nuevos (listado de la DGT + últimos 10 días)
  python3 update_dgt.py --desde 2026-01-01   # además prueba todos los días desde esa fecha (histórico)
  python3 update_dgt.py --local carpeta/     # procesa ZIP/TXT ya descargados (export_mat_YYYYMMDD.zip)
  python3 update_dgt.py --force              # borra data/ y reconstruye
"""
import argparse, datetime as dt, hashlib, io, json, re, sys, urllib.request, urllib.error, zipfile
from pathlib import Path

LIST = "https://www.dgt.es/menusecundario/dgt-en-cifras/matraba-listados/matriculaciones-automoviles-diario.html"
URL = "https://www.dgt.es/microdatos/salida/{y}/{m}/vehiculos/matriculaciones/export_mat_{d}.zip"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
W = [8,1,8,30,22,1,21,2,1,5,6,6,6,3,2,2,2,2,24,2,2,1,8,5,8,1,1,9,3,5,30,7,3,5,1,1,1,1,1,1,11,25,25,35,70,6,6,4,4,3,8,4,4,4,6,30,50,35,25,35,4,4,4,1,25,1,4,25,8]
O = [sum(W[:i]) for i in range(len(W))]
CCB = [0, 50, 125, 250, 500, 750, 1000, 1400, 2000, 3000, 10**9]  # debe coincidir con la web
DATA = Path(__file__).parent / "data"

def ccb(c):
    if not c: return 0
    for i in range(1, len(CCB)):
        if c <= CCB[i]: return i
    return len(CCB) - 1

def cat_of(h, t):
    h = h.upper()
    if h.startswith("M1"): return 0
    if h[:2] in ("L1", "L2"): return 2
    if h.startswith("L"): return 1
    if h.startswith("N1"): return 3
    if h.startswith("N"): return 4
    if h.startswith("M"): return 5
    return {"40": 0, "50": 1, "51": 2}.get(t, 6)

def num(s, f=float):
    try: return f(s.replace(",", "."))
    except ValueError: return 0

def parse(text, fallback_date):
    acc = {}
    for line in text.split("\n"):
        if len(line) < 700: continue
        g = lambda i: line[O[i]:O[i] + W[i]].strip()
        f = g(0)
        d = int(f[4:] + f[2:4] + f[:2]) if re.fullmatch(r"\d{8}", f) else fallback_date
        cc = int(num(g(9)))
        k = (d, cat_of(g(47), g(7)), g(3), g(4), g(19), g(8), ccb(cc), "U" if g(25) == "U" else "N", "X" if g(26) == "X" else "D")
        r = acc.setdefault(k, [0, 0, 0.0, 0])
        r[0] += 1; r[1] += cc; r[2] += num(g(31)); r[3] += int(num(g(33)))
    return [list(k) + [v[0], v[1], round(v[2], 1), v[3]] for k, v in acc.items()]

def read_zip(buf):
    if buf[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(buf))
        return "\n".join(z.read(n).decode("latin-1") for n in z.namelist() if n.lower().endswith(".txt"))
    return buf.decode("latin-1")

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r: return r.read()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde"); ap.add_argument("--local"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    if a.force:
        for p in DATA.glob("*.json"): p.unlink()
    ip = DATA / "index.json"
    idx = json.loads(ip.read_text()) if ip.exists() else {"files": [], "months": []}
    done = set(idx["files"])
    jobs = {}  # fecha -> loader
    if a.local:
        for p in sorted(Path(a.local).iterdir()):
            m = re.search(r"(\d{8})", p.name)
            if m and p.suffix.lower() in (".zip", ".txt"): jobs[m.group(1)] = lambda p=p: p.read_bytes()
    else:
        urls = {}
        try:
            html = get(LIST).decode("utf-8", "ignore")
            for u, d in re.findall(r"(https://www\.dgt\.es/microdatos/salida/\d{4}/\d+/vehiculos/matriculaciones/export_mat_(\d{8})\.zip)", html): urls[d] = u
        except Exception as e:
            print("Aviso: no se pudo leer el listado:", e, file=sys.stderr)
        today = dt.date.today()
        start = dt.date.fromisoformat(a.desde) if a.desde else today - dt.timedelta(days=10)
        d = start
        while d <= today:
            if d.weekday() < 5: urls.setdefault(d.strftime("%Y%m%d"), URL.format(y=d.year, m=d.month, d=d.strftime("%Y%m%d")))
            d += dt.timedelta(days=1)
        for d, u in urls.items(): jobs[d] = lambda u=u: get(u)
    new = {}
    for d in sorted(jobs):
        if d in done: continue
        try: buf = jobs[d]()
        except urllib.error.HTTPError as e:
            if e.code != 404: print("Error", d, e, file=sys.stderr)
            continue
        except Exception as e:
            print("Error", d, e, file=sys.stderr); continue
        rows = parse(read_zip(buf), int(d))
        if not rows: continue
        for r in rows: new.setdefault(str(r[0])[:6], []).append(r)
        done.add(d); print("OK", d, len(rows), "filas")
    if not new:
        print("Sin días nuevos."); idx["updated"] = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"); ip.write_text(json.dumps(idx)); return
    months = {m["m"]: m for m in idx["months"]}
    for m, rows in new.items():
        p = DATA / f"{m}.json"
        old = json.loads(p.read_text())["rows"] if p.exists() else []
        txt = json.dumps({"rows": old + rows}, separators=(",", ":"), ensure_ascii=False)
        p.write_text(txt, encoding="utf-8")
        months[m] = {"m": m, "v": hashlib.sha1(txt.encode()).hexdigest()[:10]}
    idx = {"updated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "files": sorted(done), "months": [months[k] for k in sorted(months)]}
    ip.write_text(json.dumps(idx, separators=(",", ":")))

if __name__ == "__main__": main()
