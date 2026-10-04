import { useRef, useState } from 'react'
import { api, type Affectation, type DossierDetail } from '../api'
import Icone from './Icone'

// Dépôt groupé des documents du fournisseur : le serveur range chaque fichier
// dans sa pièce (numéro en tête du nom, sinon mots du nom), puis l'agent les lit.
export default function DepotGroupe({
  dossierId, acteur, occupe, surDossier,
}: {
  dossierId: number
  acteur: string
  occupe: boolean
  surDossier: (d: DossierDetail) => void
}) {
  const entree = useRef<HTMLInputElement>(null)
  const [survol, setSurvol] = useState(false)
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)
  const [affectations, setAffectations] = useState<Affectation[] | null>(null)

  async function envoyer(fichiers: File[]) {
    if (!fichiers.length) return
    setEnvoi(true)
    setErreur(null)
    try {
      const r = await api.deposerGroupe(dossierId, fichiers, acteur)
      setAffectations(r.affectations)
      surDossier(r.dossier)
    } catch (e) {
      setErreur((e as Error).message)
    } finally {
      setEnvoi(false)
    }
  }

  const [reprise, setReprise] = useState<string | null>(null)

  async function reprendre() {
    setEnvoi(true)
    setErreur(null)
    setReprise(null)
    try {
      const debut = Date.now() - 60_000  // marge d'horloge entre le serveur et le poste
      const d = await api.reprendreDocuments(dossierId, acteur)
      const reprises = d.evenements.filter((e) => e.action === 'document_repris' && Date.parse(e.horodatage) >= debut)
      setReprise(reprises.length
        ? `${reprises.length} pièce(s) fournie(s) par l'agent depuis la base : à relire et valider comme les autres.`
        : 'Rien à fournir depuis la base : pas de dossier accepté ou traité du même fabricant (ou du même produit), ou pièces déjà là.')
      surDossier(d)
    } catch (e) {
      setErreur((e as Error).message)
    } finally {
      setEnvoi(false)
    }
  }

  const ranges = affectations?.filter((a) => a.piece != null) ?? []
  const nonRanges = affectations?.filter((a) => a.piece == null) ?? []

  return (
    <div className="depot-groupe">
      <input
        ref={entree}
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
        hidden
        onChange={(ev) => {
          const fichiers = Array.from(ev.target.files ?? [])
          ev.target.value = ''
          envoyer(fichiers)
        }}
      />
      <button
        type="button"
        className={`zone-depot ${survol ? 'survol' : ''}`}
        disabled={occupe || envoi}
        onClick={() => entree.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setSurvol(true) }}
        onDragLeave={() => setSurvol(false)}
        onDrop={(e) => { e.preventDefault(); setSurvol(false); envoyer(Array.from(e.dataTransfer.files)) }}
      >
        <span className="icone-rond accent"><Icone nom="deposer" /></span>
        <strong>{envoi ? 'Envoi et rangement en cours…' : 'Déposer tous les documents du fournisseur'}</strong>
        <span className="secondaire">
          Glissez ici tous les PDF reçus (certificat CE, ISO 13485, DoC, étiquettes, notice, catalogue…) :
          chacun est rangé dans sa pièce, puis lu par l'agent.
        </span>
      </button>
      <div className="actions">
        <button type="button" disabled={occupe || envoi} onClick={reprendre}
          title="Attestation, déclaration de conformité, étiquettes, notice, photos, catalogue : repris des dossiers acceptés ou traités du même fabricant (et du même produit). Les certificats (CE, ISO…) restent envoyés par le fournisseur.">
          <Icone nom="suite" taille={16} />Fournir les pièces depuis la base (tout sauf les certificats)
        </button>
      </div>
      {reprise && <p className="message" aria-live="polite">{reprise}</p>}
      {erreur && <p className="message erreur" role="alert">{erreur}</p>}
      {affectations && (
        <div className="affectations" aria-live="polite">
          {ranges.length > 0 && (
            <ul>
              {ranges.map((a, i) => (
                <li key={i}><Icone nom="valide" taille={14} /> {a.fichier} → <strong>pièce {a.piece}</strong> <span className="secondaire">({a.raison})</span></li>
              ))}
            </ul>
          )}
          {nonRanges.length > 0 && (
            <ul className="non-ranges">
              {nonRanges.map((a, i) => (
                <li key={i}><Icone nom="alerte" taille={14} /> {a.fichier} : {a.raison}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
