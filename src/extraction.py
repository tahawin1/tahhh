"""
Lecture des documents reçus du fournisseur (pièces `a_fournir`) :
certificat NMPA / CDSCO / CE, ISO 13485, bulletin d'analyse…

1. le texte est extrait du fichier (texte natif, ou OCR pour un scan/une photo) ;
2. Mistral retrouve chaque champ déclaré dans les règles YAML
   (`champs_a_extraire`) et recopie la phrase du document qui le justifie ;
3. le CODE vérifie que cette citation existe vraiment dans le document et
   que la valeur figure dans la citation. Sinon le champ est marqué
   « non vérifié » : une valeur que l'on ne retrouve pas dans le document
   n'est jamais présentée comme sûre.

Le résultat est une aide à la vérification humaine : il ne valide rien.
"""
from __future__ import annotations

import datetime
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import requests

from embeddings import OLLAMA_BASE_URL

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "900"))
LANGUES_OCR_RECUS = os.environ.get("LANGUES_OCR_RECUS", "fra+eng")
MAX_CARACTERES = 12000  # un certificat tient en 1 à 3 pages
# Champs demandés à Mistral par appel : 30 champs d'un coup (règles + checklist)
# dépassaient 15 min sur une machine lente et dégradaient les réponses de
# Mistral 7B (essai Jenkins du 2026-10-02). Les champs des règles passent en
# premier ; la checklist suit par paquets.
CHAMPS_PAR_APPEL = int(os.environ.get("CHAMPS_PAR_APPEL", "10"))
EXTENSIONS_ACCEPTEES = {".pdf", ".png", ".jpg", ".jpeg"}

# Verdicts du contrôle d'un champ
VERIFIE = "verifie"                      # citation retrouvée dans le document, valeur incluse
CITATION_INTROUVABLE = "citation_introuvable"  # citation absente du document : possible invention
VALEUR_HORS_CITATION = "valeur_hors_citation"  # la valeur n'apparaît pas dans la citation fournie
ABSENT = "absent"                        # l'IA indique que l'information n'est pas dans le document


class ExtractionImpossible(RuntimeError):
    pass


# ---------------------------------------------------------------- lecture du fichier


def lire_document(chemin: Path) -> str:
    """Texte du document : natif pour un PDF texte, OCR pour un scan ou une image."""
    extension = chemin.suffix.lower()
    if extension not in EXTENSIONS_ACCEPTEES:
        raise ExtractionImpossible(f"Format non pris en charge : {extension} (acceptés : PDF, PNG, JPG).")
    if extension == ".pdf":
        from ingest import extraire_texte

        texte = extraire_texte(chemin, langues_ocr=LANGUES_OCR_RECUS)
    else:
        import pytesseract
        from PIL import Image

        texte = pytesseract.image_to_string(Image.open(chemin), lang=LANGUES_OCR_RECUS)
    texte = texte.strip()
    if len(texte) < 20:
        raise ExtractionImpossible("Aucun texte lisible dans le document (scan illisible ou image vide).")
    return texte


# ---------------------------------------------------------------- contrôle des citations


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, ponctuation typographique unifiée, espaces réduits."""
    t = unicodedata.normalize("NFKD", texte)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}))
    return re.sub(r"\s+", " ", t).strip()


def _mots(texte: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normaliser(texte))


def citation_trouvee(citation: str, texte: str) -> bool:
    """La citation figure-t-elle dans le texte ? Exact après normalisation,
    ou à 85 % des mots dans l'ordre et sur un passage compact (tolère les
    petites erreurs d'OCR sans accepter des mots piochés dans tout le document)."""
    if not citation or not citation.strip():
        return False
    if normaliser(citation) in normaliser(texte):
        return True
    mots_citation, mots_texte = _mots(citation), _mots(texte)
    if len(mots_citation) < 3:
        return False
    blocs = SequenceMatcher(None, mots_texte, mots_citation, autojunk=False).get_matching_blocks()
    blocs = [b for b in blocs if b.size]
    if not blocs:
        return False
    couverts = sum(b.size for b in blocs)
    etendue = blocs[-1].a + blocs[-1].size - blocs[0].a
    return couverts / len(mots_citation) >= 0.85 and etendue <= 2 * len(mots_citation) + 3


def valeur_dans_citation(valeur: str, citation: str) -> bool:
    v, c = _mots(valeur), " ".join(_mots(citation))
    return bool(v) and " ".join(v) in c


# ---------------------------------------------------------------- dates

MOIS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def normaliser_date(valeur: str | None) -> str | None:
    """'12/03/2024', '2024-03-12', '12 mars 2024', 'March 12, 2024', '2024年3月12日'
    -> '2024-03-12'. Retourne None si la date est ambiguë ou illisible."""
    if not valeur:
        return None
    v = normaliser(valeur)
    candidats = []
    if m := re.search(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", valeur):
        candidats.append((int(m[1]), int(m[2]), int(m[3])))
    elif m := re.search(r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})", v):
        candidats.append((int(m[3]), int(m[2]), int(m[1])))  # convention jour/mois/année
    elif m := re.search(r"(\d{1,2})(?:er)?\s+([a-z]+)\.?,?\s+(\d{4})", v):
        if m[2] in MOIS:
            candidats.append((int(m[3]), MOIS[m[2]], int(m[1])))
    elif m := re.search(r"([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", v):
        if m[1] in MOIS:
            candidats.append((int(m[3]), MOIS[m[1]], int(m[2])))
    for annee, mois, jour in candidats:
        try:
            return datetime.date(annee, mois, jour).isoformat()
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- extraction par Mistral


