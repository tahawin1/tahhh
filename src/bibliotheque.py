"""
Pièces du fournisseur fournies par l'AGENT depuis la base (rules/bibliotheque.yaml).

Décision de la direction : le fournisseur n'envoie que ses certificats
(certificat CE ou autorisation du pays d'origine, ISO 13485…) ; l'agent fournit
toutes les autres pièces à partir de la base :

  1. dossiers déjà traités dans l'outil (documents reçus et lus) ;
  2. dossiers déjà ACCEPTÉS par l'AMMPS (data/dossiers_valides, sur le
     serveur), fichiers rattachés aux pièces par leur numéro ; le fabricant d'un
     dossier accepté est celui que Mistral a lu dans son formulaire (mémoire,
     outil 4).

Le code décide, jamais l'IA : même fabricant (lu dans les documents ou saisi
comme fournisseur), même produit pour les pièces propres au produit, document
non expiré. Le document est le document réel du fabricant, jamais rédigé ni
modifié : il est relu par Mistral, contrôlé par la checklist et validé par une
personne comme toute pièce. Origine tracée (colonne `origine_recu`, journal).
"""
from __future__ import annotations

import datetime
import re
import shutil
from functools import lru_cache
from pathlib import Path

import yaml

from memoire import fabricant_cle
from rule_engine import RULES_DIR

CHAMPS_FABRICANT = ("fabricant", "titulaire")
NUMERO = re.compile(r"^\s*(\d{1,2})\s*[-_. ]")
CLASSE_DANS_LE_NOM = re.compile(r"[(\[\-–]\s*(?:classe\s*)?(I|Is|Im|Ir|IIa|IIb|III)\s*[)\]]?\s*$", re.I)


