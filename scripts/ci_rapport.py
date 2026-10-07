"""
Rapport unique d'un build Jenkins : une ligne par étape du métier, avec un
verdict lisible, au lieu de centaines de lignes de tests dispersées.

Lit les rapports de rapports-ci/ (JUnit *.xml et *.json des scripts ci_*) et
écrit :
  - rapport.html : la page à ouvrir (Artefacts du build) — HTML sans CSS ni
    script, que Jenkins affiche tel quel ;
  - resume.txt   : une ligne, reprise comme description du build dans la liste.

    python scripts/ci_rapport.py --rapports rapports-ci --niveau complet
"""
from __future__ import annotations

import argparse
import html
import json
import xml.etree.ElementTree as ET
from pathlib import Path

# (fichier JUnit, étape du métier, ce que l'étape prouve)
ETAPES = [
    ("tests-python.xml", "Code", "Moteur de règles, checklist, formulaires, API : tests automatiques"),
    ("regles.xml", "Lois → pièces", "7 pays × 7 classes × 5 situations : pièces exigées et article qui les fonde"),
    ("evaluation-mistral.xml", "Lecture par Mistral", "Documents fictifs aux réponses connues : valeurs lues justes, aucune valeur fausse acceptée"),
    ("rag.xml", "RAG et recommandations", "Bon texte du bon pays retrouvé ; synthèses de Mistral citées mot pour mot"),
    ("agent.xml", "Agent de bout en bout", "Dossier complet : règles, rangement, lecture, checklist, formulaires, lettre, ZIP, base"),
    ("dossiers-acceptes.xml", "Dossiers acceptés rejoués", "L'agent refait les dossiers acceptés par l'AMMPS, sans les voir"),
]


def lire_junit(chemin: Path) -> dict | None:
    if not chemin.exists():
        return None
    racine = ET.parse(chemin).getroot()
    cas = racine.findall(".//testcase")
    echecs = [c for c in cas if c.find("failure") is not None or c.find("error") is not None]
    ignores = [c for c in cas if c.find("skipped") is not None]
    return {"total": len(cas), "echecs": len(echecs), "ignores": len(ignores),
            "motif_ignore": ignores[0].find("skipped").get("message", "") if ignores else "",
            "detail_echecs": [(c.get("name"), (c.find("failure") if c.find("failure") is not None else c.find("error")).get("message", ""))
                              for c in echecs][:15]}


def verdict(r: dict | None, niveau: str, fichier: str) -> tuple[str, str]:
    """(symbole, texte) pour une étape."""
    ia = fichier not in ("tests-python.xml", "regles.xml")
    if r is None:
        return ("—", "non exécutée (niveau rapide)" if ia and niveau == "rapide" else "non exécutée")
    reussis = r["total"] - r["echecs"] - r["ignores"]
    if r["total"] == 0:
        return ("—", "rien à contrôler")
    if r["ignores"] == r["total"]:  # rien n'a été contrôlé : pas une réussite
        return ("—", f"rien contrôlé — {r['motif_ignore']}")
    symbole = "✓" if r["echecs"] == 0 else "✗"
    return (symbole, f"{reussis}/{r['total'] - r['ignores']} réussis" + (f", {r['ignores']} ignoré(s)" if r["ignores"] else ""))


def verdict_mistral(m: dict | None, symbole: str, texte: str) -> tuple[str, str]:
    """Lecture par Mistral : réussie si l'exactitude atteint le seuil et
    qu'aucune valeur fausse n'a été acceptée (une valeur manquée est signalée
    à la relecture, pas acceptée)."""
    if not m or not m.get("total"):
        return symbole, texte
    ok = m["exactitude"] >= m["seuil"] and not m["dangereuses"]
    return ("✓" if ok else "✗", f"{m['justes']}/{m['total']} justes — {m['exactitude']:.0%} (seuil {m['seuil']:.0%}), "
                                 f"{m['dangereuses']} fausse(s) acceptée(s)")


