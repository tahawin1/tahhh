"""
Évaluation de Mistral (via Ollama) sur des documents SPÉCIMEN fictifs dont les
bonnes réponses sont connues : à chaque version du code, Jenkins vérifie que la
lecture des documents du fournisseur reste fiable.

Pour chaque spécimen (tests/fixtures/, texte et scan), le vrai pipeline de
lecture est lancé (OCR si besoin, Mistral, contrôle des citations par le
code) et chaque champ est comparé à la valeur attendue :

  - juste      : la valeur lue contient la valeur attendue ;
  - manquée    : rien lu, ou valeur signalée « non vérifiée » par le code ;
  - DANGEREUSE : valeur fausse que le code a pourtant acceptée (citation
                 retrouvée) — c'est l'erreur qui pourrait passer inaperçue.

Échec (code 1) si l'exactitude est sous le seuil ou s'il y a une seule erreur
dangereuse. Rapports : JUnit (affiché par Jenkins) et JSON.

    python scripts/evaluer_mistral.py --rapport rapports-ci
    OLLAMA_BASE_URL=http://127.0.0.1:11434 python scripts/evaluer_mistral.py --seuil 0.8
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

FIXTURES = RACINE / "tests" / "fixtures"

# Bonnes réponses : données inventées de tests/fixtures/generer_specimens.py
ATTENDU_ISO = {
    "numero": "SCB-MD-2024-0457",
    "emetteur": "SPECIMEN CERTIFICATION BODY",
    "titulaire": "Hangzhou Specimen Orthopaedics",
    "produit_couvert": "hip joint prostheses",
    "date_emission": "2024-03-12",
    "date_expiration": "2027-03-11",
    "norme": "13485",
}
SPECIMENS = [
    ("specimen_iso13485.pdf", "iso_13485", "union_europeenne", ATTENDU_ISO),
    ("specimen_iso13485_scanne.pdf", "iso_13485", "union_europeenne", ATTENDU_ISO),
    ("specimen_nmpa_traduction.pdf", "piece_specifique_chine", "chine", {
        "numero": "20213130457",
        "titulaire": "Hangzhou Specimen Orthopaedics",
        "produit_couvert": "hanche",
        "date_emission": "2021-06-15",
        "date_expiration": "2026-06-14",
        "classe_indiquee": "III",
    }),
]


def champs_de(code: str, pays: str) -> tuple[str, list[dict]]:
    from rule_engine import documents_requis_maroc

    piece = next(d for d in documents_requis_maroc(pays, "III") if d.id == code)
    return piece.nom, piece.champs_a_extraire


def juger(champ: dict, attendu: str) -> str:
    from extraction import VERIFIE, normaliser

    lu = champ.get("valeur_normalisee") if champ.get("type") == "date" else champ.get("valeur")
    juste = bool(lu) and normaliser(attendu) in normaliser(str(lu))
    if juste and champ["verification"] == VERIFIE:
        return "juste"
    if lu and not juste and champ["verification"] == VERIFIE:
        return "dangereuse"
    return "manquee"


def evaluer() -> list[dict]:
    import extraction

    resultats = []
    for fichier, code, pays, attendus in SPECIMENS:
        nom, champs = champs_de(code, pays)
        debut = time.monotonic()
        try:
            lu = extraction.extraire(FIXTURES / fichier, champs, nom)
            erreur = None
        except Exception as e:  # Ollama absent, OCR impossible… : compté, jamais ignoré
            lu, erreur = {"champs": []}, f"{type(e).__name__}: {e}"
        duree = time.monotonic() - debut
        par_nom = {c["nom"]: c for c in lu["champs"]}
        for nom_champ, attendu in attendus.items():
            champ = par_nom.get(nom_champ, {"valeur": None, "verification": "absent"})
            resultats.append({
                "specimen": fichier, "champ": nom_champ, "attendu": attendu,
                "lu": champ.get("valeur"), "verification": champ.get("verification"),
                "verdict": "erreur" if erreur else juger(champ, attendu),
                "erreur": erreur, "duree_s": round(duree / max(len(attendus), 1), 1),
            })
        print(f"  {fichier} : {sum(r['verdict'] == 'juste' for r in resultats if r['specimen'] == fichier)}"
              f"/{len(attendus)} justes en {duree:.0f} s" + (f" — {erreur}" if erreur else ""))
    return resultats


def junit(resultats: list[dict], chemin: Path) -> None:
    lignes = []
    for r in resultats:
        nom = f'{r["specimen"]} — {r["champ"]}'
        cas = f'<testcase classname="mistral.lecture" name="{escape(nom, {chr(34): "&quot;"})}" time="{r["duree_s"]}">'
        if r["verdict"] != "juste":
            message = f'{r["verdict"]} : attendu « {r["attendu"]} », lu « {r["lu"]} » ({r["verification"]})'
            if r["erreur"]:
                message += f' — {r["erreur"]}'
            # valeur manquée mais signalée à la relecture : tolérée sous le seuil
            # d'exactitude ; seule une valeur fausse acceptée est un échec
            balise = "failure" if r["verdict"] == "dangereuse" else "skipped"
            cas += f'<{balise} message="{escape(message, {chr(34): "&quot;"})}"/>'
        lignes.append(cas + "</testcase>")
    echecs = sum(r["verdict"] == "dangereuse" for r in resultats)
    chemin.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="Évaluation Mistral" tests="{len(resultats)}" '
        f'failures="{echecs}" skipped="{sum(r["verdict"] == "manquee" for r in resultats)}">\n' + "\n".join(lignes) + "\n</testsuite>\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rapport", type=Path, default=RACINE / "rapports-ci")
    parser.add_argument("--seuil", type=float, default=0.75, help="exactitude minimale (défaut 0,75)")
    args = parser.parse_args()
    from extraction import OLLAMA_MODEL

    print(f"Évaluation de {OLLAMA_MODEL} sur {len(SPECIMENS)} spécimens fictifs :")
    resultats = evaluer()
    args.rapport.mkdir(parents=True, exist_ok=True)
    junit(resultats, args.rapport / "evaluation-mistral.xml")
    justes = sum(r["verdict"] == "juste" for r in resultats)
    dangereuses = [r for r in resultats if r["verdict"] == "dangereuse"]
    exactitude = justes / len(resultats)
    bilan = {"modele": OLLAMA_MODEL, "exactitude": round(exactitude, 3), "seuil": args.seuil,
             "justes": justes, "total": len(resultats), "dangereuses": len(dangereuses), "detail": resultats}
    (args.rapport / "evaluation-mistral.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Exactitude : {exactitude:.0%} ({justes}/{len(resultats)}), seuil {args.seuil:.0%} ; "
          f"erreurs dangereuses : {len(dangereuses)}")
    for r in dangereuses:
        print(f"  ✗ DANGEREUSE {r['specimen']} {r['champ']} : attendu « {r['attendu']} », lu « {r['lu']} »")
    return 0 if exactitude >= args.seuil and not dangereuses else 1


if __name__ == "__main__":
    sys.exit(main())
