"""
Formulaires officiels remplis par le code — fiche signalétique (pièce 2) et
certificat d'enregistrement de l'annexe II (pièce 16).

Mistral ne respecte pas la mise en page d'un formulaire : ces pièces ne lui
sont pas confiées. Chaque case est remplie à partir d'une source déclarée dans
rules/formulaires_maroc.yaml, dans cet ordre de priorité :

    saisie de l'utilisateur > document reçu lu par l'agent > profil de
    l'entreprise > données du dossier > autre donnée > valeur habituelle

et chaque valeur garde sa provenance, affichée à la validation. Aucune valeur
n'est inventée : sans source, la case reste [À COMPLÉTER].
"""
from __future__ import annotations

import datetime
from pathlib import Path

import yaml

from rule_engine import RULES_DIR

FICHIER = RULES_DIR / "formulaires_maroc.yaml"
A_COMPLETER = "[À COMPLÉTER]"
CLASSES = {"I": "I", "IS": "Is", "IM": "Im", "IIA": "IIa", "IIB": "IIb", "III": "III"}
MENTION_VALIDATION = (
    "PROJET GÉNÉRÉ AUTOMATIQUEMENT — EN ATTENTE DE VALIDATION HUMAINE. "
    "Ne pas déposer avant relecture et validation explicite."
)


def charger() -> dict:
    with open(FICHIER, encoding="utf-8") as f:
        return yaml.safe_load(f)


def formulaires() -> set[str]:
    """Codes des pièces remplies par le code plutôt que rédigées par Mistral."""
    return set(charger()["formulaires"])


def _lectures(documents) -> dict[str, dict]:
    """{code de pièce : {champ : champ lu}} pour les documents reçus déjà lus."""
    lectures = {}
    for d in documents:
        if d.extraction_statut == "terminee" and d.extraction:
            lectures[d.code] = {c["nom"]: {**c, "piece": d.numero, "piece_nom": d.nom}
                                for c in d.extraction.get("champs", [])}
    return lectures


def _lu(lectures: dict, code: str, champ: str) -> dict | None:
    candidats = [c for c in lectures if c == code or (code == "piece_specifique" and c.startswith("piece_specifique"))]
    for c in candidats:
        lu = lectures[c].get(champ)
        if lu and lu.get("valeur"):
            return lu
    return None


def _formater(definition: dict, valeur: str, normalisee: str | None = None) -> str:
    if definition.get("format") == "classe":
        return CLASSES.get(valeur.upper(), valeur)
    if definition.get("format") == "date" and normalisee:
        try:
            return datetime.date.fromisoformat(normalisee).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return valeur


def resoudre(dossier, profil: dict, saisies: dict | None = None) -> dict[str, dict]:
    """Valeur et provenance de chaque donnée du dispositif pour ce dossier.
    `dossier` : objet avec produit, classe, pays_origine, documents."""
    definitions = charger()["donnees"]
    saisies = (saisies if saisies is not None else getattr(dossier, "donnees_dispositif", None)) or {}
    lectures = _lectures(dossier.documents)
    contexte = {"produit": dossier.produit, "classe": dossier.classe or "", "pays_origine": dossier.pays_origine}
    resultat: dict[str, dict] = {}

    def une(ident: str, pile: tuple = ()) -> dict:
        if ident in resultat:
            return resultat[ident]
        d = definitions[ident]
        r = {"id": ident, "libelle": d["libelle"], "type": d.get("type", "texte"), "options": d.get("options"),
             "valeur": None, "provenance": "manquant", "detail": None, "a_verifier": False}
        if (saisie := (saisies.get(ident) or "").strip()):
            r.update(valeur=saisie, provenance="saisie", detail="Saisi dans le tableau de bord")
        elif dossier.pays_origine in (d.get("na_si_origine") or []):
            r.update(valeur="NA", provenance="regle", detail=f"Sans objet pour l'origine {dossier.pays_origine}")
        else:
            for source in d.get("sources") or []:
                genre, _, reste = source.partition(":")
                if genre == "dossier" and contexte.get(reste):
                    r.update(valeur=_formater(d, contexte[reste]), provenance="dossier", detail="Données du dossier")
                elif genre == "profil" and profil.get(reste):
                    r.update(valeur=profil[reste], provenance="profil", detail="Profil de l'entreprise")
                elif genre == "piece":
                    code, _, champ = reste.partition(":")
                    lu = _lu(lectures, code, champ)
                    if lu:
                        verifie = lu.get("verification") == "verifie"
                        r.update(valeur=_formater(d, lu["valeur"], lu.get("valeur_normalisee")), provenance="piece",
                                 a_verifier=not verifie,
                                 detail=f"Lu dans la pièce {lu['piece']} ({lu['piece_nom']})"
                                        + ("" if verifie else " — non vérifié dans le texte"))
                elif genre == "donnee" and reste not in pile:
                    autre = une(reste, pile + (ident,))
                    if autre["valeur"]:
                        r.update(valeur=autre["valeur"], provenance="donnee", a_verifier=autre["a_verifier"],
                                 detail=f"Repris de « {autre['libelle']} »")
                elif genre == "defaut":
                    r.update(valeur=reste, provenance="defaut", a_verifier=True,
                             detail="Valeur habituelle (dossier accepté) — à confirmer")
                if r["valeur"]:
                    break
        resultat[ident] = r
        return r

    for ident in definitions:
        une(ident)
    return resultat


