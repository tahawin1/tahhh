"""
Contrôles automatiques de la checklist de l'entreprise (rules/checklist_maroc.yaml)
sur un dossier — agent, étape 2.

Pour chaque point de la checklist applicable au dossier :
- « lecture » : Mistral a cherché le point dans le document reçu et recopié le
  passage qui le prouve ; le CODE a vérifié que ce passage existe dans le
  document (extraction.py). Trouvé et vérifié -> ✓ ; passage introuvable ->
  « à vérifier » ; absent du document -> ✗ (« à vérifier » si le point est
  « si applicable » ou le document facultatif) ;
- contrôles déterministes en plus : validité (date d'expiration lue,
  exception de la lettre de confirmation 2023/607), classe du dispositif ;
- « cohérence » : comparaisons entre documents faites par le code (même
  fabricant, même n° de certificat CE, mêmes produits) ;
- « humain » : signature, cachet, photos… cochés par une personne nommée.

Rien n'est validé ici : le résultat aide la personne qui valide les pièces,
et liste les papiers à réclamer au fournisseur (relance préparée, jamais
envoyée).
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from functools import lru_cache

import yaml

from rule_engine import RULES_DIR

FICHIER = RULES_DIR / "checklist_maroc.yaml"
SI_APPLICABLE = re.compile(r"si applicable|si requis|si mentionn|si visible|si fabricant hors|s'il est st", re.I)
MOTS_VIDES = {"de", "du", "des", "la", "le", "les", "et", "d", "l", "s", "a", "en", "pour", "the", "of", "and",
              "co", "ltd", "inc", "sa", "spa", "s", "p", "gmbh", "sarl", "srl", "llc", "company", "medical"}

OK, KO, A_VERIFIER, EN_ATTENTE, HUMAIN_FAIT, HUMAIN_A_FAIRE = (
    "ok", "ko", "a_verifier", "en_attente", "humain_fait", "humain_a_faire")


@lru_cache(maxsize=4)
def _charger(mtime: float) -> dict:
    with open(FICHIER, encoding="utf-8") as f:
        return yaml.safe_load(f)


def charger() -> dict:
    return _charger(FICHIER.stat().st_mtime)


def element_id(doc_id: str, index: int) -> str:
    return f"cl_{doc_id}_{index}"


def documents_pour_piece(code: str) -> list[dict]:
    return [d for d in charger()["documents"] if code in (d.get("pieces") or [])]


def champs_checklist(code: str) -> list[dict]:
    """Points « lecture » de la checklist pour une pièce : ajoutés aux champs
    que l'agent cherche dans le document reçu (même contrôle des citations)."""
    champs = []
    for d in documents_pour_piece(code):
        for i, e in enumerate(d["elements"]):
            if e["controle"] == "lecture":
                champs.append({"nom": element_id(d["id"], i), "libelle": e["texte"], "type": "texte",
                               "description": f"checklist « {d['nom']} » : {e['texte']} — recopier ce que le document indique sur ce point"})
    return champs


# ---------------------------------------------------------------- outils de comparaison


def _normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _mots(texte: str) -> set[str]:
    return {m for m in re.findall(r"[a-z0-9]+", _normaliser(texte)) if len(m) > 1 and m not in MOTS_VIDES}


def _meme_nom(a: str, b: str) -> bool:
    """Deux raisons sociales désignent-elles le même fabricant ? (mots communs)"""
    ma, mb = _mots(a), _mots(b)
    if not ma or not mb:
        return False
    return len(ma & mb) / min(len(ma), len(mb)) >= 0.5


def _chiffres(texte: str) -> str:
    return "".join(re.findall(r"\d", texte or ""))


def _lecture(piece) -> dict[str, dict]:
    if piece is None or piece.extraction_statut != "terminee" or not piece.extraction:
        return {}
    return {c["nom"]: c for c in piece.extraction.get("champs", [])}


def _valeur(lu: dict, *noms: str) -> str | None:
    for n in noms:
        c = lu.get(n)
        if c and c.get("valeur"):
            return c["valeur"]
    return None


