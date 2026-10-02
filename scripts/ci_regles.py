"""
Matrice de conformité : pour CHAQUE pays d'origine × CHAQUE classe × chaque
situation (équipement, fournisseur distributeur, valeur < ou ≥ 500 $), la
liste des pièces décidée par le moteur de règles (code, jamais l'IA).

La matrice de référence est versionnée (tests/fixtures/matrice_regles.json).
Toute différence fait échouer Jenkins : une règle ne change jamais sans que
la personne qui la change l'ait voulu (et mis à jour la référence).

Contrôles en plus, sur toute la matrice :
  - chaque pièce a un fondement (`source`) et une nature (à rédiger / à fournir) ;
  - aucun numéro de pièce en double dans un même dossier ;
  - pièces étrangères hors UE : traduction signalée ;
  - le certificat du pays d'origine (pièce 4) est toujours présent.

    python scripts/ci_regles.py --rapport rapports-ci            # contrôle
    python scripts/ci_regles.py --mettre-a-jour                  # après un changement voulu des règles
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from rule_engine import charger_regles, documents_requis_maroc  # noqa: E402

REFERENCE = RACINE / "tests" / "fixtures" / "matrice_regles.json"
PAYS = ["union_europeenne", "chine", "inde", "etats_unis", "coree_du_sud", "pakistan", "autre"]
CLASSES = ["I", "IS", "IM", "IR", "IIA", "IIB", "III"]
SITUATIONS = {  # nom : (équipement, distributeur, valeur unitaire en $)
    "standard": (False, False, None),
    "valeur<500": (False, False, 100.0),
    "valeur>=500": (False, False, 900.0),
    "equipement": (True, False, 900.0),
    "distributeur": (False, True, None),
}


def calculer() -> dict:
    matrice = {}
    for pays, classe, (situation, (equipement, distributeur, valeur)) in itertools.product(PAYS, CLASSES, SITUATIONS.items()):
        pieces = documents_requis_maroc(pays, classe, equipement=equipement, valeur_usd=valeur, distributeur=distributeur)
        matrice[f"{pays}|{classe}|{situation}"] = [
            {"id": p.id, "numero": p.numero, "nature": p.nature, "traduction": p.traduction_requise,
             "source": bool(p.source)} for p in pieces]
    return matrice


def anomalies(matrice: dict) -> list[str]:
    erreurs = []
    for cle, pieces in matrice.items():
        pays = cle.split("|")[0]
        numeros = [p["numero"] for p in pieces if p["numero"] is not None]
        if len(numeros) != len(set(numeros)):
            erreurs.append(f"{cle} : numéro de pièce en double {sorted(numeros)}")
        for p in pieces:
            if not p["source"]:
                erreurs.append(f"{cle} : pièce {p['id']} sans fondement (source)")
            if p["nature"] not in ("a_rediger", "a_fournir"):
                erreurs.append(f"{cle} : pièce {p['id']} de nature inconnue {p['nature']}")
        if not any(p["numero"] == 4 for p in pieces):
            erreurs.append(f"{cle} : aucune pièce 4 (certificat ou autorisation du pays d'origine)")
        if pays in ("chine", "coree_du_sud") and not any(p["traduction"] for p in pieces if p["numero"] == 4):
            erreurs.append(f"{cle} : pièce 4 sans traduction signalée")
    return erreurs


def differences(reference: dict, actuelle: dict) -> list[str]:
    diff = []
    for cle in sorted(set(reference) | set(actuelle)):
        avant = set(reference.get(cle, []))
        apres = {f"{p['numero'] if p['numero'] is not None else '-'}:{p['id']}" for p in actuelle.get(cle, [])}
        if avant != apres:
            diff.append(f"{cle} : " + ", ".join([f"+{i}" for i in sorted(apres - avant)] + [f"-{i}" for i in sorted(avant - apres)]))
    return diff


def tableau(matrice: dict) -> str:
    """Résumé lisible : nombre de pièces par pays et par classe (situation standard)."""
    lignes = ["| Origine | " + " | ".join(CLASSES) + " |", "|---|" + "---|" * len(CLASSES)]
    for pays in PAYS:
        lignes.append(f"| {pays} | " + " | ".join(str(len(matrice[f"{pays}|{c}|standard"])) for c in CLASSES) + " |")
    return "\n".join(lignes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rapport", type=Path)
    parser.add_argument("--mettre-a-jour", action="store_true")
    args = parser.parse_args()
    matrice = calculer()
    version = charger_regles("maroc")["version"]
    if args.mettre_a_jour:
        compacte = {cle: [f"{p['numero'] if p['numero'] is not None else '-'}:{p['id']}" for p in pieces]
                    for cle, pieces in matrice.items()}
        REFERENCE.write_text(json.dumps({"version_regles": version, "matrice": compacte}, ensure_ascii=False,
                                        indent=0, sort_keys=True), encoding="utf-8")
        print(f"Référence mise à jour : {len(matrice)} combinaisons (règles Maroc {version})")
        return 0
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    erreurs = anomalies(matrice)
    diff = differences(reference["matrice"], matrice)
    print(f"Matrice des règles Maroc {version} : {len(matrice)} combinaisons "
          f"({len(PAYS)} origines × {len(CLASSES)} classes × {len(SITUATIONS)} situations)")
    print(tableau(matrice))
    for e in erreurs:
        print("  ✗", e)
    if diff:
        print(f"  ✗ {len(diff)} combinaison(s) différente(s) de la référence (règles {reference['version_regles']}) :")
        for d in diff[:40]:
            print("     ", d)
        print("    Changement voulu ? python scripts/ci_regles.py --mettre-a-jour, puis publier la référence.")
    if args.rapport:
        args.rapport.mkdir(parents=True, exist_ok=True)
        (args.rapport / "matrice-regles.md").write_text(f"# Matrice des règles Maroc {version}\n\n{tableau(matrice)}\n",
                                                        encoding="utf-8")
        cas = [f'<testcase classname="regles.matrice" name="{escape(c)}">'
               + (f'<failure message="{escape(m, {chr(34): "&quot;"})}"/>' if (m := next(
                   (x for x in erreurs + diff if x.startswith(c + " ")), None)) else "") + "</testcase>"
               for c in matrice]
        echecs = sum("<failure" in c for c in cas)
        (args.rapport / "regles.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="Règles (matrice)" tests="{len(cas)}" '
            f'failures="{echecs}">\n' + "\n".join(cas) + "\n</testsuite>\n", encoding="utf-8")
    return 1 if erreurs or diff else 0


if __name__ == "__main__":
    sys.exit(main())
