"""
Exporte les décisions du moteur de règles (et les extraits réglementaires
du RAG) pour l'édition claude.ai du tableau de bord.

    .venv/bin/python claude_ai/exporter_regles.py      # écrit claude_ai/regles.json

La page claude.ai ne contient AUCUNE règle écrite à la main : elle lit ce
fichier, produit par rule_engine.py à partir des YAML. Après toute
modification de rules/*.yaml, relancer ce script puis reconstruire la page
(claude_ai/construire.py). Les extraits RAG demandent Qdrant et Ollama
démarrés (même index que la version serveur).
"""
import datetime
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from generate import GenerateurDocuments  # noqa: E402
from rule_engine import charger_regles, documents_requis_maroc, empreinte_regles, prochain_creneau_depot  # noqa: E402

PAYS = ["chine", "inde", "union_europeenne", "autre"]
CLASSES = ["I", "IIA", "IIB", "III"]

export = {
    "genere_le": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "regles_version": empreinte_regles("maroc"),
    "jours_depot": charger_regles("maroc")["contraintes_operationnelles"]["jours_depot_physique"],
    "pays": {p: {"autorite": charger_regles(p)["autorite"], "classification": charger_regles(p)["classification"]}
             for p in ["maroc", "chine", "inde", "union_europeenne"]},
    "requis": {},
    "extraits": {},
}

generateur = GenerateurDocuments()
for pays in PAYS:
    for classe in CLASSES:
        docs = documents_requis_maroc(pays, classe=classe)
        export["requis"][f"{pays}|{classe}"] = [
            {
                "id": d.id, "nom": d.nom, "nature": d.nature, "fourni_par": d.fourni_par,
                "traduction_requise": d.traduction_requise, "legalisation_requise": d.legalisation_requise,
                "origine_regle": d.origine_regle, "consigne_redaction": d.consigne_redaction,
                "champs_a_extraire": d.champs_a_extraire,
            }
            for d in docs
        ]
        for d in docs:
            if d.a_rediger and d.id not in export["extraits"]:
                refs = generateur.references_pour_document(d, "maroc", pays)
                export["extraits"][d.id] = [
                    {"texte_source": r["texte_source"], "pays": r["pays"], "date_version": r["date_version"],
                     "fichier": r["fichier"], "chunk_index": r["chunk_index"], "score": round(r["score"], 4),
                     "texte": r["texte"][:800]}
                    for r in refs
                ]

sortie = RACINE / "claude_ai" / "regles.json"
sortie.write_text(json.dumps(export, ensure_ascii=False, indent=1))
print(f"{sortie} : {len(export['requis'])} combinaisons, extraits pour {sorted(export['extraits'])}, "
      f"règles {export['regles_version']}, prochain créneau {prochain_creneau_depot()}")
