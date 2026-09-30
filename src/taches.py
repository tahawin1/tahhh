"""
Génération des documents en tâche de fond.

Rédiger une pièce prend plusieurs minutes (Mistral sur CPU) : l'API ne peut
pas attendre la fin dans la requête HTTP (un tunnel ou un proxy coupe la
connexion bien avant). L'API met donc les pièces en file ; un worker unique
les rédige une par une et met à jour leur statut en base, que le frontend
consulte.

Un seul worker : sur un serveur sans GPU, lancer plusieurs générations en
parallèle ne va pas plus vite, chacune ralentit les autres.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import db
from db import Document, journaliser, maintenant
from rule_engine import DocumentRequis

_executeur = ThreadPoolExecutor(max_workers=1, thread_name_prefix="generation")
_generateur = None


def _obtenir_generateur():
    """Instancié à la première génération seulement (connexion Qdrant + Ollama)."""
    global _generateur
    if _generateur is None:
        from generate import GenerateurDocuments

        _generateur = GenerateurDocuments()
    return _generateur


def soumettre(document_id: int) -> None:
    """Ajoute une pièce à la file de génération (remplacé dans les tests)."""
    _executeur.submit(executer_generation, document_id)


def executer_generation(document_id: int) -> None:
    from generate import GenerationImpossible, generer_document

    with db.SessionLocal() as session:
        doc = session.get(Document, document_id)
        if doc is None or doc.statut != "en_file":
            return  # annulée ou déjà traitée entre-temps
        doc.statut = "en_generation"
        doc.erreur = None
        session.commit()

        dossier = doc.dossier
        requis = DocumentRequis(
            id=doc.code,
            nom=doc.nom,
            traduction_requise=doc.traduction_requise,
            legalisation_requise=doc.legalisation_requise,
            origine_regle=doc.origine_regle,
            nature=doc.nature,
            fourni_par=doc.fourni_par,
            consigne_redaction=doc.consigne_redaction,
        )
        try:
            resultat = generer_document(
                _obtenir_generateur(), requis, dossier.produit, dossier.pays_origine, Path(dossier.dossier_sortie),
                classe=dossier.classe,
                fournisseur=dossier.fournisseur,
                pieces_du_dossier=[d.nom for d in dossier.documents],  # figées à la création du dossier
            )
        except GenerationImpossible as e:
            doc.statut = "erreur"
            doc.erreur = str(e)
            journaliser(session, dossier.id, "système", "generation_echec", str(e), document_id=doc.id)
        except Exception as e:  # erreur inattendue (Qdrant indisponible…) : visible, jamais silencieuse
            doc.statut = "erreur"
            doc.erreur = f"Erreur inattendue : {type(e).__name__}: {e}"
            journaliser(session, dossier.id, "système", "generation_echec", doc.erreur, document_id=doc.id)
        else:
            doc.statut = "a_valider"
            doc.fichier = resultat["fichier"]
            doc.sources = resultat["sources"]
            doc.genere_le = maintenant()
            # Une nouvelle version efface la validation précédente
            doc.valide_par = None
            doc.valide_le = None
            journaliser(session, dossier.id, "système", "generation_terminee", doc.nom, document_id=doc.id)
        session.commit()


def reprendre_apres_redemarrage() -> int:
    """Au démarrage de l'API, les générations interrompues (arrêt du serveur)
    sont marquées en erreur plutôt que laissées « en cours » indéfiniment."""
    with db.SessionLocal() as session:
        interrompus = session.query(Document).filter(Document.statut.in_(db.STATUTS_EN_COURS)).all()
        for doc in interrompus:
            doc.statut = "erreur"
            doc.erreur = "Génération interrompue par un redémarrage du serveur — relancer."
            journaliser(session, doc.dossier_id, "système", "generation_echec", doc.erreur, document_id=doc.id)
        session.commit()
        return len(interrompus)
