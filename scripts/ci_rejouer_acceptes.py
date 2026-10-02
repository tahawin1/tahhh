"""
Rejeu des dossiers ACCEPTÉS par l'AMMPS : la note réelle de l'agent.

Pour chaque dossier accepté (data/dossiers_valides/<pays>/<produit (classe)>/,
sur le serveur uniquement), l'agent refait le travail SANS le voir :
  - nouveau dossier (pays et classe tirés des noms de dossiers) ;
  - dépôt groupé des seules pièces du fournisseur (pas la lettre, ni la fiche,
    ni l'annexe II, que l'agent doit produire) ;
  - lecture par Mistral, checklist, formulaires, lettre ;
puis son résultat est comparé au dossier accepté :
  - fiche et annexe II : chaque donnée apprise du formulaire accepté
    (output/memoire, outil 4) comparée à la valeur produite ;
  - lettre : ressemblance avec la lettre acceptée.

L'API de rejeu tourne SANS mémoire (MEMOIRE_DIR vide) : l'agent ne peut pas
recopier les réponses. Aucune donnée réelle ne sort du serveur : les rapports
restent dans Jenkins.

Classe du dispositif : dans le nom du dossier produit, ex. « Ciment osseux (IIb) »,
ou dans un fichier classe.txt (« IIb ») posé dans le dossier.

    python scripts/ci_rejouer_acceptes.py --api http://127.0.0.1:8100 --cle CLE \\
        --acceptes data/dossiers_valides --memoire output/memoire --rapport rapports-ci
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

import requests

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

ACTEUR = "Jenkins (rejeu d'un dossier accepté)"
PIECES_PRODUITES = {1, 2, 16}  # lettre, fiche signalétique, annexe II : produites par l'agent
CLASSE = re.compile(r"[(\[\-–]\s*(?:classe\s*)?(I|Is|Im|Ir|IIa|IIb|III)\s*[)\]]?\s*$", re.I)
NUMERO = re.compile(r"^\s*(\d{1,2})\s*[-_. ]")


def cle(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def proche(produit: str, accepte: str) -> str:
    """juste / partiel / different, par recouvrement des mots."""
    a, b = set(cle(produit).split()), set(cle(accepte).split())
    if not a or not b:
        return "different"
    if cle(accepte) in cle(produit) or cle(produit) in cle(accepte):
        return "juste"
    commun = len(a & b) / min(len(a), len(b))
    return "juste" if commun >= 0.8 else "partiel" if commun >= 0.4 else "different"


def dossiers_acceptes(racine: Path) -> list[dict]:
    trouves = []
    for pays_dir in sorted(p for p in racine.iterdir() if p.is_dir()):
        for produit_dir in sorted(p for p in pays_dir.iterdir() if p.is_dir()):
            fichiers = {}
            for f in sorted(produit_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg") and (m := NUMERO.match(f.name)):
                    fichiers.setdefault(int(m.group(1)), []).append(f)
            m = CLASSE.search(produit_dir.name)
            classe = m.group(1).upper() if m else None
            if not classe and (f := produit_dir / "classe.txt").exists():  # autre façon de l'indiquer
                classe = f.read_text(encoding="utf-8").strip().upper() or None
            trouves.append({"pays": pays_dir.name, "produit": CLASSE.sub("", produit_dir.name).strip(),
                            "dossier": produit_dir.name, "classe": classe,
                            "fichiers": fichiers})
    return trouves


class Rejeu:
    def __init__(self, api: str, cle_api: str, delai: int):
        self.api, self.delai = api.rstrip("/"), delai
        self.http = requests.Session()
        self.http.trust_env = False
        self.http.headers["X-API-Key"] = cle_api
        self.cas: list[tuple[str, str, str | None, str | None]] = []  # dossier, contrôle, échec, ignoré
        self.bilans: list[dict] = []

    def noter(self, dossier, nom, echec=None, ignore=None):
        self.cas.append((dossier, nom, echec, ignore))
        signe = "·" if ignore else "✗" if echec else "✓"
        print(f"  {signe} [{dossier}] {nom}" + (f" — {echec or ignore}" if (echec or ignore) else ""))

    def dossier(self, ident):
        r = self.http.get(f"{self.api}/dossiers/{ident}", timeout=60)
        r.raise_for_status()
        return r.json()

    def attendre(self, ident, condition, quoi):
        fin = time.monotonic() + self.delai
        while not condition(d := self.dossier(ident)):
            if time.monotonic() > fin:
                raise TimeoutError(f"{quoi} : toujours en cours après {self.delai} s")
            time.sleep(15)
        return d

    def rejouer(self, acc: dict, memoire: dict | None):
        nom = f"{acc['pays']}/{acc['dossier']}"
        if not acc["classe"]:
            self.noter(nom, "classe du dispositif", ignore="classe absente du nom du dossier : le renommer, ex. « Ciment osseux (IIb) »")
            return
        r = self.http.post(f"{self.api}/dossiers", timeout=120, json={
            "pays_origine": acc["pays"], "produit": acc["produit"], "classe": acc["classe"], "cree_par": ACTEUR})
        r.raise_for_status()
        d = r.json()
        fournisseur = [(f.name, f) for n, fs in acc["fichiers"].items() if n not in PIECES_PRODUITES for f in fs]
        r = self.http.post(f"{self.api}/dossiers/{d['id']}/documents-recus", timeout=600, data={"acteur": ACTEUR},
                           files=[("fichiers", (n, f.read_bytes(), "application/pdf")) for n, f in fournisseur])
        r.raise_for_status()
        affectations = r.json()["affectations"]
        non_ranges = [a["fichier"] for a in affectations if a["piece"] is None]
        self.noter(nom, f"{len(fournisseur) - len(non_ranges)}/{len(fournisseur)} pièces du fournisseur rangées",
                   None if not non_ranges else f"non rangées : {non_ranges}")
        d = self.attendre(d["id"], lambda x: all(p["extraction_statut"] in (None, "terminee", "erreur")
                                                  for p in x["documents"]), "lecture")
        lus = [p for p in d["documents"] if p["extraction_statut"] == "terminee"]
        erreurs = [p["code"] for p in d["documents"] if p["extraction_statut"] == "erreur"]
        verifies = sum(1 for p in lus for c in p["extraction"]["champs"] if c["verification"] == "verifie")
        trouves = sum(1 for p in lus for c in p["extraction"]["champs"] if c["valeur"])
        self.noter(nom, f"lecture : {len(lus)} pièce(s) lue(s), {verifies}/{trouves} valeurs vérifiées dans le texte",
                   f"lecture en erreur : {erreurs}" if erreurs else None)
        bilan = {"dossier": nom, "pays": acc["pays"], "classe": acc["classe"], "pieces_lues": len(lus),
                 "valeurs_verifiees": verifies, "valeurs_trouvees": trouves}

        # formulaires comparés aux données apprises du formulaire accepté
        donnees = self.http.get(f"{self.api}/dossiers/{d['id']}/donnees-dispositif", timeout=60).json()
        produits = {c["id"]: c for s in donnees["sections"] for c in s["champs"]}
        if memoire:
            verdicts = {}
            for ident, appris in memoire["valeurs"].items():
                valeur = (produits.get(ident) or {}).get("valeur")
                verdicts[ident] = "manquant" if not valeur else proche(valeur, appris["valeur"])
            justes = sum(v == "juste" for v in verdicts.values())
            note = justes / len(verdicts)
            bilan.update(formulaire_note=round(note, 2), formulaire=verdicts)
            self.noter(nom, f"formulaires : {justes}/{len(verdicts)} données identiques au dossier accepté ({note:.0%})",
                       None if note >= 0.5 else "moins de la moitié des données retrouvées : "
                       + ", ".join(k for k, v in verdicts.items() if v != "juste"))
        else:
            self.noter(nom, "formulaires comparés au dossier accepté",
                       ignore="pas de mémoire pour ce dossier : lancer l'outil 4 (Mistral lit les formulaires acceptés)")
        bilan["cases_a_completer"] = donnees["a_completer"]

        # lettre comparée à la lettre acceptée
        lettre_acceptee = acc["fichiers"].get(1)
        d = self.attendre(d["id"], lambda x: next(p for p in x["documents"] if p["code"] == "demande_signee")["statut"]
                          not in ("a_generer", "en_file", "en_generation"), "lettre")
        lettre = next(p for p in d["documents"] if p["code"] == "demande_signee")
        if lettre["statut"] == "a_valider" and lettre_acceptee:
            from extraction import lire_document

            produite = "\n".join(p["texte"] for p in self.http.get(
                f"{self.api}/dossiers/{d['id']}/documents/{lettre['id']}/apercu", timeout=60).json()["paragraphes"])
            produite = produite.split("Sources réglementaires")[0]
            acceptee = lire_document(lettre_acceptee[0])
            ressemblance = difflib.SequenceMatcher(None, cle(produite).split(), cle(acceptee).split()).ratio()
            bilan["lettre_ressemblance"] = round(ressemblance, 2)
            self.noter(nom, f"lettre : ressemblance avec la lettre acceptée {ressemblance:.0%}",
                       None if ressemblance >= 0.6 else "lettre trop éloignée du modèle accepté")
        else:
            self.noter(nom, "lettre rédigée", f"statut {lettre['statut']} {lettre.get('erreur') or ''}"
                       if lettre["statut"] != "a_valider" else None)
        self.bilans.append(bilan)

    def rapport(self, dossier: Path):
        dossier.mkdir(parents=True, exist_ok=True)
        a = {'"': "&quot;"}
        lignes = []
        for doss, nom, echec, ignore in self.cas:
            l = f'<testcase classname="acceptes.{escape(doss, a)}" name="{escape(nom, a)}">'
            l += (f'<skipped message="{escape(ignore, a)}"/>' if ignore else
                  f'<failure message="{escape(echec, a)}"/>' if echec else "")
            lignes.append(l + "</testcase>")
        echecs = sum(1 for c in self.cas if c[2])
        (dossier / "dossiers-acceptes.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="Rejeu des dossiers acceptés" tests="{len(lignes)}" '
            f'failures="{echecs}">\n' + "\n".join(lignes) + "\n</testsuite>\n", encoding="utf-8")
        (dossier / "dossiers-acceptes.json").write_text(json.dumps(self.bilans, ensure_ascii=False, indent=1), encoding="utf-8")
        tableau = ["| Dossier | Classe | Pièces lues | Valeurs vérifiées | Formulaires | Lettre | Cases à compléter |",
                   "|---|---|---|---|---|---|---|"]
        for b in self.bilans:
            tableau.append(f"| {b['dossier']} | {b['classe']} | {b['pieces_lues']} | {b['valeurs_verifiees']}/{b['valeurs_trouvees']} | "
                           f"{b.get('formulaire_note', '—')} | {b.get('lettre_ressemblance', '—')} | {b['cases_a_completer']} |")
        (dossier / "dossiers-acceptes.md").write_text("# Rejeu des dossiers acceptés\n\n" + "\n".join(tableau) + "\n",
                                                      encoding="utf-8")
        print("\n".join(tableau))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--cle", default="")
    parser.add_argument("--acceptes", type=Path, default=RACINE / "data" / "dossiers_valides")
    parser.add_argument("--memoire", type=Path, default=RACINE / "output" / "memoire")
    parser.add_argument("--rapport", type=Path, default=RACINE / "rapports-ci")
    parser.add_argument("--delai", type=int, default=3600)
    args = parser.parse_args()
    import memoire as mem

    rejeu = Rejeu(args.api, args.cle, args.delai)
    acceptes = dossiers_acceptes(args.acceptes) if args.acceptes.is_dir() else []
    if not acceptes:
        print(f"Aucun dossier accepté dans {args.acceptes} : rien à rejouer.")
        rejeu.rapport(args.rapport)
        return 0
    print(f"Rejeu de {len(acceptes)} dossier(s) accepté(s), sans mémoire :")
    for acc in acceptes:
        fichier = args.memoire / mem.fichier_memoire(acc["pays"], acc["dossier"]).name
        appris = json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else None
        try:
            rejeu.rejouer(acc, appris)
        except Exception as e:  # un dossier en échec n'arrête pas les autres
            rejeu.noter(f"{acc['pays']}/{acc['dossier']}", "rejeu complet", f"{type(e).__name__}: {e}")
    rejeu.rapport(args.rapport)
    return 1 if any(c[2] for c in rejeu.cas) else 0


if __name__ == "__main__":
    sys.exit(main())
