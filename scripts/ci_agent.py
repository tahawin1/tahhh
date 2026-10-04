"""
Agent de bout en bout, sur la vraie pile (API + Qdrant + Ollama/Mistral) et
des documents SPÉCIMEN fictifs : chaque étape du cahier des charges est
exécutée comme par un utilisateur, puis vérifiée.

  1. Règles      : création du dossier (Chine, classe III) -> pièces décidées par le code
  2. Classement  : dépôt groupé -> chaque fichier rangé dans la bonne pièce
  3. Lecture     : Mistral lit ISO et NMPA ; valeurs attendues, citations vérifiées
  4. Checklist   : contrôles de l'entreprise (expiration, classe, papiers à réclamer, relance)
  5. Formulaires : fiche signalétique et annexe II remplies par le code
  6. Rédaction   : lettre de Mistral (RAG : modèle accepté + textes) sans préambule ni invention
  7. Dépôt       : ZIP numéroté marqué BROUILLON ; rien validé, rien envoyé ; bilan (cas 2 : pièces à réclamer,
                  nos papiers préparés quand même)
  8. Base       : nouveau dossier du même fabricant -> l'agent fournit le catalogue ; certificats réclamés

    python scripts/ci_agent.py --api http://127.0.0.1:8100 --cle CLE --rapport rapports-ci
"""
from __future__ import annotations

import argparse
import datetime
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import requests

RACINE = Path(__file__).resolve().parent.parent
FIXTURES = RACINE / "tests" / "fixtures"
ACTEUR = "Jenkins (essai automatique)"
PRODUIT = "Prothèse totale de hanche SPECIMEN"
FOURNISSEUR = "Hangzhou Specimen Orthopaedics Co., Ltd."


