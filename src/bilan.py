"""
Bilan de l'agent pour un dossier : ce que le fournisseur a envoyé, ce que
l'agent a fourni depuis la base, ce qui manque, et nos papiers à compléter.

Trois cas, décidés par le code :
  - « complet »            : le fournisseur a envoyé toutes ses pièces ; l'agent
                             donne nos papiers à compléter ;
  - « complete_par_agent » : des pièces manquaient au fournisseur ; l'agent les a
                             fournies depuis la base ; il donne ces pièces
                             complémentaires et nos papiers à compléter ;
  - « incomplet »          : il manque encore des pièces du fournisseur, absentes
                             de la base : liste et relance prête (jamais envoyée),
                             plus les pièces complémentaires et nos papiers.
Rien n'est validé ni envoyé : le bilan dit ce que l'agent a fait et ce qui
reste à faire par une personne.
"""
from __future__ import annotations

import re
from pathlib import Path

DE_NOTRE_PART = ("declaration_etablissement", "quittance_droits")  # pièces de l'établissement demandeur
PIECES_PHYSIQUES = ("echantillon_modele_vente",)
A_COMPLETER = re.compile(r"\[À COMPLÉTER")


def _cases_a_completer(fichier: str | None) -> int:
    """Cases [À COMPLÉTER] restées dans un projet rédigé (lettre, formulaires)."""
    if not fichier or not Path(fichier).exists():
        return 0
    from docx import Document

    doc = Document(fichier)
    textes = [p.text for p in doc.paragraphs] + [c.text for t in doc.tables for r in t.rows for c in r.cells]
    return sum(len(A_COMPLETER.findall(t)) for t in dict.fromkeys(textes))


def _signee_par_nous(piece) -> bool:
    return "signée" in (piece.fourni_par or "") or "signées" in (piece.fourni_par or "")


def calculer(dossier, controles: dict | None = None) -> dict:
    fournisseur, notre_part = [], []
    for p in sorted(dossier.documents, key=lambda d: (d.numero is None, d.numero or 0, d.ordre)):
        base = {"numero": p.numero, "code": p.code, "nom": p.nom, "valide": p.statut == "valide"}
        if p.nature == "a_rediger":
            if p.statut in ("a_valider", "valide") and p.fichier:
                n = _cases_a_completer(p.fichier)
                notre_part.append({**base, "etat": "redige", "par": "agent",
                                   "a_faire": "validée" if p.statut == "valide" else
                                   (f"relire et compléter {n} case(s) [À COMPLÉTER], puis valider" if n
                                    else "relire et valider")})
            else:
                notre_part.append({**base, "etat": {"en_file": "en_cours", "en_generation": "en_cours"}.get(p.statut,
                                   "erreur" if p.statut == "erreur" else "a_rediger"), "par": "agent",
                                   "a_faire": "rédaction par l'agent en cours" if p.statut in ("en_file", "en_generation")
                                   else f"rédaction en erreur : {p.erreur or 'relancer'}" if p.statut == "erreur"
                                   else "rédigée par l'agent dès la lecture des documents reçus"})
            continue
        if p.code in DE_NOTRE_PART:
            fourni = bool(p.fichier_recu)
            notre_part.append({**base, "etat": "fourni_par_agent" if p.origine_recu else "recu" if fourni else "a_fournir_par_nous",
                               "par": "agent (base)" if p.origine_recu else "nous",
                               "a_faire": ("relire et valider" if fourni else
                                           "joindre la copie de la déclaration de l'établissement et de son récépissé"
                                           if p.code == "declaration_etablissement"
                                           else "payer les droits d'enregistrement et joindre la quittance")})
            continue
        if p.code in PIECES_PHYSIQUES:  # objet remis au dépôt : ni reçu ni manquant
            fournisseur.append({**base, "etat": "a_remettre", "par": "fournisseur", "origine": None,
                                "a_faire": "objet à remettre physiquement lors du dépôt (mercredi ou jeudi)"})
            continue
        if p.fichier_recu and p.extraction_statut == "erreur":
            etat, par = "illisible", "fournisseur" if not p.origine_recu else "agent (base)"
        elif p.fichier_recu:
            etat, par = ("fourni_par_agent", "agent (base)") if p.origine_recu else ("recu", "fournisseur")
        else:
            etat, par = "manquant", "fournisseur"
        ligne = {**base, "etat": etat, "par": par, "origine": p.origine_recu,
                 "a_faire": {"recu": "relire et valider", "fourni_par_agent": "relire et valider (document de la base)",
                             "illisible": "relancer la lecture ou demander un meilleur scan",
                             "manquant": "à réclamer au fournisseur"}[etat]}
        if _signee_par_nous(p) and p.fichier_recu:  # étiquettes, notice : signées et cachetées par nous
            ligne["a_faire"] += " ; signer et cacheter par le représentant légal"
            notre_part.append({**base, "etat": "a_signer", "par": "nous", "a_faire": "signer et cacheter (représentant légal)"})
        fournisseur.append(ligne)

    manquants = [l for l in fournisseur if l["etat"] in ("manquant", "illisible")]
    par_agent = [l for l in fournisseur if l["etat"] == "fourni_par_agent"]
    if manquants:
        cas, titre = "incomplet", (f"Il manque {len(manquants)} pièce(s) du fournisseur, absentes de la base : "
                                   "relance prête ; l'agent a préparé le reste")
    elif par_agent:
        cas, titre = "complete_par_agent", (f"Le fournisseur n'a pas tout envoyé : l'agent a fourni {len(par_agent)} "
                                            "pièce(s) complémentaire(s) depuis la base")
    else:
        cas, titre = "complet", "Le fournisseur a envoyé toutes ses pièces : voici nos papiers à compléter"
    controles = controles or {}
    humains = (controles.get("resume") or {}).get("humain_a_faire", 0)
    return {
        "cas": cas,
        "titre": titre,
        "fournisseur": fournisseur,
        "complementaires": par_agent,
        "manquants": manquants,
        "notre_part": notre_part,
        "points_humains_a_cocher": humains,
        "relance": controles.get("relance") if manquants else None,
        "compteurs": {"recues": sum(l["etat"] == "recu" for l in fournisseur), "fournies_par_agent": len(par_agent),
                      "manquantes": len(manquants), "a_completer": sum(1 for l in notre_part if l["etat"] != "redige"
                                                                       or "compléter" in l["a_faire"])},
    }
