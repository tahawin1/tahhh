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
import signal
import sys
import time
import traceback
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
    def __init__(self, api: str, cle_api: str, delai: int, delai_lecture: int = 1800):
        self.api, self.delai, self.delai_lecture = api.rstrip("/"), delai, delai_lecture
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
        r = self.http.get(f"{self.api}/dossiers/{ident}", timeout=(10, 60))
        r.raise_for_status()
        return r.json()

    def attendre(self, ident, condition, quoi, delai: int | None = None):
        debut = time.monotonic()
        fin, signe = debut + (delai or self.delai), debut
        while not condition(d := self.dossier(ident)):
            maintenant = time.monotonic()
            if maintenant > fin:
                raise TimeoutError(f"{quoi} : toujours en cours après {int(maintenant - debut)} s")
            if maintenant - signe >= 300:  # signe de vie toutes les 5 min : où en est l'agent
                signe = maintenant
                lus = sum(p["extraction_statut"] == "terminee" for p in d["documents"])
                en_cours = [p["code"] for p in d["documents"] if p["extraction_statut"] in ("en_file", "en_cours")]
                redaction = [p["code"] for p in d["documents"] if p["statut"] in ("en_file", "en_generation")]
                print(f"    … {quoi} depuis {int((maintenant - debut) / 60)} min : {lus} pièce(s) lue(s), "
                      f"en lecture : {', '.join(en_cours) or '—'} ; en rédaction : {', '.join(redaction) or '—'}",
                      flush=True)
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
        # une photo (pièce 9) n'a rien à lire : signalée « à cocher à la main », ce n'est pas une erreur
        non_ranges = [a["fichier"] for a in affectations if a["piece"] is None and "rien à lire" not in a["raison"]]
        self.noter(nom, f"{len(fournisseur) - len(non_ranges)}/{len(fournisseur)} pièces du fournisseur rangées",
                   None if not non_ranges else f"non rangées : {non_ranges}")
        # lecture bornée : au-delà, le rejeu continue avec les pièces déjà lues (signalé, pas bloquant)
        try:
            d = self.attendre(d["id"], lambda x: all(p["extraction_statut"] in (None, "terminee", "erreur")
                                                      for p in x["documents"]), "lecture", delai=self.delai_lecture)
        except TimeoutError as e:
            d = self.dossier(d["id"])
            restantes = [p["code"] for p in d["documents"] if p["extraction_statut"] in ("en_file", "en_cours")]
            self.noter(nom, "lecture dans le temps imparti", ignore=f"{e} ; non lues : {', '.join(restantes)}")
        lus = [p for p in d["documents"] if p["extraction_statut"] == "terminee"]
        erreurs = [p["code"] for p in d["documents"] if p["extraction_statut"] == "erreur"]
        verifies = sum(1 for p in lus for c in p["extraction"]["champs"] if c["verification"] == "verifie")
        trouves = sum(1 for p in lus for c in p["extraction"]["champs"] if c["valeur"])
        self.noter(nom, f"lecture : {len(lus)} pièce(s) lue(s), {verifies}/{trouves} valeurs vérifiées dans le texte",
                   f"lecture en erreur : {erreurs}" if erreurs else None)
        bilan = {"dossier": nom, "pays": acc["pays"], "classe": acc["classe"], "pieces_lues": len(lus),
                 "valeurs_verifiees": verifies, "valeurs_trouvees": trouves}

        # preuve de mise sur le marché : l'agent l'a-t-il reconnue seul dans la pièce 4 ?
        import preuve as preuve_mod

        attendue = preuve_mod.preuve_de_fichiers(acc["fichiers"].get(4, []))
        if attendue and acc["pays"] != "union_europeenne":
            trouvee = self.dossier(d["id"])["preuve"]
            bilan["preuve"] = trouvee
            self.noter(nom, f"preuve de mise sur le marché reconnue seule : {trouvee} (dossier accepté : {attendue})",
                       None if trouvee == attendue else "preuve mal reconnue : pièces exigées différentes du dossier accepté")

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
            detail = " ; ".join(f"{v} : {', '.join(k for k, w in verdicts.items() if w == v)}"
                                for v in ("partiel", "different", "manquant") if v in verdicts.values())
            self.noter(nom, f"formulaires : {justes}/{len(verdicts)} données identiques au dossier accepté ({note:.0%})",
                       None if note >= 0.5 else f"moins de la moitié des données retrouvées — {detail}")
            for ident, v in verdicts.items():  # ce que l'agent a mis face à ce qui a été accepté
                if v != "juste":
                    print(f"      · {ident} [{v}] agent : « {str((produits.get(ident) or {}).get('valeur') or '')[:80]} » "
                          f"— accepté : « {str(memoire['valeurs'][ident]['valeur'])[:80]} »", flush=True)
        else:
            self.noter(nom, "formulaires comparés au dossier accepté",
                       ignore="pas de mémoire pour ce dossier : lancer l'outil 4 (Mistral lit les formulaires acceptés)")
        bilan["cases_a_completer"] = donnees["a_completer"]

        # lettre comparée à la lettre acceptée
        lettre_acceptee = acc["fichiers"].get(1)
        lettre = next(p for p in self.dossier(d["id"])["documents"] if p["code"] == "demande_signee")
        if lettre["statut"] in ("a_generer", "erreur"):  # pièces exigées non reçues : lancée comme par une personne
            self.http.post(f"{self.api}/dossiers/{d['id']}/documents/{lettre['id']}/generer", timeout=120,
                           json={"acteur": ACTEUR}).raise_for_status()
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


