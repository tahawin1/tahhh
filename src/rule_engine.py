"""
Moteur de règles réglementaires — décide quels documents sont requis.

Principe non négociable (voir CLAUDE.md) : cette logique est déterministe,
codée à partir des fichiers YAML dans rules/, et ne dépend JAMAIS du LLM.
Le LLM n'intervient qu'ensuite pour rédiger le contenu de chaque document.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


@dataclass
class DocumentRequis:
    id: str
    nom: str
    traduction_requise: bool = False
    legalisation_requise: bool = False
    origine_regle: str = ""  # pour la traçabilité : quelle règle a produit cette exigence


def charger_regles(pays: str) -> dict:
    """Charge le fichier YAML de règles pour un pays donné."""
    chemin = RULES_DIR / f"{pays}.yaml"
    if not chemin.exists():
        raise ValueError(f"Aucune règle trouvée pour le pays '{pays}' ({chemin} manquant)")
    with open(chemin, encoding="utf-8") as f:
        return yaml.safe_load(f)


def documents_requis_maroc(pays_origine_produit: str, classe: str | None = None) -> list[DocumentRequis]:
    """
    Cas A du projet : dossier destiné au Maroc, produit venant d'un pays
    étranger (chine / inde / union_europeenne / autre).
    """
    regles = charger_regles("maroc")
    documents: list[DocumentRequis] = []

    for doc in regles["socle_commun"]:
        # Comparaison exacte sur la liste YAML `classes_concernees` (le champ
        # `condition` n'est qu'un libellé : un test de sous-chaîne dessus
        # faisait passer la classe "I" dans "classes IIA, IIB, III").
        # Classe inconnue -> document conservé (choix prudent).
        classes = doc.get("classes_concernees")
        if classes and classe and classe not in classes:
            continue  # ex: ISO 13485 seulement pour IIA/IIB/III
        documents.append(DocumentRequis(id=doc["id"], nom=doc["nom"], origine_regle="socle_commun"))

    piece = regles["piece_specifique_selon_origine"].get(pays_origine_produit)
    if piece is None:
        piece = regles["piece_specifique_selon_origine"]["autre"]

    documents.append(
        DocumentRequis(
            id=f"piece_specifique_{pays_origine_produit}",
            nom=piece["document"],
            traduction_requise=piece.get("traduction_requise", False),
            legalisation_requise=piece.get("legalisation_requise", False),
            origine_regle=f"piece_specifique_selon_origine.{pays_origine_produit}",
        )
    )
    return documents


def prochain_creneau_depot(pays: str = "maroc", depuis: datetime.date | None = None) -> datetime.date:
    """
    Retourne la prochaine date de dépôt physique possible.
    Pour le Maroc : mercredi et jeudi uniquement (règle DMP).
    """
    regles = charger_regles(pays)
    jours_fr = {
        "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
        "vendredi": 4, "samedi": 5, "dimanche": 6,
    }
    jours_autorises = {jours_fr[j] for j in regles["contraintes_operationnelles"]["jours_depot_physique"]}

    date_courante = depuis or datetime.date.today()
    for i in range(14):
        candidate = date_courante + datetime.timedelta(days=i)
        if candidate.weekday() in jours_autorises:
            return candidate
    raise RuntimeError("Aucun créneau de dépôt trouvé dans les 14 prochains jours — vérifier les règles.")


def resume_regles_pays(pays: str) -> str:
    """Résumé humain des règles d'un pays, utile pour vérification rapide."""
    regles = charger_regles(pays)
    lignes = [
        f"Pays : {regles['pays']}",
        f"Autorité : {regles['autorite']}",
        f"Classification : {', '.join(regles['classification'])}",
    ]
    for note in regles.get("notes", []):
        lignes.append(f"- {note}")
    return "\n".join(lignes)


if __name__ == "__main__":
    # Démonstration rapide en ligne de commande
    for pays_origine in ["chine", "inde", "union_europeenne", "autre"]:
        print(f"\n=== Dossier Maroc — fournisseur : {pays_origine} ===")
        for doc in documents_requis_maroc(pays_origine, classe="IIB"):
            flags = []
            if doc.traduction_requise:
                flags.append("traduction requise")
            if doc.legalisation_requise:
                flags.append("légalisation requise")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            print(f"  - {doc.nom}{suffix}")

    print(f"\nProchain créneau de dépôt (Maroc) : {prochain_creneau_depot()}")