@lru_cache(maxsize=1)
def politique() -> dict:
    with open(RULES_DIR / "bibliotheque.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def portee(code: str) -> str | None:
    """« commun », « meme_fabricant », « meme_produit », ou None (toujours du fournisseur)."""
    p = politique()
    if any(code == c or code.startswith(c) for c in p["toujours_du_fournisseur"]):
        return None
    for portee_, codes in p["depuis_la_base"].items():
        if code in codes:
            return portee_
    return None


def _mots(texte: str) -> set[str]:
    from memoire import _cle

    return {m for m in _cle(CLASSE_DANS_LE_NOM.sub("", texte or "")).split() if len(m) > 2}


def meme_produit(a: str, b: str) -> bool:
    ma, mb = _mots(a), _mots(b)
    if not ma or not mb:
        return False
    return len(ma & mb) / min(len(ma), len(mb)) >= politique()["ressemblance_produit"]


def fabricant_du_dossier(dossier) -> str:
    """Fabricant lu dans les documents reçus (sinon le fournisseur saisi)."""
    for d in dossier.documents:
        for c in (d.extraction or {}).get("champs", []) if d.extraction_statut == "terminee" else []:
            if c.get("nom") in CHAMPS_FABRICANT and c.get("valeur") and (cle := fabricant_cle(c["valeur"])):
                return cle
    return fabricant_cle(getattr(dossier, "fournisseur", None))


def valide(doc, aujourd_hui: datetime.date | None = None) -> bool:
    """Non expiré d'après la date lue par l'agent ; expiré mais accompagné d'une
    lettre 2023/607 : repris (le contrôle de la checklist le signalera)."""
    aujourd_hui = aujourd_hui or datetime.date.today()
    for c in (doc.extraction or {}).get("champs", []):
        if c.get("nom") in ("date_expiration", "date_validite") and c.get("valeur_normalisee"):
            try:
                if datetime.date.fromisoformat(c["valeur_normalisee"]) < aujourd_hui:
                    return "2023/607" in (doc.texte_recu or "")
            except ValueError:
                pass
    return True


# ------------------------------------------------------------------ sources


def _depuis_dossiers(piece, dossier, fabricant: str, precedents: list, aujourd_hui):
    """Pièce équivalente d'un dossier déjà traité (lue, non rejetée, non expirée)."""
    p = portee(piece.code)
    for autre in precedents:
        if autre.id == dossier.id:
            continue
        if p != "commun":
            # même fabricant, quel que soit le pays choisi pour le dossier (un fabricant chinois marqué CE
            # a pu être saisi « Chine » une fois, « Union européenne » une autre)
            if not fabricant or fabricant_du_dossier(autre) != fabricant:
                continue
            if p == "meme_produit" and not meme_produit(dossier.produit, autre.produit):
                continue
        source = next((d for d in autre.documents if d.code == piece.code and d.fichier_recu
                       and Path(d.fichier_recu).exists() and d.extraction_statut == "terminee"
                       and d.statut != "rejete" and valide(d, aujourd_hui)), None)
        if source:
            return {"fichiers": [Path(source.fichier_recu)], "nom": source.nom_fichier_recu, "source": source,
                    "origine": f"base : dossier n°{source.dossier_id} ({autre.produit})"}
    return None


def dossiers_acceptes(racine: Path | None = None) -> list[dict]:
    """Dossiers acceptés sur le serveur : pays, produit, fabricant (mémoire), fichiers par numéro."""
    import memoire
    import preuve

    racine = racine or memoire.RACINE_DEFAUT
    appris = {(e.get("pays"), e.get("produit")): e for e in memoire.charger()}
    trouves = []
    if not racine.is_dir():
        return trouves
    for pays_dir in sorted(p for p in racine.iterdir() if p.is_dir()):
        for produit_dir in sorted(p for p in pays_dir.iterdir() if p.is_dir()):
            fichiers: dict[int, list[Path]] = {}
            for f in sorted(produit_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg") and (m := NUMERO.match(f.name)):
                    fichiers.setdefault(int(m.group(1)), []).append(f)
            produit, classe = memoire.produit_et_classe(produit_dir.name)
            entree = appris.get((pays_dir.name, produit)) or appris.get((pays_dir.name, produit_dir.name)) or {}
            trouves.append({"pays": pays_dir.name, "produit": produit_dir.name, "classe": classe, "fichiers": fichiers,
                            "preuve": preuve.preuve_de_fichiers(fichiers.get(4, [])),
                            "fabricant": fabricant_cle(entree.get("fabricant")),
                            "fabricant_nom": entree.get("fabricant")})
    return trouves


def _depuis_acceptes(piece, dossier, fabricant: str, acceptes: list[dict]):
    """Fichier(s) de la même pièce (même numéro) d'un dossier accepté du même fabricant."""
    if piece.numero is None:
        return None
    p = portee(piece.code)
    for acc in acceptes:
        if not fabricant or acc["fabricant"] != fabricant:
            continue
        if p == "meme_produit" and not meme_produit(dossier.produit, acc["produit"]):
            continue
        if fichiers := acc["fichiers"].get(piece.numero):
            return {"fichiers": fichiers, "nom": fichiers[0].name if len(fichiers) == 1 else f"{len(fichiers)} fichiers",
                    "source": None, "origine": f"base : dossier accepté « {acc['produit']} »"}
    return None


def candidats(dossier, precedents: list, acceptes: list[dict] | None = None,
              aujourd_hui: datetime.date | None = None) -> dict[int, dict]:
    """{id de la pièce : origine à reprendre} pour les pièces du fournisseur
    encore vides que la politique confie à la base. Dossiers traités d'abord
    (déjà lus), puis dossiers acceptés."""
    fabricant = fabricant_du_dossier(dossier)
    acceptes = dossiers_acceptes() if acceptes is None else acceptes
    choix = {}
    for piece in dossier.documents:
        if piece.nature != "a_fournir" or piece.fichier_recu or piece.statut == "valide" or portee(piece.code) is None:
            continue
        trouve = _depuis_dossiers(piece, dossier, fabricant, precedents, aujourd_hui) \
            or _depuis_acceptes(piece, dossier, fabricant, acceptes)
        if trouve:
            choix[piece.id] = trouve
    return choix


def reprendre(dossier, precedents: list, acceptes: list[dict] | None = None,
              aujourd_hui: datetime.date | None = None) -> list[tuple[object, dict, bool]]:
    """Joint au dossier les pièces fournies par la base ; retourne
    [(pièce, origine, à relire)]. Une lecture déjà faite est reprise si elle
    couvre les champs demandés ; sinon (ou fichier d'un dossier accepté) la
    pièce est mise en file de lecture (l'appelant la soumet, journalise et
    enregistre)."""
    import classement
    from db import maintenant

    faits = []
    choix = candidats(dossier, precedents, acceptes, aujourd_hui)
    for piece in dossier.documents:
        if not (trouve := choix.get(piece.id)):
            continue
        fichiers = trouve["fichiers"]
        dossier_recus = Path(dossier.dossier_sortie) / "recus"
        dossier_recus.mkdir(parents=True, exist_ok=True)
        if len(fichiers) == 1:
            chemin = dossier_recus / f"{piece.code}_base{fichiers[0].suffix.lower()}"
            shutil.copyfile(fichiers[0], chemin)
        else:  # plusieurs fichiers d'une même pièce (étiquettes) : réunis en un PDF
            _, extension, contenu = classement.reunir([(f.name, f.suffix.lower(), f.read_bytes()) for f in fichiers])
            chemin = dossier_recus / f"{piece.code}_base{extension}"
            chemin.write_bytes(contenu)
        piece.fichier_recu = str(chemin)
        piece.nom_fichier_recu = trouve["nom"]
        piece.origine_recu = trouve["origine"][:300]
        piece.recu_le = maintenant()
        piece.extraction_erreur = None
        source = trouve["source"]
        lus = {c.get("nom") for c in ((source.extraction or {}) if source else {}).get("champs", [])}
        demandes = {c["nom"] for c in piece.champs_a_extraire or []}
        a_relire = bool(demandes) and (source is None or not demandes <= lus)
        if not demandes:  # photos, déclaration : rien à lire
            piece.extraction, piece.texte_recu, piece.extraction_statut = None, None, None
        elif a_relire:
            piece.extraction, piece.texte_recu, piece.extraction_statut = None, None, "en_file"
        else:
            piece.texte_recu = source.texte_recu
            piece.extraction = {**(source.extraction or {}), "repris_du_dossier": source.dossier_id}
            piece.extraction_statut = "terminee"
        faits.append((piece, trouve, a_relire))
    return faits
