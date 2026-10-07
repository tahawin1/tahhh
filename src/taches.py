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

import heapq
import itertools
import threading
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
            import formulaires

            if doc.code in formulaires.formulaires():
                # formulaire officiel : rempli case par case par le code, jamais par Mistral
                from generate import profil_entreprise

                resultat = formulaires.generer_formulaire(dossier, doc.code, doc.nom, Path(dossier.dossier_sortie),
                                                          profil_entreprise())
            else:
                resultat = generer_document(
                _obtenir_generateur(), requis, dossier.produit, dossier.pays_origine, Path(dossier.dossier_sortie),
                classe=dossier.classe,
                fournisseur=dossier.fournisseur,
                pieces_du_dossier=[d.nom for d in dossier.documents],  # figées à la création du dossier
                donnees=_donnees_connues(dossier),
                # modèle choisi parmi les dossiers acceptés de même preuve (CE ou autorité du pays)
                preuve="ce" if dossier.pays_origine == "union_europeenne" else (
                    dossier.preuve if dossier.preuve in ("ce", "nationale") else None),
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


def _donnees_connues(dossier) -> dict[str, str]:
    """Données du dispositif déjà établies (saisies ou lues), transmises à Mistral
    pour la lettre : il les reprend au lieu de les inventer."""
    import formulaires
    from generate import profil_entreprise

    utiles = ("designation", "nom_marque", "indications", "fabricant_nom", "fabricant_adresse", "presentation")
    donnees = formulaires.resoudre(dossier, profil_entreprise(), dossier.donnees_dispositif)
    return {donnees[i]["libelle"]: donnees[i]["valeur"] for i in utiles
            if donnees[i]["valeur"] and donnees[i]["provenance"] in ("saisie", "piece")}


# Ordre de lecture des documents reçus : d'abord la pièce 4 (elle fixe la preuve
# CE ou nationale, donc les pièces exigées), puis les pièces qui remplissent les
# formulaires (étiquettes, notice, catalogue, déclaration) ; les certificats
# ISO et autres ensuite. Sur un PC lent, les formulaires sont prêts plus tôt.
ORDRE_LECTURE = ("piece_specifique", "etiquetage", "notice", "catalogue", "declaration_conformite",
                 "attestation_fabricant")
_lectures_en_attente: list[tuple[int, int, int]] = []
_verrou_lectures = threading.Lock()
_numero_lecture = itertools.count()


def rang_lecture(code: str | None) -> int:
    code = code or ""
    return next((i for i, debut in enumerate(ORDRE_LECTURE) if code.startswith(debut)), len(ORDRE_LECTURE))


def soumettre_extraction(document_id: int) -> None:
    """Ajoute la lecture d'un document reçu à la file, par ordre d'utilité
    (ORDRE_LECTURE) puis d'arrivée (remplacé dans les tests)."""
    try:
        with db.SessionLocal() as session:
            doc = session.get(Document, document_id)
            rang = rang_lecture(doc.code if doc else None)
    except Exception:
        rang = len(ORDRE_LECTURE)
    with _verrou_lectures:
        heapq.heappush(_lectures_en_attente, (rang, next(_numero_lecture), document_id))
    _executeur.submit(_lecture_suivante)


def _lecture_suivante() -> None:
    """Une soumission = une lecture : la plus utile en attente à ce moment."""
    with _verrou_lectures:
        if not _lectures_en_attente:
            return
        _, _, document_id = heapq.heappop(_lectures_en_attente)
    executer_extraction(document_id)


def executer_extraction(document_id: int) -> None:
    """Lit le document reçu d'une pièce à fournir et en extrait les champs
    déclarés dans les règles, chaque valeur étant confrontée au texte réel."""
    import extraction

    with db.SessionLocal() as session:
        doc = session.get(Document, document_id)
        if doc is None or doc.extraction_statut != "en_file" or not doc.fichier_recu:
            return
        doc.extraction_statut = "en_cours"
        doc.extraction_erreur = None
        session.commit()
        try:
            resultat = extraction.extraire(Path(doc.fichier_recu), doc.champs_a_extraire or [], doc.nom)
        except extraction.ExtractionImpossible as e:
            doc.extraction_statut = "erreur"
            doc.extraction_erreur = str(e)
            journaliser(session, doc.dossier_id, "système", "lecture_echec", f"{doc.nom} — {e}", document_id=doc.id)
        except Exception as e:  # jamais silencieux
            doc.extraction_statut = "erreur"
            doc.extraction_erreur = f"Erreur inattendue : {type(e).__name__}: {e}"
            journaliser(session, doc.dossier_id, "système", "lecture_echec", doc.extraction_erreur, document_id=doc.id)
        else:
            try:  # textes repris dans les formulaires : traduits en français s'il le faut (jamais bloquant)
                extraction.traduire_champs(resultat["champs"])
            except Exception:
                pass
            doc.texte_recu = resultat.pop("texte")
            doc.extraction = resultat
            doc.extraction_statut = "terminee"
            r = resultat["resume"]
            journaliser(
                session, doc.dossier_id, "système", "lecture_terminee",
                f"{doc.nom} — {r['verifie']} champ(s) vérifié(s), "
                f"{r['citation_introuvable'] + r['valeur_hors_citation']} non vérifié(s), {r['absent']} absent(s)"
                + (f" — {resultat['incomplet']} : relancer la lecture" if resultat.get("incomplet") else ""),
                document_id=doc.id,
            )
        session.commit()
        if doc.extraction_statut == "terminee":
            detecter_preuve(session, doc)
            enchainer(session, doc.dossier)


def detecter_preuve(session, doc) -> None:
    """Pièce 4 lue, preuve encore « à détecter » : le code (pas Mistral) regarde
    si c'est un certificat CE d'organisme notifié ou un certificat de l'autorité
    du pays, et adapte les pièces exigées. Journalisé, jamais bloquant."""
    import preuve

    dossier = doc.dossier
    if not doc.code.startswith("piece_specifique_") or dossier.preuve != "auto":
        return
    try:
        trouvee = preuve.detecter(doc.texte_recu or "", [doc.nom_fichier_recu or ""])
        if trouvee == "ce" and dossier.pays_origine != preuve.PAYS_CE:
            a_relire = preuve.changer(session, dossier, "ce", "système",
                                      f"certificat CE détecté dans « {doc.nom_fichier_recu} »")
            session.commit()
            for document_id in a_relire:
                soumettre_extraction(document_id)
        elif trouvee is not None:
            dossier.preuve = trouvee
            journaliser(session, dossier.id, "système", "preuve_detectee",
                        f"Preuve de mise sur le marché : {trouvee} (détectée dans « {doc.nom_fichier_recu} »)")
            session.commit()
    except Exception as e:  # jamais silencieux
        journaliser(session, dossier.id, "système", "preuve_echec", f"Détection de la preuve : {e}")
        session.commit()


def reprendre_documents(session, dossier, acteur: str = "système") -> int:
    """L'agent fournit depuis la base les pièces que la politique lui confie
    (rules/bibliotheque.yaml : tout sauf les certificats) : dossiers déjà
    traités et dossiers acceptés du même fabricant (et du même produit pour
    les pièces propres au produit). Journalisé ; rien n'est validé. Retourne
    le nombre de pièces fournies."""
    import bibliotheque

    precedents = (session.query(db.Dossier).filter(db.Dossier.id != dossier.id)
                  .order_by(db.Dossier.id.desc()).limit(100).all())
    faits = bibliotheque.reprendre(dossier, precedents)
    for piece, trouve, a_relire in faits:
        journaliser(session, dossier.id, acteur, "document_repris",
                    f"{piece.nom} — fourni par l'agent depuis la {trouve['origine']} ({trouve['nom']})"
                    + (" ; lecture par l'agent en cours" if a_relire else " ; lecture reprise"),
                    document_id=piece.id)
    session.commit()
    for piece, _, a_relire in faits:
        if a_relire:
            soumettre_extraction(piece.id)
    return len(faits)


def enchainer(session, dossier, acteur: str = "système") -> list[str]:
    """Agent, étape 4 — enchaînement automatique, sans rien valider ni envoyer :
    1. les formulaires remplis par le code (fiche signalétique, annexe II) sont
       remis à jour avec les nouvelles données, sauf s'ils sont déjà validés
       ou en cours (une validation humaine n'est jamais défaite en silence) ;
    2. quand tous les documents lisibles du fournisseur sont lus, la lettre de
       demande est mise en file de rédaction si elle ne l'a jamais été.
    Retourne les codes des pièces relancées."""
    import formulaires
    from generate import profil_entreprise

    relances = []
    try:  # dès que le fabricant est connu, ses documents déjà reçus sont repris
        reprendre_documents(session, dossier, acteur)
    except Exception as e:  # jamais silencieux, jamais bloquant
        journaliser(session, dossier.id, acteur, "reprise_echec", f"Bibliothèque fournisseur : {e}")
    codes_formulaires = formulaires.formulaires()
    for doc in dossier.documents:
        if doc.code in codes_formulaires and doc.statut in ("a_generer", "a_valider", "erreur"):
            try:
                resultat = formulaires.generer_formulaire(dossier, doc.code, doc.nom, Path(dossier.dossier_sortie),
                                                          profil_entreprise())
            except Exception as e:  # jamais silencieux
                journaliser(session, dossier.id, acteur, "generation_echec", f"{doc.nom} — {e}", document_id=doc.id)
                continue
            doc.statut, doc.fichier, doc.sources, doc.genere_le = "a_valider", resultat["fichier"], resultat["sources"], maintenant()
            journaliser(session, dossier.id, acteur, "formulaire_mis_a_jour",
                        f"{doc.nom} — {resultat['bilan']['a_completer']} case(s) à compléter", document_id=doc.id)
            relances.append(doc.code)
    # Les deux cas de la direction : que le fournisseur ait tout envoyé ou non, l'agent prépare
    # nos papiers dès que les documents REÇUS (du fournisseur ou fournis depuis la base) sont lus ;
    # une pièce manquante ne bloque pas (elle est réclamée) ; une lecture en erreur non plus.
    recus = [d for d in dossier.documents if d.nature == "a_fournir" and d.champs_a_extraire and d.fichier_recu]
    tout_lu = (bool(recus) and all(d.extraction_statut in ("terminee", "erreur") for d in recus)
               and any(d.extraction_statut == "terminee" for d in recus))
    a_lancer = [d for d in dossier.documents if d.nature == "a_rediger" and d.code not in codes_formulaires
                and d.statut == "a_generer"]
    if tout_lu:
        for doc in a_lancer:
            doc.statut = "en_file"
            journaliser(session, dossier.id, acteur, "generation_demandee",
                        f"{doc.nom} — lancée automatiquement : documents reçus lus", document_id=doc.id)
            relances.append(doc.code)
    session.commit()
    for doc in a_lancer if tout_lu else []:
        soumettre(doc.id)
    return relances


def reprendre_apres_redemarrage() -> int:
    """Au démarrage de l'API, les générations interrompues (arrêt du serveur)
    sont marquées en erreur plutôt que laissées « en cours » indéfiniment."""
    with db.SessionLocal() as session:
        interrompus = session.query(Document).filter(Document.statut.in_(db.STATUTS_EN_COURS)).all()
        for doc in interrompus:
            doc.statut = "erreur"
            doc.erreur = "Génération interrompue par un redémarrage du serveur — relancer."
            journaliser(session, doc.dossier_id, "système", "generation_echec", doc.erreur, document_id=doc.id)
        lectures = session.query(Document).filter(Document.extraction_statut.in_(("en_file", "en_cours"))).all()
        for doc in lectures:
            doc.extraction_statut = "erreur"
            doc.extraction_erreur = "Lecture interrompue par un redémarrage du serveur — relancer."
            journaliser(session, doc.dossier_id, "système", "lecture_echec", doc.extraction_erreur, document_id=doc.id)
        session.commit()
        return len(interrompus) + len(lectures)