CLASSES = {"i": "I", "is": "IS", "im": "IM", "ir": "IR", "iia": "IIA", "iib": "IIB", "iii": "III",
           "ii a": "IIA", "ii b": "IIB", "2a": "IIA", "2b": "IIB"}


def _classe_lue(texte: str) -> str | None:
    t = _normaliser(texte).replace("class ", "classe ")
    m = re.search(r"\b(iii|ii ?[ab]|i[smr]?)\b", t.replace("classe", " "))
    return CLASSES.get(m.group(1).replace(" ", "")) if m else None


# ---------------------------------------------------------------- évaluation


def evaluer(dossier, aujourd_hui: datetime.date | None = None) -> dict:
    """Résultat de la checklist pour un dossier (objet avec documents,
    classe, pays_origine, controles_humains)."""
    aujourd_hui = aujourd_hui or datetime.date.today()
    pieces = {d.code: d for d in dossier.documents}
    lectures = {code: _lecture(p) for code, p in pieces.items()}
    humains = getattr(dossier, "controles_humains", None) or {}

    # fabricants cités dans les documents lus (pour la cohérence)
    fabricants = {}
    for code, lu in lectures.items():
        v = _valeur(lu, "fabricant", "titulaire")
        if v:
            fabricants[code] = v
    numero_ce = _valeur(lectures.get(f"piece_specifique_{dossier.pays_origine}", {}), "numero")

    resultat_docs = []
    for doc in charger()["documents"]:
        codes = [c for c in doc.get("pieces") or [] if c in pieces]
        if not codes:
            continue  # document de la checklist sans objet pour ce dossier
        piece = pieces[codes[0]]
        lu = lectures.get(piece.code, {})
        recu = bool(piece.fichier_recu) or piece.nature == "a_rediger"
        elements = []
        for i, e in enumerate(doc["elements"]):
            ident = element_id(doc["id"], i)
            r = {"id": ident, "texte": e["texte"], "controle": e["controle"], "statut": EN_ATTENTE, "detail": None}
            if e["controle"] == "humain":
                fait = humains.get(ident)
                r.update(statut=HUMAIN_FAIT if fait else HUMAIN_A_FAIRE,
                         detail=f"Vérifié par {fait['par']} le {fait['le'][:10]}" if fait else "À vérifier par une personne")
            elif not recu:
                r["detail"] = "Document pas encore reçu"
            elif piece.nature == "a_fournir" and piece.extraction_statut in ("en_file", "en_cours"):
                r["detail"] = "Lecture du document en cours par l'agent"
            elif piece.nature == "a_fournir" and piece.extraction_statut == "erreur" and e["controle"] == "lecture":
                r.update(statut=A_VERIFIER, detail="La lecture du document a échoué : relancer la lecture (bouton « Relire »)")
            elif e["controle"] == "lecture":
                r.update(_point_lu(e, lu.get(ident), lu, doc, dossier, piece, aujourd_hui))
            else:
                r.update(_coherence(e, piece.code, fabricants, numero_ce, lectures))
            elements.append(r)
        resultat_docs.append({
            "id": doc["id"], "nom": doc["nom"], "condition": doc.get("condition"), "optionnel": doc.get("optionnel"),
            "fondement": doc.get("fondement"),
            "piece": {"code": piece.code, "numero": piece.numero, "nom": piece.nom, "statut": piece.statut,
                      "recu": bool(piece.fichier_recu), "nature": piece.nature},
            "elements": elements,
        })

    resume = {k: 0 for k in (OK, KO, A_VERIFIER, EN_ATTENTE, HUMAIN_FAIT, HUMAIN_A_FAIRE)}
    for d in resultat_docs:
        for e in d["elements"]:
            resume[e["statut"]] += 1
    a_reclamer = _a_reclamer(dossier, resultat_docs)
    return {"resume": resume, "documents": resultat_docs, "a_reclamer": a_reclamer,
            "relance": _relance(dossier, a_reclamer), "checklist_version": charger()["version"]}


