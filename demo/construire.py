"""
Assemble la démonstration hors ligne du tableau de bord en une seule page HTML.

    python demo/construire.py SORTIE.html [--dossiers 1,2]

1. build de production de frontend/ avec VITE_API_URL=https://demo.invalid ;
2. intègre dans la page : la feuille de style, l'instantané des données
   réelles (demo/instantane.json, filtré sur --dossiers), demo/shim.js puis
   l'application.

L'instantané se régénère depuis un backend en marche (voir README de demo/).
"""
import argparse
import datetime
import json
import os
import subprocess
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DEMO = RACINE / "demo"

parser = argparse.ArgumentParser()
parser.add_argument("sortie")
parser.add_argument("--dossiers", default="", help="ids des dossiers à garder, ex. 1,2 (défaut : tous)")
args = parser.parse_args()

instantane = json.loads((DEMO / "instantane.json").read_text())
if args.dossiers:
    garder = {int(i) for i in args.dossiers.split(",")}
    instantane["dossiers"] = [d for d in instantane["dossiers"] if d["id"] in garder]
    instantane["apercus"] = {k: v for k, v in instantane["apercus"].items() if int(k.split("/")[0]) in garder}

with tempfile.TemporaryDirectory() as dist:
    subprocess.run(
        ["npx", "vite", "build", "--outDir", dist, "--emptyOutDir"],
        cwd=RACINE / "frontend", check=True, env={**os.environ, "VITE_API_URL": "https://demo.invalid"},
    )
    assets = Path(dist) / "assets"
    css = next(assets.glob("*.css")).read_text()
    js = next(assets.glob("*.js")).read_text()

pris_le = datetime.datetime.fromisoformat(instantane["pris_le"]).strftime("%d/%m/%Y à %H:%M UTC")
donnees = json.dumps(instantane, ensure_ascii=False).replace("</", "<\\/")
shim = (DEMO / "shim.js").read_text()
assert "</script" not in js and "</script" not in shim

page = f"""<title>Tableau de bord conformité DM</title>
<style>
{css}
.bandeau-demo {{
  background: var(--attention-fond); color: var(--attention);
  padding-block: 0.6rem; padding-inline: 1rem; font-size: 0.88rem; line-height: 1.45; text-align: center;
  border-bottom: 1px solid var(--bordure);
}}
.bandeau-demo strong {{ font-weight: 700; }}
/* la démo n'est reliée à aucun serveur : pas d'indicateur « Backend en ligne » */
.entete .pastille {{ display: none; }}
</style>
<div class="bandeau-demo" role="note">
  <strong>Démonstration</strong> — instantané des données réelles du backend, pris le {pris_le}.
  Cette page n'est pas connectée au serveur : les validations et rejets restent dans cet onglet
  (un rechargement les efface) et la rédaction par Mistral est désactivée.
</div>
<div id="root"></div>
<script type="application/json" id="instantane">{donnees}</script>
<script>
{shim}
</script>
<script type="module">
{js}
</script>
"""
Path(args.sortie).write_text(page)
print(f"{args.sortie} : {len(page) // 1024} Ko, {len(instantane['dossiers'])} dossier(s)")
