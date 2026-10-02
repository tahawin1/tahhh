"""
Bibliothèque fournisseur : les documents déjà reçus d'un fabricant servent aux
dossiers suivants, tant qu'ils sont valides — moins de documents à réclamer.

Seules les pièces qui ne dépendent pas du produit sont reprises :
certificat ISO 13485, certificat CE / autorisation du pays d'origine (avec sa
lettre de confirmation), attestation du fabricant, catalogue ; et la
déclaration de l'établissement importateur (la même pour tous les dossiers).
La déclaration de conformité, les étiquettes, la notice et les photos sont
propres au produit : elles restent à fournir pour chaque dossier.

Décisions prises par le code (jamais par l'IA) : même fabricant (lu dans les
documents ou saisi comme fournisseur), même pays d'origine, document lu par
l'agent et non expiré (sauf lettre 2023/607 : « à vérifier » par les
contrôles). Une pièce reprise n'est jamais validée d'office : elle reste à
relire et à valider par une personne, comme une pièce reçue.
"""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path

from memoire import fabricant_cle

REUTILISABLES = ("iso_13485", "piece_specifique", "attestation_fabricant", "catalogue")
SANS_FABRICANT = ("declaration_etablissement",)  # pièce de l'importateur, commune à tous les dossiers
CHAMPS_FABRICANT = ("fabricant", "titulaire")


def _reutilisable(code: str) -> bool:
    return code in SANS_FABRICANT or any(code == r or code.startswith(r) for r in REUTILISABLES)


def fabricant_du_dossier(dossier) -> str:
    """Fabricant lu dans les documents reçus (sinon le fournisseur saisi)."""
    for d in dossier.documents:
        for c in (d.extraction or {}).get("champs", []) if d.extraction_statut == "terminee" else []:
            if c.get("nom") in CHAMPS_FABRICANT and c.get("valeur") and (cle := fabricant_cle(c["valeur"])):
                return cle
    return fabricant_cle(getattr(dossier, "fournisseur", None))


def valide(doc, aujourd_hui: datetime.date | None = None) -> bool:
    """Non expiré d'après la date lue par l'agent ; un certificat expiré
    accompagné d'une lettre 2023/607 est repris (le contrôle le signalera)."""
    aujourd_hui = aujourd_hui or datetime.date.today()
    for c in (doc.extraction or {}).get("champs", []):
        if c.get("nom") == "date_expiration" and c.get("valeur_normalisee"):
            try:
                if datetime.date.fromisoformat(c["valeur_normalisee"]) < aujourd_hui:
                    return "2023/607" in (doc.texte_recu or "")
            except ValueError:
                pass
    return True


def candidats(dossier, precedents: list, aujourd_hui: datetime.date | None = None) -> dict[int, object]:
    """{id de la pièce du dossier : pièce d'un dossier précédent à reprendre}.
    `precedents` : autres dossiers, du plus récent au plus ancien."""
    fabricant = fabricant_du_dossier(dossier)
    choix = {}
    for piece in dossier.documents:
        if piece.nature != "a_fournir" or piece.fichier_recu or piece.statut == "valide" or not _reutilisable(piece.code):
            continue
        for autre in precedents:
            if autre.id == dossier.id or autre.pays_origine != dossier.pays_origine and piece.code not in SANS_FABRICANT:
                continue
            if piece.code not in SANS_FABRICANT and (not fabricant or fabricant_du_dossier(autre) != fabricant):
                continue
            source = next((d for d in autre.documents if d.code == piece.code and d.fichier_recu
                           and Path(d.fichier_recu).exists() and d.extraction_statut == "terminee"
                           and d.statut != "rejete" and valide(d, aujourd_hui)), None)
            if source:
                choix[piece.id] = source
                break
    return choix


def reprendre(dossier, precedents: list, aujourd_hui: datetime.date | None = None) -> list[tuple[object, object, bool]]:
    """Copie les documents repris dans le dossier (fichier, texte, lecture) ;
    retourne [(pièce, source, à relire)]. La lecture est reprise telle quelle si
    elle couvre tous les champs demandés aujourd'hui pour la pièce ; sinon la
    pièce est remise en file de lecture (à relire = True, l'appelant la soumet).
    L'appelant journalise et enregistre."""
    from db import maintenant

    faits = []
    choix = candidats(dossier, precedents, aujourd_hui)
    for piece in dossier.documents:
        if not (source := choix.get(piece.id)):
            continue
        chemin = Path(dossier.dossier_sortie) / "recus" / f"{piece.code}_repris_{source.dossier_id}{Path(source.fichier_recu).suffix}"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source.fichier_recu, chemin)
        piece.fichier_recu = str(chemin)
        piece.nom_fichier_recu = source.nom_fichier_recu
        piece.recu_le = maintenant()
        piece.texte_recu = source.texte_recu
        piece.extraction_erreur = None
        lus = {c.get("nom") for c in (source.extraction or {}).get("champs", [])}
        demandes = {c["nom"] for c in piece.champs_a_extraire or []}
        a_relire = not demandes <= lus
        if a_relire:
            piece.extraction, piece.extraction_statut = None, "en_file"
        else:
            piece.extraction = {**(source.extraction or {}), "repris_du_dossier": source.dossier_id}
            piece.extraction_statut = "terminee"
        faits.append((piece, source, a_relire))
    return faits