# Checklist : « Qu'il soit effectué par ministre de la santé » (certificat de libre vente)
AUTORITE_SANTE = re.compile(r"ministry of health|minist[eè]re de la sant|health and family welfare|CDSCO|drugs? control|"
                            r"medical products administration|NMPA|药监|药品监督管理|food and drug|\bFDA\b|MFDS|DRAP|competent authority for "
                            r"medical devices|autorit[ée] (?:sanitaire|comp[ée]tente)|Bundesinstitut|Ministero della Salute", re.I)
AUTORITE_COMMERCE = re.compile(r"ministry of commerce|minist[eè]re du commerce|foreign trade|\bDGFT\b|"
                               r"chamber of commerce|chambre de commerce|CCPIT", re.I)
SANS_LICENCE = re.compile(r"licensed under the Drugs and Cosmetics Act[^\n]{0,200}?\bNo\b|based on declaration by", re.I | re.S)


def _autorite_sante(texte_recu: str) -> dict | None:
    """Autorité émettrice du certificat de libre vente : santé (conforme à la
    checklist) ou commerce (non conforme). None si le texte ne permet pas de trancher."""
    sante, commerce = AUTORITE_SANTE.search(texte_recu), AUTORITE_COMMERCE.search(texte_recu)
    if commerce and not sante:
        detail = (f"Délivré par une autorité du commerce (« {commerce.group(0)} »), pas par le ministère de la santé "
                  "comme l'exige la checklist : demander au fabricant le certificat de l'autorité sanitaire, ou "
                  "son certificat CE s'il en a un")
        if SANS_LICENCE.search(texte_recu):
            detail += " ; le certificat précise en outre qu'il est établi sur déclaration du fabricant / sans licence sanitaire"
        return {"statut": KO, "detail": detail, "citation": commerce.group(0)}
    if sante:
        return {"statut": OK, "detail": f"Autorité sanitaire : « {sante.group(0)} »", "citation": sante.group(0)}
    return None


def _point_lu(e: dict, champ: dict | None, lu: dict, doc: dict, dossier, piece, aujourd_hui) -> dict:
    texte = e["texte"]
    souple = bool(SI_APPLICABLE.search(texte)) or bool(doc.get("optionnel"))
    # contrôles déterministes prioritaires
    if re.search(r"ministre de la sant", texte, re.I) and piece.texte_recu:
        if (r := _autorite_sante(piece.texte_recu)) is not None:
            return r
    if re.search(r"expir|validit|non expir", texte, re.I):
        date = (lu.get("date_expiration") or lu.get("date_fin") or {}).get("valeur_normalisee")
        if date:
            try:
                fin = datetime.date.fromisoformat(date)
            except ValueError:
                fin = None
            if fin and fin < aujourd_hui:
                lettre = re.search(r"2023\s*/\s*607|confirmation letter|lettre de confirmation", piece.texte_recu or "", re.I)
                if lettre:
                    return {"statut": A_VERIFIER, "detail": f"Expiré sur le papier le {fin:%d/%m/%Y}, mais une lettre de "
                            "confirmation (règlement 2023/607) figure dans le document : vérifier la nouvelle échéance"}
                return {"statut": KO, "detail": f"Expiré le {fin:%d/%m/%Y}"}
            if fin:
                return {"statut": OK, "detail": f"Valable jusqu'au {fin:%d/%m/%Y}"}
    if re.search(r"^classe", texte, re.I) and dossier.classe:
        lue = _classe_lue(_valeur(lu, "classe_indiquee") or (champ or {}).get("valeur") or "")
        if lue:
            attendue = dossier.classe.upper()
            if lue == attendue or (lue == "I" and attendue in ("IS", "IM", "IR")):
                return {"statut": OK, "detail": f"Classe {lue} — conforme au dossier"}
            return {"statut": KO, "detail": f"Classe {lue} dans le document, {attendue} dans le dossier"}
    if champ is None:
        return {"statut": A_VERIFIER, "detail": "Point non recherché lors de la lecture : relancer la lecture du document"}
    verdict = champ.get("verification")
    if verdict == "verifie":
        return {"statut": OK, "detail": champ.get("valeur"), "citation": champ.get("citation")}
    if verdict == "absent":
        return {"statut": A_VERIFIER if souple else KO,
                "detail": "Absent du document" + (" — vérifier s'il s'applique" if souple else "")}
    return {"statut": A_VERIFIER, "detail": f"Lu : « {champ.get('valeur')} » — passage non retrouvé tel quel dans le document",
            "citation": champ.get("citation")}


