"""
Rapprochement des réglementations des sept pays (rules/correspondances.yaml).

Deux usages, tous deux en lecture seule et sans décision :
- `tableau()` : grille commune (niveaux de risque IMDRF A à D -> classes de
  chaque pays, document qui prouve la mise sur le marché, système qualité…) ;
- `comparer(theme)` : pour un thème commun (classification, libre vente…),
  les extraits des textes officiels indexés de chaque pays (RAG), côte à côte.
"""
from __future__ import annotations

import yaml

from rule_engine import RULES_DIR

FICHIER = RULES_DIR / "correspondances.yaml"
# pays dont les textes sont (ou seront) indexés dans Qdrant sous ce nom
PAYS_TEXTES = ["maroc", "union_europeenne", "chine", "inde", "etats_unis", "coree_du_sud", "pakistan", "international"]


def charger() -> dict:
    with open(FICHIER, encoding="utf-8") as f:
        return yaml.safe_load(f)


def tableau() -> dict:
    c = charger()
    return {"version": c["version"], "date_version": c["date_version"], "niveaux": c["niveaux"],
            "pays": [{"id": k, **v} for k, v in c["pays"].items()], "themes": c["themes"]}


def equivalents(pays: str, classe: str) -> dict[str, list[str]]:
    """Classes des autres pays au même niveau de risque que `classe` du pays
    `pays` (indicatif). Ex. equivalents("coree_du_sud", "2") -> {"maroc": ["IIA"], …}."""
    c = charger()["pays"]
    niveaux = [n for n, classes in c[pays]["classes"].items() if str(classe).upper() in [str(x).upper() for x in classes]]
    resultat: dict[str, list[str]] = {}
    for autre, infos in c.items():
        if autre == pays:
            continue
        vues: list[str] = []
        for n in niveaux:
            vues += [str(x) for x in infos["classes"][n] if str(x) not in vues]
        resultat[autre] = vues
    return resultat


def comparer(theme: str, generateur, k: int = 2) -> dict:
    """Extraits des textes officiels de chaque pays sur un même thème."""
    themes = {t["id"]: t for t in charger()["themes"]}
    if theme not in themes:
        raise KeyError(theme)
    question = themes[theme]["question"]
    par_pays = {}
    for pays in PAYS_TEXTES:
        extraits = generateur.rechercher_references(pays, question, k=k)
        par_pays[pays] = [{"texte_source": e["texte_source"], "date_version": e["date_version"], "fichier": e["fichier"],
                           "chunk_index": e["chunk_index"], "score": round(e["score"], 4), "texte": e["texte"][:1200]}
                          for e in extraits]
    return {"theme": themes[theme], "pays": par_pays}
