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
            "pays": [{"id": k, **v} for k, v in c["pays"].items()], "themes": c["themes"],
            "parcours_vers_maroc": c.get("parcours_vers_maroc", {})}


def fiche_pays(pays_origine: str, classe_maroc: str | None = None) -> str:
    """Cadre réglementaire d'un dossier, en texte, pour le prompt de Mistral :
    parcours du pays d'origine jusqu'au Maroc et articles qui fondent chaque
    étape. Lu dans rules/correspondances.yaml — Mistral le reprend, il ne le
    décide pas."""
    c = charger()
    infos = c["pays"].get(pays_origine)
    if infos is None:  # « autre » : seulement le parcours marocain
        lignes = [f"Pays d'origine : {pays_origine} (pas de fiche pays ; certificat de libre vente du pays d'origine)"]
    else:
        lignes = [f"Pays d'origine : {infos['nom']} — autorité : {infos['autorite']} — texte : {infos['texte']}",
                  f"Preuve de mise sur le marché dans ce pays : {infos['preuve_mise_sur_le_marche']}"]
        if classe_maroc:
            eq = equivalents("maroc", classe_maroc).get(pays_origine)
            if eq:
                lignes.append(f"Classe marocaine {classe_maroc} ≈ classe(s) {', '.join(eq)} dans ce pays (indicatif)")
    parcours = c.get("parcours_vers_maroc", {})
    lignes += ["Étapes jusqu'au dépôt au Maroc :"] + [f"  - {e}" for e in parcours.get(pays_origine, []) + parcours.get("commun_maroc", [])]
    for theme in c["themes"]:
        refs = theme.get("articles", {})
        if theme["id"] in ("preuve_pays_origine", "classification", "etiquetage") and (refs.get("maroc") or refs.get(pays_origine)):
            lignes.append(f"Articles — {theme['question']} : Maroc : {refs.get('maroc', '—')} ; origine : {refs.get(pays_origine, '—')}")
    return "\n".join(lignes)


def synthese(theme: str, generateur, k: int = 2) -> dict:
    """Pour un thème, Mistral résume ce que dit le texte de chaque pays, à
    partir des seuls extraits retrouvés ; la citation qu'il donne est
    vérifiée par le code dans l'extrait (sinon « non vérifiée »)."""
    import json

    from extraction import citation_trouvee

    comparaison = comparer(theme, generateur, k=k)
    references = next(t for t in charger()["themes"] if t["id"] == theme).get("articles", {})
    resultat = {}
    for pays, extraits in comparaison["pays"].items():
        if not extraits:
            resultat[pays] = {"resume": None, "citation": None, "verifiee": False, "reference": references.get(pays),
                              "sources": []}
            continue
        texte = "\n\n".join(f"[{e['texte_source']}]\n{e['texte']}" for e in extraits)
        prompt = (f"Question : {comparaison['theme']['question']}.\n"
                  f"Extraits du texte officiel ({pays}) :\n<<<\n{texte}\n>>>\n"
                  "Réponds en français, en 2 phrases au plus, UNIQUEMENT d'après ces extraits. "
                  "Donne aussi une citation recopiée mot pour mot (au plus 200 caractères) des extraits. "
                  "Si les extraits ne répondent pas, resume = null.")
        brut = generateur.interroger_json(prompt, {"type": "object", "properties": {
            "resume": {"type": ["string", "null"]}, "citation": {"type": ["string", "null"]}},
            "required": ["resume", "citation"]})
        try:
            r = json.loads(brut)
        except ValueError:
            r = {"resume": None, "citation": None}
        citation = (r.get("citation") or "").strip() or None
        resultat[pays] = {"resume": r.get("resume"), "citation": citation,
                          "verifiee": bool(citation) and citation_trouvee(citation, texte),
                          "reference": references.get(pays),
                          "sources": [f"{e['texte_source']} (version du {e['date_version']})" for e in extraits]}
    return {"theme": comparaison["theme"], "pays": resultat}


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
