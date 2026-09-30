import { useState, type FormEvent } from 'react'
import { api, definirCleApi, ErreurApi, type Sante } from '../api'

export interface Session {
  nom: string
  cleApi: string
}

// Identification minimale en attendant Keycloak (voir CLAUDE.md) : le nom
// sert à tracer qui crée, génère, valide ou rejette chaque pièce ; la clé
// d'API est vérifiée par le backend si celui-ci en exige une.
export default function Connexion({ sante, surConnexion }: { sante: Sante | null; surConnexion: (s: Session) => void }) {
  const [nom, setNom] = useState('')
  const [cle, setCle] = useState('')
  const [erreur, setErreur] = useState<string | null>(null)
  const [enCours, setEnCours] = useState(false)
  const cleRequise = sante?.authentification === 'cle_api'

  async function soumettre(e: FormEvent) {
    e.preventDefault()
    setErreur(null)
    setEnCours(true)
    definirCleApi(cle.trim())
    try {
      await api.dossiers() // vérifie la clé auprès du backend
      surConnexion({ nom: nom.trim(), cleApi: cle.trim() })
    } catch (err) {
      definirCleApi('')
      setErreur(err instanceof ErreurApi && err.status === 401 ? "Clé d'API invalide." : (err as Error).message)
    } finally {
      setEnCours(false)
    }
  }

  return (
    <div className="etroite">
      <form className="carte" onSubmit={soumettre}>
        <h1>Connexion</h1>
        <p className="aide">
          Votre nom est enregistré dans le journal de chaque dossier pour tracer qui rédige, valide ou rejette une pièce.
        </p>
        <label>
          Nom et prénom
          <input value={nom} onChange={(e) => setNom(e.target.value)} required minLength={2} autoFocus placeholder="ex. Salma Bennani" />
        </label>
        <label>
          <span>Clé d'API {sante?.authentification === 'aucune' && <span className="facultatif">(non exigée par ce serveur)</span>}</span>
          <input type="password" value={cle} onChange={(e) => setCle(e.target.value)} required={cleRequise} autoComplete="off" />
        </label>
        {erreur && <p className="message erreur" role="alert">{erreur}</p>}
        <button className="principal" disabled={enCours || nom.trim().length < 2}>
          {enCours ? 'Vérification…' : 'Accéder au tableau de bord'}
        </button>
      </form>
    </div>
  )
}
