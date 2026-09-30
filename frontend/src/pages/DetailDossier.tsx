import { useCallback, useEffect, useState } from 'react'
import { api, type ApercuProjet, type DossierDetail, type Piece } from '../api'
import { ACTIONS, PAYS, PAYS_PUCE, STATUT_DOSSIER, STATUT_PIECE, dateHeure, dateLongue } from '../libelles'
import { Anneau } from '../composants/Progression'
import Icone from '../composants/Icone'
import { etapes, prochaineAction } from '../parcours'
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
    return erreur ? <p className="message erreur" role="alert">{erreur}</p> : <p className="aide">Chargement du dossier…</p>
  }

  const aRediger = dossier.documents.filter((d) => d.nature === 'a_rediger')
  const aFournir = dossier.documents.filter((d) => d.nature === 'a_fournir')
  const aLancer = aRediger.filter((d) => ['a_generer', 'erreur', 'rejete'].includes(d.statut)).length
  const st = STATUT_DOSSIER[dossier.statut]
  const puce = PAYS_PUCE[dossier.pays_origine] ?? PAYS_PUCE.autre
  const frise = etapes(dossier)
  const suite = prochaineAction(dossier)

  return (
    <div className="detail">
      <a className="lien-retour" href="#/"><Icone nom="retour" taille={18} /> Tableau de bord</a>

      <header className="dossier-entete">
        <Anneau valides={dossier.compteurs.valides} total={dossier.compteurs.total} taille={84} />
        <div className="dossier-titre">
          <p className="surtitre">Dossier n°{dossier.id} · {PAYS[dossier.pays_origine] ?? dossier.pays_origine} → Maroc</p>
          <h1>{dossier.produit}</h1>
          <div className="etiquettes">
            <span className={`puce-pays ${puce.teinte}`}>{puce.code}</span>
            <span className="etiquette">Classe {dossier.classe ?? 'non précisée'}</span>
            {dossier.fournisseur && <span className="etiquette"><Icone nom="monde" taille={14} /> {dossier.fournisseur}</span>}
            <span className="etiquette discrete">Créé le {dateHeure(dossier.cree_le)} par {dossier.cree_par}</span>
            <span className="etiquette discrete" title="Version des règles utilisées">Règles {dossier.regles_version}</span>
          </div>
        </div>
        <span className={`pastille grande ${st.ton}`}>{st.libelle}</span>
      </header>

      <ol className="frise" aria-label="Avancement du dossier">
        {frise.map((e, i) => (
          <li key={e.cle} className={`etape ${e.etat}`} aria-current={e.etat === 'en_cours' ? 'step' : undefined}>
            <span className="etape-rond">{e.etat === 'fait' ? <Icone nom="valide" taille={16} /> : i + 1}</span>
            <span className="etape-texte">
              <strong>{e.titre}</strong>
              <small>{e.detail}</small>
            </span>
          </li>
        ))}
      </ol>

      <div className={`prochaine-action ${suite.ton}`}>
        <span className="icone-rond"><Icone nom={suite.ton === 'ok' ? 'valide' : suite.ton === 'erreur' ? 'alerte' : suite.ton === 'encours' ? 'ia' : 'cible'} /></span>
        <div>
          <p className="surtitre">Prochaine action</p>
          <strong>{suite.titre}</strong>
          {suite.ton === 'ok' && dossier.prochain_creneau_depot ? (
            <p>Dépôt physique à effectuer <strong>manuellement</strong> à l'AMMPS — prochain créneau : <strong>{dateLongue(dossier.prochain_creneau_depot)}</strong>.</p>
          ) : suite.detail && <p>{suite.detail}</p>}
        </div>
      </div>

      {erreur && <p className="message erreur" role="alert">{erreur}</p>}

      <section>
        <div className="section-titre">
          <h2><span className="icone-rond accent petit"><Icone nom="ia" taille={16} /></span> Rédigées par l'agent <span className="compte">{aRediger.length}</span></h2>
          <button
            className="principal"
            disabled={!!action || aLancer === 0}
            onClick={() => executer('generer', () => api.genererTout(dossier.id, session.nom))}
          >
            <Icone nom="ia" taille={18} />
            {aLancer ? `Lancer la rédaction (${aLancer} pièce${aLancer > 1 ? 's' : ''})` : 'Rien à rédiger'}
          </button>
        </div>
        <p className="aide">Projets rédigés par l'IA à partir des règles et des textes officiels : à relire puis valider.</p>
        <div className="pieces">
          {aRediger.map((p) => (
            <CartePiece key={p.id} piece={p} dossierId={dossier.id} session={session} occupe={!!action} executer={executer} />
          ))}
        </div>
      </section>

      <section>
        <div className="section-titre">
          <h2><span className="icone-rond neutre petit"><Icone nom="deposer" taille={16} /></span> Envoyées par le fournisseur <span className="compte">{aFournir.length}</span></h2>
        </div>
        <p className="aide">Documents émis par des tiers (autorités, organismes, fabricant) : jamais rédigés par le système. Déposez-les, l'agent les lit et contrôle chaque valeur.</p>
        <div className="pieces">
          {aFournir.map((p) => (
            <CartePiece key={p.id} piece={p} dossierId={dossier.id} session={session} occupe={!!action} executer={executer} />
          ))}
        </div>
      </section>

      <section>
        <div className="section-titre">
          <h2><span className="icone-rond neutre petit"><Icone nom="journal" taille={16} /></span> Journal</h2>
        </div>
        <ol className="journal">
          {dossier.evenements.map((e, i) => (
            <li key={i} className={e.acteur.startsWith('agent') || e.acteur === 'système' ? 'par-agent' : 'par-humain'}>
              <span className="journal-point" aria-hidden />
              <div>
                <p><strong>{ACTIONS[e.action] ?? e.action}</strong> · {e.acteur}</p>
                {e.detail && <p className="secondaire">{e.detail}</p>}
              </div>
              <time className="secondaire">{dateHeure(e.horodatage)}</time>
            </li>
          ))}
        </ol>
      </section>
    </div>
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
        <span className={`icone-piece ${st.ton}`}><Icone nom={piece.statut === 'valide' ? 'valide' : redigee ? 'document' : 'deposer'} taille={18} /></span>
        <h3>{piece.numero != null && <span className="numero-piece">Pièce {piece.numero}</span>}{piece.nom}</h3>
        <span className={`pastille ${st.ton}`}>{st.libelle}</span>
      </header>

      <div className="drapeaux">
        {!redigee && <span>Émise par {piece.fourni_par}</span>}
        {piece.traduction_requise && <span className="drapeau">Traduction assermentée requise</span>}
        {piece.legalisation_requise && <span className="drapeau">Légalisation / apostille requise</span>}
        {piece.source && <span title="Fondement de l'exigence">{piece.source}</span>}
      </div>
      {piece.remarque && <p className="remarque-piece"><Icone nom="alerte" taille={16} /> {piece.remarque}</p>}

      {piece.activite && (
        <div className="agent-en-direct" aria-live="polite">
          <div className="agent-titre"><span className="pulsation" aria-hidden /><Icone nom="ia" taille={16} /> {piece.activite}</div>
          {piece.progression && <pre className="agent-flux">{piece.progression}</pre>}
        </div>
      )}

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
              <button onClick={basculerProjet}><Icone nom="lire" taille={16} />{projet ? 'Masquer le projet' : 'Lire le projet'}</button>
              <button onClick={() => api.telecharger(dossierId, piece).catch((e: Error) => setErreurFichier(e.message))}>
                <Icone nom="telecharger" taille={16} />Télécharger (.docx)
              </button>
            </>
          )}
          {peutValider && (
            <button className="principal" disabled={occupe} onClick={() => setDecision('valider')}>
              <Icone nom="valide" taille={16} />{redigee ? 'Valider le projet' : 'Marquer reçue et vérifiée'}
            </button>
          )}
          {peutRejeter && <button className="danger" disabled={occupe} onClick={() => setDecision('rejeter')}>Rejeter</button>}
          {peutRegenerer && (
            <button disabled={occupe} onClick={() => executer('regenerer', () => api.genererPiece(dossierId, piece.id, session.nom))}>
              <Icone nom="relancer" taille={16} />{piece.statut === 'a_valider' ? 'Régénérer' : 'Relancer la rédaction'}
            </button>
          )}
        </div>
      )}
    </article>
  )
}
