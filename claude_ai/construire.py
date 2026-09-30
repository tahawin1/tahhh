"""
Assemble l'édition claude.ai du tableau de bord en une seule page HTML.

    .venv/bin/python claude_ai/construire.py SORTIE.html            # page à publier sur claude.ai
    .venv/bin/python claude_ai/construire.py SORTIE.html --local DOSSIER_LIBS
                                            # test local : bibliothèques locales + simulation de claude.ai

Contenu : le build de production de frontend/ (VITE_API_URL pointant vers
le moteur), claude_ai/regles.json (exporté du moteur de règles), puis
controle.js et moteur.js. Bibliothèques : pdf.js 3.11.174 et JSZip 3.10.1
depuis cdnjs (seul hôte de scripts autorisé sur claude.ai).
"""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
ICI = RACINE / "claude_ai"
CDN = {
    "pdf": "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
    "pdf_worker": "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js",
    "jszip": "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js",
}
LOCAL = {
    "pdf": "pdfjs-dist-3.11.174/build/pdf.min.js",
    "pdf_worker": "pdfjs-dist-3.11.174/build/pdf.worker.min.js",
    "jszip": "jszip-3.10.1/dist/jszip.min.js",
}

parser = argparse.ArgumentParser()
parser.add_argument("sortie")
parser.add_argument("--local", metavar="DOSSIER_LIBS", help="test local : scripts depuis ce dossier + simulation")
args = parser.parse_args()

with tempfile.TemporaryDirectory() as dist:
    subprocess.run(
        ["npx", "vite", "build", "--outDir", dist, "--emptyOutDir"],
        cwd=RACINE / "frontend", check=True, env={**os.environ, "VITE_API_URL": "https://moteur.claude-ai.invalid"},
    )
    css = next((Path(dist) / "assets").glob("*.css")).read_text()
    app = next((Path(dist) / "assets").glob("*.js")).read_text()

regles = (ICI / "regles.json").read_text().replace("</", "<\\/")
scripts_js = [(ICI / "controle.js").read_text(), (ICI / "moteur.js").read_text()]
if args.local:
    scripts_js.insert(0, (ICI / "simulation_locale.js").read_text())
    sources = {k: os.path.relpath(Path(args.local) / v, Path(args.sortie).resolve().parent) for k, v in LOCAL.items()}
else:
    sources = CDN
for code in [app, *scripts_js]:
    assert "</script" not in code

libs = "\n".join(f'<script src="{sources[k]}"></script>' for k in ("pdf", "pdf_worker", "jszip"))
inline = "\n".join(f"<script>\n{code}\n</script>" for code in scripts_js)

page = f"""<title>Espace conformité DM</title>
<style>
{css}
</style>
<div id="root"></div>
<script type="application/json" id="regles">{regles}</script>
{libs}
<script>if (window.pdfjsLib) window.pdfjsLib.GlobalWorkerOptions.workerSrc = "{sources['pdf_worker']}";</script>
{inline}
<script type="module">
{app}
</script>
"""
Path(args.sortie).write_text(page)
print(f"{args.sortie} : {len(page) // 1024} Ko{' (test local)' if args.local else ''}")
