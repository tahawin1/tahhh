import { useCallback, useEffect, useState } from 'react'
import { api, type ApercuProjet, type DossierDetail, type Piece } from '../api'
import { ACTIONS, PAYS, STATUT_DOSSIER, STATUT_PIECE, dateHeure, dateLongue } from '../libelles'
import Progression from '../composants/Progression'
import LectureAgent from '../composants/LectureAgent'
import type { Session } from './Connexion'

export default function DetailDossier({ id, session }: { id: number; session: Session }) {
  const [dossier, setDossier] = useState<DossierDetail | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [action, setAction] = useState<string | null>(null)

  const charger = useCallback(
    () => api.dossier(id).then((d) => { setDossier(d); setErreur(null) }, (e: Error) => setErreur(e.message)),
    [id],
  )

  useEffect(() => { charger() }, [charger])

  // Suivi des tâches de fond (rédaction, lecture de documents) : rafraîchissement tant qu'une tâche tourne
  const enCours = dossier?.statut === 'generation_en_cours'
    || !!dossier?.documents.some((d) => d.extraction_statut === 'en_file' || d.extraction_statut === 'en_cours')
  useEffect(() => {
    if (!enCours) return
    const t = window.setInterval(charger, 5000)
    return () => window.clearInterval(t)
  }, [enCours, charger])

  async function executer(libelle: string, appel: () => Promise<DossierDetail>) {
    setAction(libelle)
    setErreur(null)
    try {
      setDossier(await appel())
    } catch (e) {
      setErreur((e as Error).message)
    } finally {
      setAction(null)
    }
  }

  if (!dossier) {
    return erreur ? <p className="message erreur" role="alert">{erreur}</p> : <p className="aide">Chargement…</p>
  }

  const aRediger = dossier.documents.filter((d) => d.nature === 'a_rediger')
  const aFournir = dossier.documents.filter((d) => d.nature === 'a_fournir')
  const aLancer = aRediger.filter((d) => ['a_generer', 'erreur', 'rejete'].includes(d.statut)).length
  const st = STATUT_DOSSIER[dossier.statut]

  return (
    <>
      <p><a href="#/">← Dossiers</a></p>
      <div className="titre-page">
        <div>
          <h1>Dossier n°{dossier.id} — {dossier.produit}</h1>
          <p className="secondaire">
            Origine : {PAYS[dossier.pays_origine] ?? dossier.pays_origine} · Classe {dossier.classe ?? 'non précisée'}
            {dossier.fournisseur && ` · ${dossier.fournisseur}`} · Créé le {dateHeure(dossier.cree_le)} par {dossier.cree_par}
            {' · '}Règles <code>{dossier.regles_version}</code>
          </p>
        </div>
        <span className={`pastille grande ${st.ton}`}>{st.libelle}</span>
      </div>

      <div className="carte resume">
        <Progression compteurs={dossier.compteurs} />
        {dossier.statut === 'pret_pour_depot_manuel' && dossier.prochain_creneau_depot ? (
          <p className="message ok">
            Toutes les pièces sont validées. Dépôt physique à effectuer <strong>manuellement</strong> auprès de la DMP —
            prochain créneau (mercredi ou jeudi) : <strong>{dateLongue(dossier.prochain_creneau_depot)}</strong>.
          </p>
        ) : (
          <p className="aide">
            Chaque pièce doit être validée par une personne nommée. Le dossier n'est jamais déposé par le système.
          </p>
        )}
      </div>

      {erreur && <p className="message erreur" role="alert">{erreur}</p>}

      <section>
        <div className="titre-section">
          <h2>Pièces à rédiger <span className="secondaire">— projets rédigés par l'IA, à relire</span></h2>
          <button
            className="principal"
            disabled={!!action || aLancer === 0}
            onClick={() => executer('generer', () => api.genererTout(dossier.id, session.nom))}
          >
            {aLancer ? `Lancer la rédaction (${aLancer} pièce${aLancer > 1 ? 's' : ''})` : 'Rien à rédiger'}
          </button>
        </div>
        {enCours && (
          <p className="aide">
            Rédaction en cours sur le serveur (plusieurs minutes par pièce sans GPU) — la page se met à jour automatiquement.
          </p>
        )}
        <div className="pieces">
          {aRediger.map((p) => (
            <CartePiece key={p.id} piece={p} dossierId={dossier.id} session={session} occupe={!!action} executer={executer} />
          ))}
        </div>
      </section>

      <section>
        <div className="titre-section">
          <h2>Pièces à obtenir <span className="secondaire">— émises par des tiers, jamais rédigées par le système</span></h2>
        </div>
        <div className="pieces">
          {aFournir.map((p) => (
            <CartePiece key={p.id} piece={p} dossierId={dossier.id} session={session} occupe={!!action} executer={executer} />
          ))}
        </div>
      </section>

      <section>
        <h2>Journal</h2>
        <ol className="journal">
          {dossier.evenements.map((e, i) => (
            <li key={i}>
              <span className="secondaire">{dateHeure(e.horodatage)}</span>
              <strong>{ACTIONS[e.action] ?? e.action}</strong>
              <span>{e.acteur}</span>
              {e.detail && <span className="secondaire">{e.detail}</span>}
            </li>
          ))}
        </ol>
      </section>
    </>
  )
}

