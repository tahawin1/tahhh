"""
Assemble la démonstration hors ligne du tableau de bord en une seule page
HTML (publiable comme page claude.ai).

    python demo/construire.py SORTIE.html

C'est le build de production de frontend/ en mode démonstration
(VITE_API_URL=demo) : données d'exemple dans frontend/src/demo/instantane.json,
adaptateur dans frontend/src/demo/moteurDemo.ts. Le même mode sert à
déployer la démonstration sur Vercel (voir DEPLOIEMENT.md).
demo/instantane-complet.json garde l'instantané brut de l'API dont
l'exemple est tiré.
"""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

parser = argparse.ArgumentParser()
parser.add_argument("sortie")
args = parser.parse_args()

with tempfile.TemporaryDirectory() as dist:
    subprocess.run(
        ["npx", "vite", "build", "--outDir", dist, "--emptyOutDir"],
        cwd=RACINE / "frontend", check=True,
        env={**os.environ, "VITE_API_URL": "demo", "PAGE_UNIQUE": "1"},  # un seul fichier JS, démo incluse
    )
    fichiers_js = list((Path(dist) / "assets").glob("*.js"))
    assert len(fichiers_js) == 1, fichiers_js
    css = next((Path(dist) / "assets").glob("*.css")).read_text()
    app = fichiers_js[0].read_text()

assert "</script" not in app
page = f"""<title>Tableau de bord conformité DM</title>
<style>
{css}
</style>
<div id="root"></div>
<script type="module">
{app}
</script>
"""
Path(args.sortie).write_text(page)
print(f"{args.sortie} : {len(page) // 1024} Ko")