def _coherence(e: dict, code: str, fabricants: dict, numero_ce: str | None, lectures: dict) -> dict:
    texte = _normaliser(e["texte"])
    constats, problemes = [], []
    propre = fabricants.get(code)
    autres = {c: v for c, v in fabricants.items() if c != code}
    if propre and autres:
        differents = [f"{v} ({c})" for c, v in autres.items() if not _meme_nom(propre, v)]
        if differents:
            problemes.append(f"Fabricant « {propre} » différent de : " + " ; ".join(differents))
        else:
            constats.append(f"même fabricant que {len(autres)} autre(s) document(s)")
    if "ce" in texte.split() or "certificat ce" in texte or "et ce" in texte:
        cite = None
        for nom, champ in lectures.get(code, {}).items():
            if champ.get("valeur") and nom in _points_numero_certificat():
                cite = champ["valeur"]
        if cite and numero_ce:
            a, b = _chiffres(cite), _chiffres(numero_ce)
            if a and b and (a in b or b in a):
                constats.append(f"n° de certificat {cite} = certificat CE")
            else:
                problemes.append(f"n° de certificat « {cite} » différent du certificat CE « {numero_ce} »")
    if problemes:
        return {"statut": KO, "detail": " ; ".join(problemes)}
    if constats:
        return {"statut": OK, "detail": "Cohérent : " + " ; ".join(constats)}
    return {"statut": A_VERIFIER, "detail": "Pas assez d'éléments lus pour comparer : à vérifier"}


def _points_numero_certificat() -> set[str]:
    """Points de la checklist qui demandent le numéro du certificat CE cité."""
    return {element_id(d["id"], i) for d in charger()["documents"] for i, e in enumerate(d["elements"])
            if re.search(r"num[eé]ro du certificat|n° de certificat", e["texte"], re.I)}


def _a_reclamer(dossier, docs: list[dict]) -> list[dict]:
    demandes = {}
    for p in dossier.documents:
        if p.nature == "a_fournir" and p.statut != "valide" and not p.fichier_recu:
            demandes[p.code] = {"piece": p.numero, "nom": p.nom, "fourni_par": p.fourni_par,
                                "raisons": ["document non reçu"]}
    for d in docs:
        if d["piece"]["nature"] != "a_fournir":
            continue
        ko = [e["texte"] for e in d["elements"] if e["statut"] == KO]
        if ko:
            entree = demandes.setdefault(d["piece"]["code"], {"piece": d["piece"]["numero"], "nom": d["piece"]["nom"],
                                                              "fourni_par": None, "raisons": []})
            entree["raisons"] += [f"« {d['nom']} » : {t}" for t in ko]
    return list(demandes.values())


def _relance(dossier, demandes: list[dict]) -> str | None:
    """Projet de message au fournisseur : préparé, jamais envoyé par le système."""
    if not demandes:
        return None
    lignes = [f"Objet : dossier d'enregistrement au Maroc — {dossier.produit}", "",
              "Bonjour,", "",
              "Pour compléter le dossier d'enregistrement de ce dispositif auprès de l'AMMPS (Maroc), "
              "merci de nous transmettre les documents suivants :", ""]
    for d in demandes:
        numero = f"pièce {d['piece']} — " if d["piece"] else ""
        lignes.append(f"- {numero}{d['nom']}")
        lignes += [f"    • {r}" for r in d["raisons"] if r != "document non reçu"]
    lignes += ["", "Les documents en langue étrangère doivent pouvoir être traduits ; merci d'indiquer s'ils sont "
               "légalisés ou apostillés.", "", "Cordialement,"]
    return "\n".join(lignes)
