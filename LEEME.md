# Matriculaciones DGT (actualización automática)

1. Crea un repositorio en GitHub y sube estos archivos (`index.html`, `update_dgt.py`, `.github/`).
2. Settings → Pages → Deploy from branch → `main` / root.
3. Actions → «Actualizar datos DGT» → Run workflow. Para el histórico, ejecuta en local
   `python3 update_dgt.py --desde 2025-01-01` y sube la carpeta `data/`.
4. Desde entonces el workflow corre cada día laborable, añade los ZIP nuevos de la DGT y la web
   los carga sola (`data/index.json` + `data/YYYYMM.json`).

Si la DGT bloquea las descargas automáticas, descarga los ZIP a mano en una carpeta y ejecuta
`python3 update_dgt.py --local carpeta/`.
Prueba en local: `python3 -m http.server` y abre http://localhost:8000.
