import { useEffect, useState } from 'react'
import { api, type Bilan, type LigneBilan } from '../api'
import Icone from './Icone'

const CAS: Record<Bilan['cas'], { ton: string; surtitre: string }> = {
  complet: { ton: 'ok', surtitre: 'Cas 1 — le fournisseur a tout envoyé' },
  complete_par_agent: { ton: 'encours', surtitre: "Cas 2 — pièces complémentaires fournies par l'agent" },
  incomplet: { ton: 'attention', surtitre: 'Cas 2 — pièces encore à réclamer au fournisseur' },
}

const ETAT: Record<string, { libelle: string; ton: string }> = {
  recu: { libelle: 'Reçue du fournisseur', ton: 'ok' },
  fourni_par_agent: { libelle: "Fournie par l'agent", ton: 'encours' },
  manquant: { libelle: 'À réclamer', ton: 'erreur' },
  illisible: { libelle: 'Illisible', ton: 'erreur' },
  a_remettre: { libelle: 'Objet à remettre', ton: 'neutre' },
  redige: { libelle: "Préparée par l'agent", ton: 'encours' },
  en_cours: { libelle: 'En rédaction', ton: 'encours' },
  a_rediger: { libelle: 'Bientôt préparée', ton: 'neutre' },
  erreur: { libelle: 'Erreur', ton: 'erreur' },
  a_fournir_par_nous: { libelle: 'À fournir par nous', ton: 'attention' },
  a_signer: { libelle: 'À signer', ton: 'attention' },
}

function Ligne({ l }: { l: LigneBilan }) {
  const e = ETAT[l.etat] ?? { libelle: l.etat, ton: 'neutre' }
  return (
    <li className="ligne-bilan">
      <span className="numero-bilan">{l.numero ?? '—'}</span>
      <span className="nom-bilan">
        <strong>{l.nom}</strong>
        <small className="secondaire">{l.valide ? 'Validée' : l.a_faire}{l.origine ? ` — ${l.origine}` : ''}</small>
      </span>
      <span className={`pastille ${l.valide ? 'ok' : e.ton}`}>{l.valide ? 'Validée' : e.libelle}</span>
    </li>
  )
}

// Bilan de l'agent : que le fournisseur ait tout envoyé ou non, ce que l'agent
// a fourni ou préparé, ce qui manque, et nos papiers à compléter. Rien n'est
// validé ni envoyé ici.
export default function BilanAgent({ dossierId, version }: { dossierId: number; version: string }) {
  const [bilan, setBilan] = useState<Bilan | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [relance, setRelance] = useState(false)

  useEffect(() => {
    api.bilan(dossierId).then((b) => { setBilan(b); setErreur(null) }, (e: Error) => setErreur(e.message))
  }, [dossierId, version])

  if (erreur) return <p className="message erreur">{erreur}</p>
  if (!bilan) return <p className="aide">Calcul du bilan…</p>
  const cas = CAS[bilan.cas]

  return (
    <div className={`bilan-agent ${cas.ton}`}>
      <p className="surtitre">{cas.surtitre}</p>
      <strong>{bilan.titre}</strong>
      <p className="secondaire">
        {bilan.compteurs.recues} reçue(s) du fournisseur · {bilan.compteurs.fournies_par_agent} fournie(s) par l'agent
        · {bilan.compteurs.manquantes} à réclamer · {bilan.points_humains_a_cocher} point(s) de la checklist à cocher
      </p>
      <div className="colonnes-bilan">
        <div>
          <h3><Icone nom="deposer" taille={16} /> Pièces du fournisseur</h3>
          <ul>{bilan.fournisseur.map((l) => <Ligne key={l.code} l={l} />)}</ul>
        </div>
        <div>
          <h3><Icone nom="document" taille={16} /> Nos papiers (à compléter)</h3>
          <ul>{bilan.notre_part.map((l, i) => <Ligne key={`${l.code}-${i}`} l={l} />)}</ul>
        </div>
      </div>
      {bilan.relance && (
        <div className="actions">
          <button onClick={() => setRelance(!relance)}>
            <Icone nom="journal" taille={16} />{relance ? 'Masquer' : 'Voir'} la relance au fournisseur (à envoyer par vous)
          </button>
        </div>
      )}
      {relance && bilan.relance && <pre className="relance">{bilan.relance}</pre>}
    </div>
  )
}