def _schema(champs: list[dict]) -> dict:
    """Schéma JSON imposé à la réponse de Mistral (sortie structurée d'Ollama)."""
    entree = {
        "type": "object",
        "properties": {"valeur": {"type": ["string", "null"]}, "citation": {"type": ["string", "null"]}},
        "required": ["valeur", "citation"],
    }
    return {"type": "object", "properties": {c["nom"]: entree for c in champs}, "required": [c["nom"] for c in champs]}


def interroger_mistral(texte: str, champs: list[dict], piece: str) -> dict:
    liste = "\n".join(f"- {c['nom']} : {c['description']}" for c in champs)
    prompt = f"""Tu lis un document reçu d'un fournisseur de dispositifs médicaux. Il est censé être : {piece}.

DOCUMENT (texte extrait, éventuellement par OCR) :
<<<
{texte[:MAX_CARACTERES]}
>>>

Pour chaque champ ci-dessous, retrouve l'information DANS CE DOCUMENT :
{liste}

Règles strictes :
- "valeur" : l'information exactement telle qu'elle est écrite dans le document (même langue, même format de date).
- "citation" : le passage du document, recopié mot pour mot (au plus 200 caractères), qui contient cette valeur.
- Si l'information n'est pas dans le document : "valeur": null et "citation": null. Ne devine jamais, ne complète jamais.
Réponds uniquement avec l'objet JSON demandé."""

    session = requests.Session()
    session.trust_env = False  # Ollama est local
    try:
        # Une erreur 500 passagère d'Ollama est relancée une fois (voir generate.py).
        for tentative in (1, 2):
            r = session.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": _schema(champs),
                    # ~80 jetons par champ (valeur + citation) : la checklist ajoute jusqu'à 30 points par pièce
                    "options": {"temperature": 0, "num_ctx": 8192, "num_predict": max(1200, 90 * len(champs))},
                },
                timeout=OLLAMA_TIMEOUT,
            )
            if r.status_code < 500 or tentative == 2:
                break
            time.sleep(5)
        if r.status_code >= 500:
            raise ExtractionImpossible(
                f"Mistral a échoué deux fois (erreur {r.status_code} d'Ollama) — relancer la lecture."
            )
        r.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise ExtractionImpossible(f"Ollama n'est pas démarré sur {OLLAMA_BASE_URL}.") from e
    except requests.exceptions.Timeout as e:
        raise ExtractionImpossible(f"Mistral n'a pas répondu en {OLLAMA_TIMEOUT}s.") from e
    import json

    try:
        return json.loads(r.json()["response"])
    except (ValueError, KeyError) as e:
        raise ExtractionImpossible("Réponse de Mistral illisible (JSON invalide).") from e


def controler(reponse: dict, champs: list[dict], texte: str) -> list[dict]:
    """Confronte chaque valeur proposée par Mistral au texte réel du document."""
    resultats = []
    for c in champs:
        brut = reponse.get(c["nom"]) or {}
        valeur = (brut.get("valeur") or "").strip() or None
        citation = (brut.get("citation") or "").strip() or None
        if valeur is None:
            verdict = ABSENT
        elif not citation_trouvee(citation or "", texte):
            verdict = CITATION_INTROUVABLE
        elif not valeur_dans_citation(valeur, citation):
            verdict = VALEUR_HORS_CITATION
        else:
            verdict = VERIFIE
        resultats.append({
            "nom": c["nom"],
            "libelle": c["libelle"],
            "type": c.get("type", "texte"),
            "valeur": valeur,
            "valeur_normalisee": normaliser_date(valeur) if c.get("type") == "date" else valeur,
            "citation": citation,
            "verification": verdict,
        })
    return resultats


def extraire(chemin: Path, champs: list[dict], piece: str) -> dict:
    """Pipeline complet pour un document reçu. Lève ExtractionImpossible si
    le document est illisible ou si le premier paquet (champs des règles)
    échoue ; un paquet suivant (points de la checklist) en échec n'efface
    pas ce qui a été lu : ses champs sont marqués absents et signalés."""
    if not champs:
        raise ExtractionImpossible("Aucun champ à extraire n'est déclaré pour cette pièce dans les règles.")
    texte = lire_document(chemin)
    resultats, incomplet = [], []
    paquets = [champs[i:i + CHAMPS_PAR_APPEL] for i in range(0, len(champs), CHAMPS_PAR_APPEL)]
    for rang, paquet in enumerate(paquets):
        try:
            resultats += controler(interroger_mistral(texte, paquet, piece), paquet, texte)
        except ExtractionImpossible as e:
            if rang == 0:
                raise
            incomplet.append(str(e))
            resultats += controler({}, paquet, texte)  # absents : rien n'est inventé
    return {
        "champs": resultats,
        "resume": {v: sum(1 for r in resultats if r["verification"] == v)
                   for v in (VERIFIE, CITATION_INTROUVABLE, VALEUR_HORS_CITATION, ABSENT)},
        "caracteres_lus": len(texte),
        "texte": texte,
        "modele": OLLAMA_MODEL,
        "appels": len(paquets),
        **({"incomplet": f"{len(incomplet)} paquet(s) de champs non lu(s) : {incomplet[0]}"} if incomplet else {}),
    }
