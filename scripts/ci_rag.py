"""
Contrôle du RAG (Qdrant + embeddings bge-m3 via Ollama) et des
recommandations de Mistral, sur la vraie base du serveur — lecture seule.

1. Index : chaque pays a des extraits indexés (dossiers_reference), avec
   leur date de version ; modèles des dossiers acceptés comptés.
2. Recherche : pour des questions de référence, le bon texte officiel du bon
   pays doit sortir dans les 3 premiers extraits (sinon le RAG nourrit
   Mistral avec le mauvais texte).
3. Recommandations : synthèse par Mistral, pays par pays, avec citation
   vérifiée par le code dans l'extrait (thèmes « preuve du pays d'origine » et
   « certificat de libre vente ») : au moins N pays avec citation vérifiée.

    python scripts/ci_rag.py --rapport rapports-ci
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

PAYS = ["maroc", "union_europeenne", "chine", "inde", "etats_unis", "coree_du_sud", "pakistan"]

# (pays, question, motif attendu dans le nom du texte source)
QUESTIONS = [
    ("maroc", "pièces du dossier d'enregistrement d'un dispositif médical importé", r"Arrêtés 2853|Loi 84-12"),
    ("maroc", "matériovigilance : signalement des incidents et rappel des dispositifs", r"Loi 84-12|Arrêtés"),
    ("union_europeenne", "certificate of free sale issued by the Member State", r"2017/745"),
    ("union_europeenne", "conformity assessment by a notified body for class III devices", r"2017/745"),
    ("chine", "registration of imported class II and class III medical devices", r"Order 739"),
    ("inde", "import licence and free sale certificate for medical devices", r"Medical Devices Rules"),
    ("etats_unis", "certification for export of a device to a foreign government", r"FD&C Act|21 CFR"),
    ("etats_unis", "premarket notification 510(k)", r"21 CFR Part 807|FD&C Act, section 510"),
    ("coree_du_sud", "import permit, certification or notification of medical devices", r"Medical Devices Act|의료기기법|Enforcement"),
    ("pakistan", "registration and enlistment of medical devices", r"DRAP|Medical Devices Rules"),
]
THEMES_MISTRAL = ["preuve_pays_origine", "libre_vente"]


class Rapport:
    def __init__(self):
        self.cas: list[tuple[str, str, float, str | None]] = []

    def noter(self, groupe: str, nom: str, duree: float, echec: str | None = None):
        self.cas.append((groupe, nom, duree, echec))
        print(f"  {'✗' if echec else '✓'} [{groupe}] {nom}" + (f" — {echec}" if echec else ""))

    def junit(self, chemin: Path):
        a = {'"': "&quot;"}
        lignes = [f'<testcase classname="rag.{g}" name="{escape(n, a)}" time="{d:.1f}">'
                  + (f'<failure message="{escape(e, a)}"/>' if e else "") + "</testcase>" for g, n, d, e in self.cas]
        echecs = sum(1 for c in self.cas if c[3])
        chemin.write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="RAG et Mistral" '
                          f'tests="{len(self.cas)}" failures="{echecs}">\n' + "\n".join(lignes) + "\n</testsuite>\n",
                          encoding="utf-8")


def controler_index(rapport: Rapport, client) -> dict:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from generate import COLLECTION
    from modeles import COLLECTION_MODELES

    comptes = {}
    for pays in PAYS:
        debut = time.monotonic()
        n = client.count(COLLECTION, count_filter=Filter(must=[FieldCondition(key="pays", match=MatchValue(value=pays))]),
                         exact=True).count
        comptes[pays] = n
        rapport.noter("index", f"{pays} : {n} extraits indexés", time.monotonic() - debut,
                      None if n else "aucun extrait : lancer scripts/indexer_tout.sh")
    if client.collection_exists(COLLECTION_MODELES):
        comptes["modeles_acceptes"] = client.count(COLLECTION_MODELES, exact=True).count
    else:
        comptes["modeles_acceptes"] = 0
    print(f"  · modèles de dossiers acceptés indexés : {comptes['modeles_acceptes']}")
    return comptes


def controler_recherche(rapport: Rapport, generateur) -> list[dict]:
    resultats = []
    for pays, question, motif in QUESTIONS:
        debut = time.monotonic()
        extraits = generateur.rechercher_references(pays, question, k=3)
        sources = [e["texte_source"] for e in extraits]
        bon = any(re.search(motif, s) for s in sources)
        mauvais_pays = [e["pays"] for e in extraits if e.get("pays") != pays]
        echec = None
        if mauvais_pays:
            echec = f"extraits d'un autre pays : {mauvais_pays}"
        elif not bon:
            echec = f"texte attendu ({motif}) absent des 3 premiers : {sources}"
        rapport.noter("recherche", f"{pays} — {question}", time.monotonic() - debut, echec)
        resultats.append({"pays": pays, "question": question, "sources": sources,
                          "scores": [round(e["score"], 3) for e in extraits], "ok": echec is None})
    return resultats


def controler_mistral(rapport: Rapport, generateur, minimum: int) -> dict:
    import correspondances

    syntheses = {}
    for theme in THEMES_MISTRAL:
        debut = time.monotonic()
        try:
            r = correspondances.synthese(theme, generateur)
        except Exception as e:
            rapport.noter("mistral", f"synthèse « {theme} »", time.monotonic() - debut, f"{type(e).__name__}: {e}")
            continue
        verifiees = [p for p, v in r["pays"].items() if v.get("verifiee")]
        inventees = [p for p, v in r["pays"].items() if v.get("citation") and not v.get("verifiee")]
        syntheses[theme] = r
        echec = None
        if len(verifiees) < minimum:
            echec = f"{len(verifiees)} pays avec citation vérifiée (minimum {minimum}) ; citation introuvable : {inventees}"
        rapport.noter("mistral", f"synthèse « {theme} » : citations vérifiées pour {', '.join(verifiees) or 'aucun pays'}",
                      time.monotonic() - debut, echec)
    return syntheses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rapport", type=Path, default=RACINE / "rapports-ci")
    parser.add_argument("--minimum-citations", type=int, default=4,
                        help="pays (sur 7) avec citation vérifiée exigés par thème")
    parser.add_argument("--sans-mistral", action="store_true", help="index et recherche seulement")
    args = parser.parse_args()
    from generate import GenerateurDocuments

    rapport = Rapport()
    generateur = GenerateurDocuments()
    print("1. Index Qdrant")
    comptes = controler_index(rapport, generateur.client)
    print("2. Recherche (bon texte, bon pays)")
    recherche = controler_recherche(rapport, generateur)
    syntheses = {}
    if not args.sans_mistral:
        print("3. Recommandations de Mistral (citations vérifiées par le code)")
        syntheses = controler_mistral(rapport, generateur, args.minimum_citations)
    args.rapport.mkdir(parents=True, exist_ok=True)
    rapport.junit(args.rapport / "rag.xml")
    (args.rapport / "rag.json").write_text(json.dumps({"index": comptes, "recherche": recherche, "syntheses": syntheses},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    echecs = [c for c in rapport.cas if c[3]]
    print(f"RAG : {len(rapport.cas) - len(echecs)}/{len(rapport.cas)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