def charger_json(chemin: Path):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def construire(rapports: Path, niveau: str, build: str) -> tuple[str, str]:
    lignes, resume = [], []
    for fichier, nom, preuve in ETAPES:
        r = lire_junit(rapports / fichier)
        symbole, texte = verdict(r, niveau, fichier)
        if fichier == "evaluation-mistral.xml" and r is not None:
            symbole, texte = verdict_mistral(charger_json(rapports / "evaluation-mistral.json"), symbole, texte)
        lignes.append((nom, preuve, symbole, texte, r))
        if symbole != "—":
            resume.append(f"{nom} {symbole} {texte.split(',')[0]}")
    mistral = charger_json(rapports / "evaluation-mistral.json")
    agent = charger_json(rapports / "agent.json")
    acceptes = charger_json(rapports / "dossiers-acceptes.json")
    matrice = (rapports / "matrice-regles.md").read_text(encoding="utf-8") if (rapports / "matrice-regles.md").exists() else ""

    h = html.escape
    corps = [f"<h1>Rapport de l'agent — build {h(build)} (niveau {h(niveau)})</h1>",
             "<p>Chaque ligne est une étape du métier. ✓ : prouvée par ce build. ✗ : à corriger (détail plus bas). "
             "— : non exécutée.</p>",
             "<table border='1' cellpadding='6' cellspacing='0'><tr><th>Étape</th><th>Ce qui est prouvé</th>"
             "<th>Verdict</th><th>Résultat</th></tr>"]
    for nom, preuve, symbole, texte, _ in lignes:
        corps.append(f"<tr><td><b>{h(nom)}</b></td><td>{h(preuve)}</td><td align='center'><b>{symbole}</b></td>"
                     f"<td>{h(texte)}</td></tr>")
    corps.append("</table>")
    if mistral:
        corps.append(f"<h2>Lecture par Mistral</h2><p>Modèle {h(str(mistral.get('modele')))} : exactitude "
                     f"<b>{mistral.get('exactitude', 0):.0%}</b> (seuil {mistral.get('seuil', 0):.0%}), "
                     f"{mistral.get('justes')}/{mistral.get('total')} valeurs justes, "
                     f"<b>{mistral.get('dangereuses')}</b> valeur(s) fausse(s) acceptée(s).</p>")
        manquees = [d for d in mistral.get("detail", []) if d.get("verdict") == "manquee"]
        if manquees:
            corps.append("<p>Valeurs manquées (signalées « à relire », jamais acceptées) :</p><ul>" + "".join(
                f"<li>{h(d['specimen'])} — {h(d['champ'])} : attendu « {h(str(d['attendu']))} », "
                f"lu « {h(str(d['lu']))} »</li>" for d in manquees) + "</ul>")
    if agent and agent.get("bilan"):
        b = agent["bilan"]
        corps.append(f"<h2>Agent de bout en bout</h2><p>Bilan du dossier d'essai : <b>{h(b.get('titre', ''))}</b></p>")
    if agent and agent.get("lettre"):
        lettre = agent["lettre"].split("Sources réglementaires")[0]
        corps.append(f"<h3>Lettre rédigée par Mistral (dossier fictif)</h3><pre>{h(lettre)}</pre>")
    if acceptes:
        corps.append("<h2>Dossiers acceptés rejoués</h2><table border='1' cellpadding='6' cellspacing='0'>"
                     "<tr><th>Dossier</th><th>Classe</th><th>Pièces lues</th><th>Valeurs vérifiées</th>"
                     "<th>Formulaires = dossier accepté</th><th>Avec la mémoire du fabricant</th><th>Lettre ressemblante</th><th>Cases à compléter</th></tr>")
        for a in acceptes:
            note, lettre_r, avec = a.get("formulaire_note"), a.get("lettre_ressemblance"), a.get("formulaire_note_memoire")
            corps.append(f"<tr><td>{h(a['dossier'])}</td><td>{h(str(a['classe']))}</td><td>{a['pieces_lues']}</td>"
                         f"<td>{a['valeurs_verifiees']}/{a['valeurs_trouvees']}</td>"
                         f"<td>{'—' if note is None else f'{note:.0%}'}</td>"
                         f"<td>{'—' if avec is None else f'{avec:.0%}'}</td>"
                         f"<td>{'—' if lettre_r is None else f'{lettre_r:.0%}'}</td>"
                         f"<td>{a['cases_a_completer']}</td></tr>")
        corps.append("</table>")
    if matrice:
        corps.append(f"<h2>Matrice des règles</h2><pre>{h(matrice)}</pre>")
    echecs = [(nom, e) for nom, _, _, _, r in lignes if r for e in r["detail_echecs"]]
    if echecs:
        corps.append("<h2>À corriger</h2><ul>" + "".join(f"<li><b>{h(n)}</b> — {h(t)} : {h(m)}</li>"
                                                         for n, (t, m) in echecs) + "</ul>")
    page = ("<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Rapport de l'agent</title></head><body>"
            + "\n".join(corps) + "</body></html>")
    return page, " · ".join(resume) or "aucun rapport"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rapports", type=Path, default=Path("rapports-ci"))
    parser.add_argument("--niveau", default="complet")
    parser.add_argument("--build", default="")
    args = parser.parse_args()
    page, resume = construire(args.rapports, args.niveau, args.build)
    args.rapports.mkdir(parents=True, exist_ok=True)
    (args.rapports / "rapport.html").write_text(page, encoding="utf-8")
    (args.rapports / "resume.txt").write_text(resume, encoding="utf-8")
    print("RÉSUMÉ :", resume)


if __name__ == "__main__":
    main()