function CartePiece({
  piece, dossierId, session, occupe, executer,
}: {
  piece: Piece
  dossierId: number
  session: Session
  occupe: boolean
  executer: (libelle: string, appel: () => Promise<DossierDetail>) => Promise<void>
}) {
  const [decision, setDecision] = useState<'valider' | 'rejeter' | null>(null)
  const [commentaire, setCommentaire] = useState('')
  const [sourcesOuvertes, setSourcesOuvertes] = useState(false)
  const [erreurFichier, setErreurFichier] = useState<string | null>(null)
  const [projet, setProjet] = useState<ApercuProjet | null>(null)

  async function basculerProjet() {
    if (projet) return setProjet(null)
    try {
      setProjet(await api.apercuProjet(dossierId, piece.id))
    } catch (e) {
      setErreurFichier((e as Error).message)
    }
  }
  const st = STATUT_PIECE[piece.statut]
  const redigee = piece.nature === 'a_rediger'

  const peutValider = redigee ? piece.statut === 'a_valider' : ['a_obtenir', 'rejete'].includes(piece.statut)
  const peutRejeter = redigee ? ['a_valider', 'valide'].includes(piece.statut) : ['a_obtenir', 'valide'].includes(piece.statut)
  const peutRegenerer = redigee && ['erreur', 'rejete', 'a_valider'].includes(piece.statut)
  const commentaireObligatoire = decision === 'rejeter' || (decision === 'valider' && !redigee)

  async function confirmer() {
    const c = commentaire.trim()
    await executer(decision!, () =>
      decision === 'valider'
        ? api.valider(dossierId, piece.id, session.nom, c || null)
        : api.rejeter(dossierId, piece.id, session.nom, c),
    )
    setDecision(null)
    setCommentaire('')
  }

  return (
    <article className={`piece ton-${st.ton}`}>
      <header>
        <h3>{piece.nom}</h3>
        <span className={`pastille ${st.ton}`}>{st.libelle}</span>
      </header>

      <div className="drapeaux">
        {!redigee && <span>Émise par {piece.fourni_par}</span>}
        {piece.traduction_requise && <span className="drapeau">Traduction assermentée requise</span>}
        {piece.legalisation_requise && <span className="drapeau">Légalisation / apostille requise</span>}
      </div>

      {piece.erreur && <p className="message erreur">{piece.erreur}</p>}
      {piece.valide_par && (
        <p className="secondaire">
          {piece.statut === 'rejete' ? 'Rejetée' : 'Validée'} par <strong>{piece.valide_par}</strong> le {dateHeure(piece.valide_le)}
          {piece.commentaire && <> — « {piece.commentaire} »</>}
        </p>
      )}
      {redigee && piece.genere_le && <p className="secondaire">Projet rédigé le {dateHeure(piece.genere_le)}</p>}

      {piece.sources && piece.sources.length > 0 && (
        <div className="sources">
          <button className="lien" onClick={() => setSourcesOuvertes(!sourcesOuvertes)}>
            {sourcesOuvertes ? 'Masquer' : 'Voir'} les {piece.sources.length} extraits réglementaires utilisés
          </button>
          {sourcesOuvertes && (
            <ul>
              {piece.sources.map((s, i) => (
                <li key={i}>{s.texte_source} — version du {s.date_version}{s.chunk_index !== undefined && `, extrait n°${s.chunk_index}`}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {erreurFichier && <p className="message erreur">{erreurFichier}</p>}

      {piece.lisible_par_agent && (
        <LectureAgent piece={piece} dossierId={dossierId} acteur={session.nom} occupe={occupe} executer={executer} />
      )}

      {projet && (
        <div className="projet" aria-label={`Projet : ${piece.nom}`}>
          {projet.paragraphes.map((p, i) =>
            p.genre === 'titre' ? <h4 key={i}>{p.texte}</h4>
              : p.genre === 'puce' ? <p key={i} className="puce">{p.texte}</p>
              : <p key={i}>{p.texte}</p>,
          )}
        </div>
      )}

      {decision ? (
        <div className="decision">
          <label>
            {decision === 'rejeter'
              ? 'Motif du rejet (obligatoire)'
              : redigee
                ? 'Commentaire (facultatif)'
                : 'Pièce reçue et vérifiée : référence, date de réception… (obligatoire)'}
            <textarea value={commentaire} onChange={(e) => setCommentaire(e.target.value)} rows={2} autoFocus />
          </label>
          <div className="actions">
            <button
              className={decision === 'valider' ? 'principal' : 'danger'}
              disabled={occupe || (commentaireObligatoire && !commentaire.trim())}
              onClick={confirmer}
            >
              Confirmer {decision === 'valider' ? 'la validation' : 'le rejet'} ({session.nom})
            </button>
            <button onClick={() => { setDecision(null); setCommentaire('') }}>Annuler</button>
          </div>
        </div>
      ) : (
        <div className="actions">
          {piece.fichier_disponible && (
            <>
              <button onClick={basculerProjet}>{projet ? 'Masquer le projet' : 'Lire le projet'}</button>
              <button onClick={() => api.telecharger(dossierId, piece).catch((e: Error) => setErreurFichier(e.message))}>
                Télécharger (.docx)
              </button>
            </>
          )}
          {peutValider && (
            <button className="principal" disabled={occupe} onClick={() => setDecision('valider')}>
              {redigee ? 'Valider le projet' : 'Marquer reçue et vérifiée'}
            </button>
          )}
          {peutRejeter && <button className="danger" disabled={occupe} onClick={() => setDecision('rejeter')}>Rejeter</button>}
          {peutRegenerer && (
            <button disabled={occupe} onClick={() => executer('regenerer', () => api.genererPiece(dossierId, piece.id, session.nom))}>
              {piece.statut === 'a_valider' ? 'Régénérer' : 'Relancer la rédaction'}
            </button>
          )}
        </div>
      )}
    </article>
  )
}