def catalogue_specimen() -> bytes:
    """Catalogue fictif du fabricant spécimen (généré, aucune donnée réelle)."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    for i, ligne in enumerate(["SPECIMEN - DOCUMENT FICTIF POUR TESTS", "Hangzhou Specimen Orthopaedics Co., Ltd.",
                               "Product catalogue 2026 - brand SPECIMEN-ORTHO",
                               "Total hip prosthesis SPECIMEN    REF HSO-THP-01",
                               "Femoral stem SPECIMEN            REF HSO-FS-02"]):
        page.insert_text((50, 60 + 20 * i), ligne, fontsize=11)
    return doc.tobytes()


class Essai:
    def __init__(self, api: str, cle: str, delai: int):
        self.api, self.delai = api.rstrip("/"), delai
        self.http = requests.Session()
        self.http.trust_env = False  # API locale
        self.http.headers["X-API-Key"] = cle
        self.cas: list[tuple[str, str, float, str | None]] = []
        self.journal: dict = {}

    # ------------------------------------------------------------- outils
    def get(self, chemin, **kw):
        r = self.http.get(self.api + chemin, timeout=120, **kw)
        r.raise_for_status()
        return r

    def post(self, chemin, **kw):
        r = self.http.post(self.api + chemin, timeout=300, **kw)
        r.raise_for_status()
        return r.json()

    def verifier(self, etape: str, nom: str, condition: bool, detail: str = "", debut: float | None = None):
        duree = time.monotonic() - debut if debut else 0.0
        self.cas.append((etape, nom, duree, None if condition else (detail or "condition non remplie")))
        print(f"  {'✓' if condition else '✗'} [{etape}] {nom}" + ("" if condition else f" — {detail}"))
        return condition

    def attendre(self, dossier_id: int, condition, quoi: str) -> dict:
        fin = time.monotonic() + self.delai
        while True:
            d = self.get(f"/dossiers/{dossier_id}").json()
            if condition(d):
                return d
            if time.monotonic() > fin:
                raise TimeoutError(f"{quoi} : toujours en cours après {self.delai} s")
            time.sleep(10)

    @staticmethod
    def piece(dossier: dict, code: str) -> dict:
        return next(p for p in dossier["documents"] if p["code"] == code)

    @staticmethod
    def champ(piece: dict, nom: str) -> dict:
        return next((c for c in (piece.get("extraction") or {}).get("champs", []) if c["nom"] == nom), {})

    # ------------------------------------------------------------- étapes
    def regles(self) -> dict:
        debut = time.monotonic()
        d = self.post("/dossiers", json={"pays_origine": "chine", "produit": PRODUIT, "classe": "III",
                                         "fournisseur": FOURNISSEUR, "cree_par": ACTEUR})
        codes = {p["code"] for p in d["documents"]}
        attendues = {"demande_signee", "fiche_signaletique", "piece_specifique_chine", "iso_13485",
                     "certificat_enregistrement_annexe2", "evaluation_clinique"}
        self.verifier("1 règles", f"dossier n°{d['id']} : {len(codes)} pièces décidées par le moteur de règles",
                      attendues <= codes, f"pièces attendues manquantes : {sorted(attendues - codes)}", debut)
        p4 = self.piece(d, "piece_specifique_chine")
        self.verifier("1 règles", "pièce 4 chinoise : traduction signalée et fondement cité",
                      p4["traduction_requise"] and bool(p4["source"]), str(p4))
        return d

    def classement_et_lecture(self, d: dict) -> dict:
        debut = time.monotonic()
        fichiers = [("fichiers", ("5-ISO 13485 certificate.pdf", (FIXTURES / "specimen_iso13485_scanne.pdf").read_bytes(),
                                  "application/pdf")),
                    ("fichiers", ("4-NMPA registration certificate.pdf",
                                  (FIXTURES / "specimen_nmpa_traduction.pdf").read_bytes(), "application/pdf")),
                    ("fichiers", ("14-Catalogue.pdf", catalogue_specimen(), "application/pdf"))]
        r = self.post(f"/dossiers/{d['id']}/documents-recus", files=fichiers, data={"acteur": ACTEUR})
        ranges = {a["fichier"]: a["piece"] for a in r["affectations"]}
        self.verifier("2 classement", "ISO rangé en pièce 5, NMPA en pièce 4, catalogue en pièce 14",
                      ranges.get("5-ISO 13485 certificate.pdf") == 5 and ranges.get("4-NMPA registration certificate.pdf") == 4
                      and ranges.get("14-Catalogue.pdf") == 14,
                      str(r["affectations"]), debut)
        debut = time.monotonic()
        d = self.attendre(d["id"], lambda x: all(self.piece(x, c)["extraction_statut"] in ("terminee", "erreur")
                                                  for c in ("iso_13485", "piece_specifique_chine", "catalogue")),
                          "lecture par Mistral")
        iso, nmpa = self.piece(d, "iso_13485"), self.piece(d, "piece_specifique_chine")
        self.verifier("3 lecture", "les deux documents lus (dont un scan, par OCR)",
                      iso["extraction_statut"] == nmpa["extraction_statut"] == "terminee",
                      f"ISO : {iso['extraction_erreur']} ; NMPA : {nmpa['extraction_erreur']}", debut)
        attendus = [(iso, "numero", "SCB-MD-2024-0457"), (iso, "date_expiration", "2027-03-11"),
                    (iso, "titulaire", "Hangzhou Specimen"), (nmpa, "numero", "20213130457"),
                    (nmpa, "date_expiration", "2026-06-14"), (nmpa, "classe_indiquee", "III")]
        for piece, nom, attendu in attendus:
            c = self.champ(piece, nom)
            lu = c.get("valeur_normalisee") if "date" in nom else c.get("valeur")
            juste = bool(lu) and attendu.lower() in str(lu).lower()
            faux_accepte = bool(lu) and not juste and c.get("verification") == "verifie"
            self.verifier("3 lecture", f"{piece['code']}.{nom} = {attendu}", juste and not faux_accepte,
                          f"lu « {lu} » ({c.get('verification')})" + (" — VALEUR FAUSSE ACCEPTÉE" if faux_accepte else ""))
        return d

    def checklist(self, d: dict):
        debut = time.monotonic()
        c = self.get(f"/dossiers/{d['id']}/controles").json()
        self.journal["controles_resume"] = c["resume"]
        elements = [e for doc in c["documents"] for e in doc["elements"]]
        expire = [e for e in elements if e["statut"] == "ko" and "2026" in (e.get("detail") or "")]
        self.verifier("4 checklist", f"{len(c['documents'])} documents de la checklist appliqués ({sum(c['resume'].values())} points)",
                      len(c["documents"]) >= 5, json.dumps(c["resume"]), debut)
        self.verifier("4 checklist", "certificat NMPA expiré (14/06/2026) détecté par le code", bool(expire),
                      "aucun point « ko » portant sur la date d'expiration")
        self.verifier("4 checklist", "papiers à réclamer et projet de relance (jamais envoyé)",
                      bool(c["a_reclamer"]) and "AMMPS" in (c.get("relance") or "") and PRODUIT in c["relance"],
                      f"{len(c['a_reclamer'])} à réclamer")
        self.verifier("4 checklist", "points humains (signatures, cachets) laissés à une personne",
                      c["resume"].get("humain_a_faire", 0) > 0, json.dumps(c["resume"]))

    def formulaires(self, d: dict):
        debut = time.monotonic()
        donnees = self.get(f"/dossiers/{d['id']}/donnees-dispositif").json()
        champs = {c["id"]: c for s in donnees["sections"] for c in s["champs"]}
        fab = champs["fabricant_nom"]
        self.verifier("5 formulaires", "fabricant repris du document lu (provenance tracée)",
                      "Hangzhou Specimen" in (fab["valeur"] or "") and fab["provenance"] == "piece", str(fab), debut)
        self.verifier("5 formulaires", "classe écrite comme sur le formulaire officiel", champs["classe"]["valeur"] == "III",
                      str(champs["classe"]))
        inventes = [c["id"] for c in champs.values() if c["valeur"] and c["provenance"] == "manquant"]
        self.verifier("5 formulaires", f"rien d'inventé ({donnees['a_completer']} case(s) laissée(s) [À COMPLÉTER])",
                      not inventes, str(inventes))
        fiche = self.piece(self.get(f"/dossiers/{d['id']}").json(), "fiche_signaletique")
        self.verifier("5 formulaires", "fiche signalétique produite, à valider", fiche["statut"] == "a_valider", fiche["statut"])

    def redaction(self, d: dict) -> dict:
        debut = time.monotonic()
        lettre = self.piece(self.get(f"/dossiers/{d['id']}").json(), "demande_signee")
        if lettre["statut"] in ("a_generer", "erreur"):
            self.post(f"/dossiers/{d['id']}/documents/{lettre['id']}/generer", json={"acteur": ACTEUR})
        d = self.attendre(d["id"], lambda x: self.piece(x, "demande_signee")["statut"] in ("a_valider", "erreur"),
                          "rédaction de la lettre par Mistral")
        lettre = self.piece(d, "demande_signee")
        if not self.verifier("6 rédaction", "lettre rédigée par Mistral", lettre["statut"] == "a_valider",
                             lettre.get("erreur") or lettre["statut"], debut):
            return d
        texte = "\n".join(p["texte"] for p in self.get(f"/dossiers/{d['id']}/documents/{lettre['id']}/apercu").json()["paragraphes"])
        self.journal["lettre"] = texte
        corps = texte.split("Sources réglementaires")[0]
        self.verifier("6 rédaction", "adressée au Directeur général de l'AMMPS",
                      "AMMPS" in corps or "Agence Marocaine" in corps, corps[:300])
        self.verifier("6 rédaction", "désignation du dispositif reprise", "hanche" in corps.lower(), corps[:300])
        self.verifier("6 rédaction", "pas de préambule ni de consigne recopiée",
                      not re.search(r"(?im)^\s*(voici|ici, il est important|note\s*:|consignes|r[eè]gles strictes)", corps), corps[:300])
        self.verifier("6 rédaction", "datée du jour", datetime.date.today().strftime("%d/%m/%Y") in corps
                      or "[À COMPLÉTER" in corps, re.findall(r"le \S+", corps)[:2])
        sources = lettre.get("sources") or []
        self.verifier("6 rédaction", "sources affichées (modèle accepté ou textes du RAG)", bool(sources), str(sources)[:200])
        return d

    def depot(self, d: dict):
        debut = time.monotonic()
        r = self.get(f"/dossiers/{d['id']}/export")
        noms = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        self.verifier("7 dépôt", "ZIP : bordereau + pièces numérotées (04, 05)",
                      noms[0] == "00-Bordereau.docx" and any(n.startswith("04-") for n in noms)
                      and any(n.startswith("05-") for n in noms), str(noms), debut)
        self.verifier("7 dépôt", "marqué BROUILLON (rien validé)", "BROUILLON" in r.headers.get("content-disposition", ""),
                      r.headers.get("content-disposition", ""))
        d = self.get(f"/dossiers/{d['id']}").json()
        self.verifier("7 dépôt", "aucune pièce validée par l'agent", all(p["statut"] != "valide" for p in d["documents"]))
        b = self.get(f"/dossiers/{d['id']}/bilan").json()
        notre = {l["code"]: l for l in b["notre_part"]}
        self.journal["bilan"] = {"cas": b["cas"], "titre": b["titre"], "compteurs": b["compteurs"]}
        self.verifier("7 dépôt", f"bilan de l'agent : {b['titre']}",
                      b["cas"] == "incomplet" and bool(b["relance"]) and notre["demande_signee"]["etat"] == "redige"
                      and notre["fiche_signaletique"]["etat"] == "redige",
                      json.dumps({"cas": b["cas"], "lettre": notre.get("demande_signee", {}).get("etat")}))

    def memoire(self):
        """Politique de la direction : le fournisseur n'envoie que ses certificats ; l'agent
        fournit le reste depuis la base (ici : le catalogue du dossier précédent du même fabricant)."""
        debut = time.monotonic()
        d = self.post("/dossiers", json={"pays_origine": "chine", "produit": "Tige fémorale SPECIMEN", "classe": "IIB",
                                         "fournisseur": FOURNISSEUR, "cree_par": ACTEUR})
        catalogue = self.piece(d, "catalogue")
        self.verifier("8 base", "nouveau dossier du même fabricant : catalogue fourni par l'agent depuis la base",
                      catalogue["extraction_statut"] == "terminee" and "base" in (catalogue.get("origine_recu") or "")
                      and catalogue["statut"] != "valide", f"catalogue : {catalogue['extraction_statut']} "
                      f"{catalogue.get('origine_recu')}", debut)
        certificats = [self.piece(d, c)["extraction_statut"] for c in ("iso_13485", "piece_specifique_chine")]
        self.verifier("8 base", "certificats (ISO, NMPA) jamais repris : toujours envoyés par le fournisseur",
                      certificats == [None, None], str(certificats))
        c = self.get(f"/dossiers/{d['id']}/controles").json()
        non_recus = " ".join(x["nom"] for x in c["a_reclamer"] if "document non reçu" in x["raisons"])
        self.verifier("8 base", "relance au fournisseur : ISO 13485 réclamé, catalogue non (fourni par l'agent)",
                      "13485" in non_recus and "Catalogue" not in non_recus, non_recus[:300])

    # ------------------------------------------------------------- rapport
    def rapport(self, dossier: Path):
        dossier.mkdir(parents=True, exist_ok=True)
        a = {'"': "&quot;"}
        cas = [f'<testcase classname="agent.{escape(e, a)}" name="{escape(n, a)}" time="{t:.1f}">'
               + (f'<failure message="{escape(m, a)}"/>' if m else "") + "</testcase>" for e, n, t, m in self.cas]
        echecs = sum(1 for c in self.cas if c[3])
        (dossier / "agent.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="Agent de bout en bout" '
                                           f'tests="{len(cas)}" failures="{echecs}">\n' + "\n".join(cas) + "\n</testsuite>\n",
                                           encoding="utf-8")
        (dossier / "agent.json").write_text(json.dumps({"etapes": [{"etape": e, "controle": n, "duree_s": round(t, 1),
                                                                    "echec": m} for e, n, t, m in self.cas],
                                                        **self.journal}, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--cle", default="")
    parser.add_argument("--rapport", type=Path, default=RACINE / "rapports-ci")
    parser.add_argument("--delai", type=int, default=2400, help="attente maximale par étape longue (s)")
    args = parser.parse_args()
    essai = Essai(args.api, args.cle, args.delai)
    print(f"Agent de bout en bout sur {args.api}")
    try:
        d = essai.regles()
        d = essai.classement_et_lecture(d)
        essai.checklist(d)
        essai.formulaires(d)
        d = essai.redaction(d)
        essai.depot(d)
        essai.memoire()
    except Exception as e:  # une étape impossible est un échec visible, jamais un arrêt muet
        essai.verifier("arrêt", "le scénario a pu aller jusqu'au bout", False, f"{type(e).__name__}: {e}")
    essai.rapport(args.rapport)
    echecs = [c for c in essai.cas if c[3]]
    print(f"Agent : {len(essai.cas) - len(echecs)}/{len(essai.cas)} contrôles réussis")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
