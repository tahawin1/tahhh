"""
Modèles de rédaction tirés des dossiers réellement acceptés par l'administration.

Chaque pièce « à rédiger » d'un dossier accepté (lettre de demande, fiche
signalétique, certificat de l'annexe II…) devient le modèle de la même pièce
pour les dossiers suivants : Mistral reprend sa structure, son destinataire,
ses formules et l'en-tête de l'entreprise, et n'y remplace que les données du
nouveau dispositif.

Les dossiers acceptés restent sur le serveur, jamais sur GitHub :

    data/dossiers_valides/<pays_origine>/<produit>/**/<numéro>-<nom>.pdf
    ex. data/dossiers_valides/union_europeenne/Ciment osseux/MODULES/1/1-1-Lettre de Demande.pdf

Le numéro en tête du nom de fichier est celui de la pièce dans le dossier
déposé ; il est rapproché de la pièce par le champ `numero` des règles
(rules/maroc.yaml) — c'est le code, pas l'IA, qui décide quel fichier est
le modèle de quelle pièce.

    python src/modeles.py                      # indexe data/dossiers_valides
    python src/modeles.py --racine AUTRE/DOSSIER
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import re
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from embeddings import Embedder
from memoire import produit_et_classe
from rule_engine import charger_regles

COLLECTION_MODELES = "modeles_dossiers"
RACINE_DEFAUT = Path(__file__).resolve().parent.parent / "data" / "dossiers_valides"
TEXTE_MAX = 7000  # caractères gardés par modèle (contexte de Mistral limité)
NUMERO_FICHIER = re.compile(r"^\s*(\d{1,2})\s*[-_. ]")


def pieces_a_rediger_par_numero() -> dict[int, str]:
    """{numéro dans le dossier : id de la pièce}, pour les pièces à rédiger,
    d'après les règles (jamais d'après le contenu du fichier)."""
    regles = charger_regles("maroc")
    return {d["numero"]: d["id"] for d in regles["socle_commun"]
             if d.get("nature") == "a_rediger" and d.get("numero") is not None}


def _client(host: str | None = None, port: int | None = None) -> QdrantClient:
    return QdrantClient(host=host or os.environ.get("QDRANT_HOST", "localhost"),
                        port=port or int(os.environ.get("QDRANT_PORT", "6333")))


def fichiers_modeles(racine: Path) -> list[dict]:
    """Repère, sans rien lire, les fichiers qui serviront de modèles."""
    import preuve as preuve_mod

    trouves = []
    for pays_dir in sorted(p for p in racine.iterdir() if p.is_dir()):
        table = pieces_a_rediger_par_numero()
        for produit_dir in sorted(p for p in pays_dir.iterdir() if p.is_dir()):
            pieces_4 = [f for f in produit_dir.rglob("*") if f.is_file() and (m := NUMERO_FICHIER.match(f.name))
                        and int(m.group(1)) == 4]
            preuve = preuve_mod.preuve_de_fichiers(sorted(pieces_4))
            for fichier in sorted(produit_dir.rglob("*.pdf")):
                m = NUMERO_FICHIER.match(fichier.name)
                if not m or int(m.group(1)) not in table:
                    continue
                produit, classe = produit_et_classe(produit_dir.name)
                trouves.append({
                    "fichier": fichier,
                    "pays_origine": pays_dir.name,
                    "produit": produit,
                    "classe": classe,
                    "preuve": preuve,
                    "numero": int(m.group(1)),
                    "piece_id": table[int(m.group(1))],
                })
    return trouves


def _deja_indexes(client: QdrantClient, ids: list[str]) -> dict[str, dict]:
    """{id: payload} des modèles déjà dans Qdrant (vide si la collection n'existe pas)."""
    try:
        if not client.collection_exists(COLLECTION_MODELES):
            return {}
        points = client.retrieve(COLLECTION_MODELES, ids=ids, with_payload=True, with_vectors=False)
    except Exception:
        return {}
    return {str(p.id): p.payload or {} for p in points}


def _retirer_absents(client: QdrantClient, gardes: set[str]) -> int:
    """Retire les modèles dont le fichier n'est plus dans les dossiers acceptés
    (dossier déplacé dans un autre pays, renommé ou supprimé)."""
    from qdrant_client.models import PointIdsList

    try:
        if not client.collection_exists(COLLECTION_MODELES):
            return 0
        absents, offset = [], None
        while True:
            points, offset = client.scroll(COLLECTION_MODELES, limit=256, offset=offset, with_payload=False,
                                           with_vectors=False)
            absents += [p.id for p in points if str(p.id) not in gardes]
            if offset is None:
                break
        if absents:
            client.delete(COLLECTION_MODELES, points_selector=PointIdsList(points=absents))
        return len(absents)
    except Exception as e:  # jamais bloquant
        print(f"  ! nettoyage des anciens modèles impossible : {e}")
        return 0


def indexer(racine: Path = RACINE_DEFAUT, client: QdrantClient | None = None, embedder: Embedder | None = None,
            forcer: bool = False) -> list[dict]:
    """Lit chaque modèle (texte ou OCR) et l'enregistre dans Qdrant. Incrémental :
    un fichier déjà indexé et inchangé (même empreinte, même pays, classe et
    preuve) n'est pas relu (`forcer` pour tout relire) ; les modèles des
    dossiers retirés ou déplacés sont effacés. Retourne les modèles (re)lus."""
    from extraction import lire_document

    client = client or _client()
    trouves = fichiers_modeles(racine)
    if not trouves:
        return []
    for m in trouves:
        m["relatif"] = str(m["fichier"].relative_to(racine))
        m["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"modele:{m['relatif']}"))
        m["empreinte"] = hashlib.sha256(m["fichier"].read_bytes()).hexdigest()[:12]
    retires = _retirer_absents(client, {m["id"] for m in trouves})
    if retires:
        print(f"  - {retires} ancien(s) modèle(s) retiré(s) (dossier déplacé ou supprimé)")
    deja = {} if forcer else _deja_indexes(client, [m["id"] for m in trouves])
    a_lire = []
    for m in trouves:
        p = deja.get(m["id"])
        if p and all(p.get(k) == m[k] for k in ("empreinte", "pays_origine", "produit", "classe", "preuve")):
            continue
        a_lire.append(m)
    if len(a_lire) < len(trouves):
        print(f"  = {len(trouves) - len(a_lire)} modèle(s) inchangé(s), non relu(s)")
    if not a_lire:
        return []
    embedder = embedder or Embedder()
    points = []
    for m in a_lire:
        try:
            texte = lire_document(m["fichier"]).strip()
        except Exception as e:  # un fichier illisible ne bloque pas les autres
            print(f"  ✗ {m['fichier'].name} : lecture impossible ({type(e).__name__}: {e}), ignoré")
            continue
        if not texte:
            print(f"  ! {m['fichier'].name} : aucun texte lisible, ignoré")
            continue
        relatif = m["relatif"]
        points.append(PointStruct(
            id=m["id"],
            vector=embedder.encoder_un(f"{m['produit']} — {texte[:1500]}"),
            payload={
                "piece_id": m["piece_id"],
                "numero": m["numero"],
                "pays_origine": m["pays_origine"],
                "produit": m["produit"],
                "classe": m["classe"],
                "preuve": m["preuve"],
                "fichier": relatif,
                "empreinte": m["empreinte"],
                "texte": texte[:TEXTE_MAX],
                "indexe_le": datetime.date.today().isoformat(),
            },
        ))
        print(f"  ✓ pièce {m['numero']} ({m['piece_id']}) — {m['produit']} — {len(texte)} caractères")
    if not points:
        return []
    if not client.collection_exists(COLLECTION_MODELES):
        client.create_collection(COLLECTION_MODELES, vectors_config=VectorParams(size=len(points[0].vector), distance=Distance.COSINE))
    client.upsert(COLLECTION_MODELES, points=points)
    return [p.payload for p in points]


def modele_pour(piece_id: str, pays_origine: str, produit: str,
                client: QdrantClient, embedder: Embedder, classe: str | None = None,
                preuve: str | None = None) -> dict | None:
    """Le modèle accepté le plus proche pour cette pièce : même pièce
    obligatoirement ; de préférence même pays du fabricant, même preuve de mise
    sur le marché (CE ou autorité du pays) et même classe, puis de moins en
    moins de critères ; produit le plus ressemblant. None s'il n'y en a pas
    (la rédaction se fait alors sans modèle)."""
    try:
        if not client.collection_exists(COLLECTION_MODELES):
            return None
    except Exception:
        return None
    vecteur = embedder.encoder_un(produit)
    piece = FieldCondition(key="piece_id", match=MatchValue(value=piece_id))
    pays = FieldCondition(key="pays_origine", match=MatchValue(value=pays_origine))
    meme_classe = FieldCondition(key="classe", match=MatchValue(value=str(classe).upper())) if classe else None
    meme_preuve = FieldCondition(key="preuve", match=MatchValue(value=preuve)) if preuve in ("ce", "nationale") else None
    # du plus proche au plus large : même pays + même preuve + même classe, … , même pièce seulement
    combinaisons = [(pays, meme_preuve, meme_classe), (pays, meme_preuve), (meme_preuve, meme_classe), (meme_preuve,),
                    (pays, meme_classe), (pays,), (meme_classe,), ()]
    essais, vus = [], set()
    for c in combinaisons:
        if any(f is None for f in c):
            continue
        cle = tuple(id(f) for f in c)
        if cle not in vus:
            vus.add(cle)
            essais.append([piece, *c])
    for filtres in essais:
        points = client.query_points(COLLECTION_MODELES, query=vecteur, query_filter=Filter(must=filtres),
                                     limit=1, with_payload=True).points
        if points:
            return {**points[0].payload, "score": points[0].score}
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Indexe les dossiers acceptés comme modèles de rédaction.")
    parser.add_argument("--racine", type=Path, default=RACINE_DEFAUT)
    parser.add_argument("--forcer", action="store_true", help="relire tous les modèles, même inchangés")
    args = parser.parse_args()
    if not args.racine.is_dir():
        raise SystemExit(f"Dossier introuvable : {args.racine}")
    print(f"Modèles cherchés dans {args.racine}")
    resultat = indexer(args.racine, forcer=args.forcer)
    print(f"{len(resultat)} modèle(s) nouveau(x) ou modifié(s) indexé(s) dans la collection « {COLLECTION_MODELES} ».")