def choisir(acceptes: list[dict], nombre: int, decalage: int) -> list[dict]:
    """`nombre` dossiers pris à tour de rôle selon le numéro du build : tous les
    dossiers sont rejoués en quelques nuits sans dépasser la durée d'un build."""
    if nombre <= 0 or nombre >= len(acceptes):
        return acceptes
    debut = ((max(decalage, 1) - 1) * nombre) % len(acceptes)
    return [acceptes[(debut + i) % len(acceptes)] for i in range(nombre)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--cle", default="")
    parser.add_argument("--acceptes", type=Path, default=RACINE / "data" / "dossiers_valides")
    parser.add_argument("--memoire", type=Path, default=RACINE / "output" / "memoire")
    parser.add_argument("--rapport", type=Path, default=RACINE / "rapports-ci")
    parser.add_argument("--delai", type=int, default=3600)
    parser.add_argument("--delai-lecture", type=int, default=1800,
                        help="temps maximal de lecture d'un dossier (s) ; au-delà, rejeu avec les pièces déjà lues")
    parser.add_argument("--nombre", type=int, default=0,
                        help="dossiers rejoués par build (0 = tous) : environ 25 min par dossier avec Mistral")
    parser.add_argument("--decalage", type=int, default=0,
                        help="numéro du build : les dossiers sont pris à tour de rôle d'un build à l'autre")
    args = parser.parse_args()
    import memoire as mem

    rejeu = Rejeu(args.api, args.cle, args.delai, args.delai_lecture)

    def trop_long(signum, frame):
        raise TimeoutError("durée maximale du dossier dépassée")

    signal.signal(signal.SIGALRM, trop_long)
    acceptes = dossiers_acceptes(args.acceptes) if args.acceptes.is_dir() else []
    if not acceptes:
        print(f"Aucun dossier accepté dans {args.acceptes} : rien à rejouer.")
        # signalé dans le rapport : une étape qui n'a rien rejoué n'est pas une réussite
        rejeu.noter("aucun dossier", "dossiers acceptés", ignore="aucun dossier accepté dans /opt/conformite/data/"
                    "dossiers_valides (les déposer avec l'outil 3, la classe dans le nom du dossier)")
        rejeu.rapport(args.rapport)
        return 0
    acceptes = choisir(acceptes, args.nombre, args.decalage)
    print(f"Rejeu de {len(acceptes)} dossier(s) accepté(s), sans mémoire : "
          + ", ".join(f"{a['pays']}/{a['dossier']}" for a in acceptes))
    for acc in acceptes:
        # mémoire apprise avant ou après l'ajout de la classe au nom du dossier
        fichiers = [args.memoire / mem.fichier_memoire(acc["pays"], nom).name for nom in (acc["produit"], acc["dossier"])]
        fichier = next((f for f in fichiers if f.exists()), None)
        appris = json.loads(fichier.read_text(encoding="utf-8")) if fichier else None
        # garde-fou absolu : quel que soit l'appel bloqué, le dossier est abandonné après sa durée
        # maximale (lecture + lettre + marge) et l'endroit du blocage est écrit dans le rapport
        signal.alarm(args.delai_lecture + args.delai + 600)
        try:
            rejeu.rejouer(acc, appris)
        except Exception as e:  # un dossier en échec n'arrête pas les autres
            ou = traceback.extract_tb(e.__traceback__)[-1]
            rejeu.noter(f"{acc['pays']}/{acc['dossier']}", "rejeu complet",
                        f"{type(e).__name__}: {e} (à {Path(ou.filename).name}:{ou.lineno}, {ou.name})")
        finally:
            signal.alarm(0)
        rejeu.rapport(args.rapport)  # rapport mis à jour après chaque dossier : rien n'est perdu si le build est coupé
    rejeu.rapport(args.rapport)
    return 1 if any(c[2] for c in rejeu.cas) else 0


if __name__ == "__main__":
    sys.exit(main())
