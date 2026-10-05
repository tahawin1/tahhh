"""
Mémoire des dossiers acceptés : ce que Mistral apprend une fois pour toutes.

Pour chaque dossier accepté (data/dossiers_valides/, jamais versionné), Mistral
lit la fiche signalétique (pièce 2) et le certificat de l'annexe II (pièce 16)
tels qu'ils ont été déposés et acceptés, et en relève les données du dispositif
(présentation, indications, domaine thérapeutique, composition, références,
coordonnées du fabricant…). Chaque valeur est confrontée au texte du document
par le code : une valeur introuvable dans le document n'est pas retenue.

Le résultat est écrit dans output/memoire/ (sur le serveur, sauvegardé avec
les dossiers). Pour un nouveau dossier du MÊME FABRICANT, les formulaires
reprennent ces valeurs quand les documents du fournisseur ne les donnent pas,
toujours marquées « à confirmer » : moins de documents à réclamer, jamais de
valeur inventée, et la relecture humaine reste obligatoire.

    python src/memoire.py                 # apprend de data/dossiers_valides
    python src/memoire.py --liste         # ce qui a été appris
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import unicodedata
from pathlib import Path

RACINE_DEFAUT = Path(__file__).resolve().parent.parent / "data" / "dossiers_valides"
DOSSIER_MEMOIRE = Path(os.environ.get("MEMOIRE_DIR", Path(__file__).resolve().parent.parent / "output" / "memoire"))
NUMERO_FICHIER = re.compile(r"^\s*(\d{1,2})\s*[-_. ]")
PIECES_LUES = (2, 16)  # fiche signalétique, certificat de l'annexe II

# Données relevées dans les formulaires acceptés. Les cases à cocher (type de
# DM, « contient du latex » oui/non…) ne sont pas lues : le texte d'un PDF ne
# dit pas quelle case est cochée.
CHAMPS_APPRIS = {
    "nom_marque": "nom de marque / nom(s) commercial(aux) du dispositif",
    "categorie": "catégorie du dispositif médical",
    "code_classification": "code GMDN, EMDN ou Cladimed",
    "presentation": "présentation (conditionnement) du dispositif",
    "indications": "indications du dispositif, texte complet",
    "domaine_therapeutique": "domaine thérapeutique",
    "duree_validite": "durée de validité (péremption)",
    "conservation": "conditions de conservation",
    "sterilisation": "dispositif stérile : méthode de stérilisation",
    "composition": "composition : éléments et matériaux constitutifs",
    "fabricant_nom": "nom de l'établissement de fabrication",
    "fabricant_adresse": "adresse de l'établissement de fabrication",
    "fabricant_contact": "téléphone, fax et adresse électronique du fabricant",
    "references": ("liste des références de l'annexe : une ligne par produit, au format "
                   "« MARQUE | NOM COMMERCIAL | RÉFÉRENCE »"),
}


CLASSE_DANS_LE_NOM = re.compile(r"\s*[(\[\-–]\s*(?:classe\s*)?(I|Is|Im|Ir|IIa|IIb|III)\s*[)\]]?\s*$", re.I)


def produit_et_classe(nom_dossier: str) -> tuple[str, str | None]:
    """« Ciment osseux (IIb) » -> (« Ciment osseux », « IIB ») ; sans classe : (nom, None)."""
    m = CLASSE_DANS_LE_NOM.search(nom_dossier)
    if not m:
        return nom_dossier.strip(), None
    return (nom_dossier[:m.start()].strip() or nom_dossier.strip()), m.group(1).upper()


def _cle(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def fabricant_cle(nom: str | None) -> str:
    """« TECRES S.P.A. », « Tecres SpA » -> « tecres » : le premier mot significatif."""
    mots = [m for m in _cle(nom or "").split() if len(m) > 2 and m not in {"the", "les", "ltd", "spa", "gmbh", "inc"}]
    return mots[0] if mots else ""


def fichier_memoire(pays: str, produit: str) -> Path:
    return DOSSIER_MEMOIRE / f"{_cle(pays).replace(' ', '_')}__{_cle(produit).replace(' ', '_')}.json"


def formulaires_acceptes(racine: Path = RACINE_DEFAUT) -> list[dict]:
    """[{pays, produit, fichiers: {numéro: chemin}}] pour chaque dossier accepté."""
    dossiers = []
    if not racine.is_dir():
        return dossiers
    for pays_dir in sorted(p for p in racine.iterdir() if p.is_dir()):
        for produit_dir in sorted(p for p in pays_dir.iterdir() if p.is_dir()):
            fichiers = {}
            for f in sorted(produit_dir.rglob("*.pdf")):
                if (m := NUMERO_FICHIER.match(f.name)) and int(m.group(1)) in PIECES_LUES:
                    fichiers.setdefault(int(m.group(1)), f)
            if fichiers:
                # « Ciment osseux (IIb) » -> « Ciment osseux » : la classe n'est pas le nom du produit
                produit, _ = produit_et_classe(produit_dir.name)
                dossiers.append({"pays": pays_dir.name, "produit": produit, "fichiers": fichiers})
    return dossiers


def _retenir(champ: dict, texte: str) -> bool:
    """Le code ne garde que les valeurs retrouvées dans le document accepté."""
    from extraction import VERIFIE, _mots, citation_trouvee

    valeur = champ.get("valeur")
    if not valeur:
        return False
    if champ["verification"] == VERIFIE or citation_trouvee(valeur, texte):
        return True
    if champ["nom"] == "references":  # tableau reformaté : chaque cellule doit figurer dans le document
        cellules = [c.strip() for ligne in valeur.splitlines() for c in ligne.split("|") if c.strip()]
        mots = set(_mots(texte))
        return bool(cellules) and all(set(_mots(c)) <= mots for c in cellules)
    return False


def apprendre(racine: Path = RACINE_DEFAUT) -> list[dict]:
    """Fait lire par Mistral les formulaires des dossiers acceptés ; écrit la mémoire."""
    from extraction import CHAMPS_PAR_APPEL, ExtractionImpossible, _lire_paquet, lire_document

    DOSSIER_MEMOIRE.mkdir(parents=True, exist_ok=True)
    champs = [{"nom": k, "libelle": v, "description": v} for k, v in CHAMPS_APPRIS.items()]
    appris = []
    for d in formulaires_acceptes(racine):
        valeurs = {}
        for numero, chemin in sorted(d["fichiers"].items()):
            print(f"  … {d['produit']} : Mistral lit la pièce {numero} ({chemin.name}) — 1 à 5 min, patienter", flush=True)
            try:
                texte = lire_document(chemin)
            except Exception as e:  # un dossier illisible ne bloque pas les autres
                print(f"  ✗ {d['produit']} — pièce {numero} : {type(e).__name__}: {e}")
                continue
            # par paquets, comme la lecture des documents reçus : une réponse coupée
            # (JSON invalide) est relue en deux moitiés ; un paquet en échec n'efface
            # pas ce que les autres ont appris
            lus = []
            for i in range(0, len(champs), CHAMPS_PAR_APPEL):
                paquet = champs[i:i + CHAMPS_PAR_APPEL]
                try:
                    lus += _lire_paquet(texte, paquet, "formulaire accepté par l'administration "
                                        "(fiche signalétique ou certificat d'enregistrement)")
                except ExtractionImpossible as e:
                    print(f"  ! {d['produit']} — pièce {numero} : {', '.join(c['nom'] for c in paquet)} non lus ({e})")
            for c in lus:
                if c["nom"] not in valeurs and _retenir(c, texte):
                    valeurs[c["nom"]] = {"valeur": c["valeur"], "piece": numero, "fichier": chemin.name}
        if not valeurs:
            print(f"  ! {d['produit']} : aucune donnée retrouvée dans les formulaires")
            continue
        entree = {"pays": d["pays"], "produit": d["produit"],
                  "fabricant": (valeurs.get("fabricant_nom") or {}).get("valeur"),
                  "appris_le": datetime.date.today().isoformat(), "valeurs": valeurs}
        fichier_memoire(d["pays"], d["produit"]).write_text(json.dumps(entree, ensure_ascii=False, indent=1),
                                                            encoding="utf-8")
        appris.append(entree)
        print(f"  ✓ {d['produit']} ({d['pays']}) — fabricant {entree['fabricant'] or '?'} — "
              f"{len(valeurs)} donnée(s) apprise(s) : {', '.join(valeurs)}")
    return appris


def charger() -> list[dict]:
    if not DOSSIER_MEMOIRE.is_dir():
        return []
    entrees = []
    for f in sorted(DOSSIER_MEMOIRE.glob("*.json")):
        try:
            entrees.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return entrees


def pour(fabricant: str | None, pays: str, produit: str) -> dict | None:
    """Le dossier accepté du même fabricant le plus proche (même pays d'origine,
    produit le plus ressemblant). Sans fabricant connu ou sans dossier du même
    fabricant : None — on ne reprend jamais les données d'un autre fabricant."""
    cle = fabricant_cle(fabricant)
    if not cle:
        return None
    candidats = [e for e in charger() if fabricant_cle(e.get("fabricant")) == cle]
    if not candidats:
        return None
    mots = set(_cle(produit).split())
    return max(candidats, key=lambda e: (e.get("pays") == pays, len(mots & set(_cle(e.get("produit", "")).split()))))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--racine", type=Path, default=RACINE_DEFAUT)
    parser.add_argument("--liste", action="store_true", help="afficher la mémoire sans rien relire")
    args = parser.parse_args()
    if args.liste:
        for e in charger():
            print(f"{e['produit']} ({e['pays']}) — {e.get('fabricant')} — appris le {e['appris_le']} : "
                  f"{', '.join(e['valeurs'])}")
        return
    if not formulaires_acceptes(args.racine):
        print("Aucun formulaire accepté (pièces 2 ou 16) dans", args.racine)
        return
    print(f"Mistral lit les formulaires acceptés ({args.racine}) :")
    n = len(apprendre(args.racine))
    print(f"{n} dossier(s) accepté(s) appris — mémoire : {DOSSIER_MEMOIRE}")


if __name__ == "__main__":
    main()