# ---------------------------------------------------------------- DOCX


def _lignes_references(valeur: str | None) -> list[list[str]]:
    """« MARQUE | NOM | REF » par ligne ; une ligne sans séparateur va dans la
    colonne « Noms commerciaux »."""
    lignes = []
    for brute in (valeur or "").splitlines():
        if not brute.strip():
            continue
        parties = [p.strip() for p in brute.replace("\t", "|").split("|")]
        lignes.append((parties + ["", "", ""])[:3] if len(parties) > 1 else ["", brute.strip(), ""])
    return lignes


def _ecrire_valeur(cellule, donnee: dict) -> None:
    from docx.enum.text import WD_COLOR_INDEX

    paragraphe = cellule.paragraphs[0]
    valeur = donnee["valeur"]
    if donnee["type"] == "choix" and donnee["options"]:
        autres = valeur and valeur not in donnee["options"]
        texte = "   ".join(f"{'☒' if o == valeur else '☐'} {o}" for o in donnee["options"])
        paragraphe.add_run(texte + (f"   ☒ {valeur}" if autres else ""))
        if not valeur:
            paragraphe.add_run(f"   {A_COMPLETER}").font.highlight_color = WD_COLOR_INDEX.YELLOW
        return
    if not valeur:
        paragraphe.add_run(A_COMPLETER).font.highlight_color = WD_COLOR_INDEX.YELLOW
        return
    premiere, *suite = valeur.splitlines() or [""]
    paragraphe.add_run(premiere)
    for ligne in suite:
        cellule.add_paragraph(ligne)


def remplir_docx(code: str, donnees: dict[str, dict], titre_piece: str, chemin: Path) -> dict:
    """Écrit le formulaire `code` rempli ; retourne le bilan (cases vides, à vérifier)."""
    from docx import Document
    from docx.shared import Pt

    config = charger()["formulaires"][code]
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10)
    doc.add_heading(titre_piece, level=1)
    doc.add_paragraph().add_run(MENTION_VALIDATION).bold = True
    doc.add_heading(config["titre"], level=2)
    utilisees = []
    for section in config["sections"]:
        doc.add_heading(section["titre"], level=3)
        table = doc.add_table(rows=0, cols=2)
        table.style = "Table Grid"
        for ligne in section["lignes"]:
            ident, libelle = (next(iter(ligne.items())) if isinstance(ligne, dict) else (ligne, None))
            donnee = donnees[ident]
            utilisees.append(donnee)
            cellules = table.add_row().cells
            cellules[0].paragraphs[0].add_run(libelle or donnee["libelle"]).bold = True
            _ecrire_valeur(cellules[1], donnee)
    doc.add_paragraph()
    representant = donnees["representant_legal"]["valeur"] or A_COMPLETER
    doc.add_paragraph(config["signature"].format(representant_legal=representant))
    if config.get("partie_reservee"):
        doc.add_paragraph().add_run(config["partie_reservee"]).italic = True
    if config.get("annexe"):
        doc.add_page_break()
        titre, *suite = config["annexe"].splitlines()
        doc.add_heading(titre, level=2)
        for ligne in suite:
            doc.add_paragraph(ligne)
        references = donnees["references"]
        utilisees.append(references)
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        for cellule, entete in zip(table.rows[0].cells, ("Nom de marque", "Noms commerciaux", "Référence")):
            cellule.paragraphs[0].add_run(entete).bold = True
        lignes = _lignes_references(references["valeur"]) or [[A_COMPLETER, "", ""]]
        for ligne in lignes:
            for cellule, texte in zip(table.add_row().cells, ligne):
                cellule.paragraphs[0].add_run(texte)

    vides = [d for d in utilisees if not d["valeur"]]
    a_verifier = [d for d in utilisees if d["valeur"] and d["a_verifier"]]
    doc.add_heading("Origine des données (relecture — à retirer avant dépôt)", level=2)
    doc.add_paragraph(f"{len(utilisees) - len(vides)} case(s) remplie(s), {len(vides)} à compléter, "
                      f"{len(a_verifier)} à vérifier.")
    for d in utilisees:
        if d["valeur"] and d["provenance"] not in ("saisie",):
            marque = " — À VÉRIFIER" if d["a_verifier"] else ""
            doc.add_paragraph(f"{d['libelle']} : {d['detail']}{marque}", style="List Bullet")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    doc.save(chemin)
    return {"remplies": len(utilisees) - len(vides), "a_completer": len(vides), "a_verifier": len(a_verifier)}


def generer_formulaire(dossier, code: str, titre_piece: str, dossier_sortie: Path, profil: dict) -> dict:
    """Remplit le formulaire d'une pièce ; même forme de résultat que generate.generer_document."""
    donnees = resoudre(dossier, profil)
    chemin = dossier_sortie / f"{code}.docx"
    bilan = remplir_docx(code, donnees, titre_piece, chemin)
    regles = charger()
    return {
        "fichier": str(chemin),
        "sources": [{
            "texte_source": (f"Formulaire officiel rempli par le code (rules/formulaires_maroc.yaml v{regles['version']}) : "
                             f"{bilan['remplies']} case(s) remplie(s), {bilan['a_completer']} à compléter, "
                             f"{bilan['a_verifier']} à vérifier"),
            "date_version": regles["date_version"],
            "fichier": "rules/formulaires_maroc.yaml",
        }],
        "bilan": bilan,
    }
