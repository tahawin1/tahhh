"""
Preuve de mise sur le marché (pièce 4) : certificat CE d'un organisme notifié,
ou certificat de l'autorité du pays du fabricant (rule_engine.PREUVES).

Le pays du fabricant et la preuve sont deux informations distinctes : un
fabricant chinois ou indien marqué CE présente son certificat CE (voie
européenne), pas un certificat NMPA ou CDSCO. L'utilisateur choisit le pays ;
la preuve est détectée par le code dans la pièce 4 reçue (texte et nom de
fichier) — jamais par Mistral — puis les pièces exigées sont recalculées par
le moteur de règles, et le changement est journalisé.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

from rule_engine import PAYS_CE, documents_requis_maroc

# Marques d'un certificat CE (organisme notifié, directive ou règlement européen)
MARQUES_CE = re.compile(
    r"notified body|organisme notifi|benannte stelle|organismo notificato|"
    r"\bE[CU][ -](?:design[- ]examination |type[- ]examination |quality (?:assurance|management) )?certificate|"
    r"certificat(?:e)? (?:de marquage )?CE\b|marquage CE|\bCE[ -]?(?:mark|certificat)|"
    r"93/42/(?:EEC|CEE|EE)|2017/745|2023/607|confirmation letter|lettre de confirmation|\bCE\s?\d{4}\b",
    re.I)
# Marques d'un certificat de l'autorité du pays (enregistrement, libre vente à l'export)
MARQUES_NATIONALES = re.compile(
    r"NMPA|国械注|药监|医疗器械|CDSCO|free sale|libre vente|foreign trade|certificate (?:for|to) foreign government|"
    r"exportation of medical|MFDS|DRAP|\bFSC\b",
    re.I)


def detecter(texte: str, noms_fichiers: list[str] | tuple[str, ...] = ()) -> str | None:
    """« ce », « nationale » ou None (rien de concluant). Le CE l'emporte : un
    dossier marqué CE joint parfois aussi une attestation de libre vente."""
    tout = f"{texte or ''}\n" + "\n".join(noms_fichiers)
    if MARQUES_CE.search(tout):
        return "ce"
    if MARQUES_NATIONALES.search(tout):
        return "nationale"
    return None


@functools.lru_cache(maxsize=256)
def _preuve_fichiers(chemins: tuple[str, ...], dates: tuple[float, ...]) -> str | None:
    import pymupdf

    textes = []
    for c in chemins:
        if c.lower().endswith(".pdf"):
            try:
                with pymupdf.open(c) as doc:  # texte seulement (pas d'OCR) : le nom de fichier complète
                    textes.append("".join(page.get_text() for page in doc)[:20000])
            except Exception:
                continue
    return detecter("\n".join(textes), [Path(c).name for c in chemins])


def preuve_de_fichiers(fichiers: list[Path]) -> str | None:
    """Preuve d'un dossier accepté, d'après sa pièce 4 (mise en cache par date de fichier)."""
    existants = [f for f in fichiers if f.exists()]
    return _preuve_fichiers(tuple(str(f) for f in existants), tuple(f.stat().st_mtime for f in existants))


def changer(session, dossier, preuve: str, acteur: str, motif: str) -> list[str]:
    """Passe le dossier sur une autre preuve : la pièce 4 change de nature
    (son document reçu est gardé et relu avec les champs de la nouvelle voie),
    les pièces liées à l'origine sont ajoutées ou retirées par le moteur de
    règles. Une pièce déjà reçue ou validée n'est jamais retirée. Journalisé.
    Retourne les identifiants des pièces à relire."""
    from db import Document, journaliser

    effective = None if dossier.pays_origine == PAYS_CE else preuve
    requis = {d.id: d for d in documents_requis_maroc(
        dossier.pays_origine, classe=dossier.classe, equipement=bool(dossier.equipement),
        valeur_usd=dossier.valeur_unitaire_usd, distributeur=bool(dossier.fournisseur_distributeur), preuve=effective)}
    ancienne = dossier.preuve
    dossier.preuve = preuve
    actuels = {d.code: d for d in dossier.documents}
    a_relire, ajoutes, retires = [], [], []

    # pièce 4 : même document, autre voie
    ancien4 = next((d for c, d in actuels.items() if c.startswith("piece_specifique_")), None)
    nouveau4 = next((d for i, d in requis.items() if i.startswith("piece_specifique_")), None)
    if ancien4 is not None and nouveau4 is not None and ancien4.code != nouveau4.id:
        del actuels[ancien4.code]
        ancien4.code, ancien4.nom, ancien4.fourni_par = nouveau4.id, nouveau4.nom, nouveau4.fourni_par
        ancien4.traduction_requise, ancien4.legalisation_requise = nouveau4.traduction_requise, nouveau4.legalisation_requise
        ancien4.origine_regle, ancien4.remarque, ancien4.source_regle = (nouveau4.origine_regle, nouveau4.remarque,
                                                                         nouveau4.source)
        ancien4.champs_a_extraire = nouveau4.champs_a_extraire
        actuels[ancien4.code] = ancien4
        if ancien4.fichier_recu:
            ancien4.extraction_statut = "en_file"
            a_relire.append(ancien4.id)

    for code, d in requis.items():
        if code not in actuels:
            doc = Document(ordre=0, code=d.id, nom=d.nom, nature=d.nature, fourni_par=d.fourni_par,
                           consigne_redaction=d.consigne_redaction, champs_a_extraire=d.champs_a_extraire,
                           traduction_requise=d.traduction_requise, legalisation_requise=d.legalisation_requise,
                           origine_regle=d.origine_regle, numero=d.numero, remarque=d.remarque, source_regle=d.source,
                           statut="a_generer" if d.a_rediger else "a_obtenir")
            dossier.documents.append(doc)
            ajoutes.append(d.nom)
    for code, doc in list(actuels.items()):
        if code not in requis and not doc.fichier_recu and not doc.fichier and doc.statut in ("a_obtenir", "a_generer"):
            dossier.documents.remove(doc)
            retires.append(doc.nom)
    # ordre du dossier déposé
    for ordre, doc in enumerate(sorted(dossier.documents, key=lambda d: d.numero if d.numero is not None else 10_000)):
        doc.ordre = ordre
    journaliser(session, dossier.id, acteur, "preuve_modifiee",
                f"Preuve de mise sur le marché : {ancienne or 'nationale'} → {preuve} ({motif})"
                + (f" ; pièces ajoutées : {', '.join(ajoutes)}" if ajoutes else "")
                + (f" ; pièces retirées : {', '.join(retires)}" if retires else ""))
    session.flush()
    return a_relire
