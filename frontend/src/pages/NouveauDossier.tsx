import { useEffect, useState, type FormEvent } from 'react'
import { api, type Apercu } from '../api'
import { PAYS } from '../libelles'
import type { Session } from './Connexion'

const CLASSES = ['I', 'IIA', 'IIB', 'III']

export default function NouveauDossier({ session }: { session: Session }) {
  const [produit, setProduit] = useState('')
  const [fournisseur, setFournisseur] = useState('')
  const [pays, setPays] = useState('chine')
  const [classe, setClasse] = useState('IIB')
  const [apercu, setApercu] = useState<Apercu | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [enCours, setEnCours] = useState(false)

  // Aperçu en direct des pièces requises : décidé par le moteur de règles du
  // backend (YAML, déterministe), jamais par le frontend ni par l'IA.
  useEffect(() => {
    let actif = true
    api.apercu(pays, 'aperçu', classe).then(
      (a) => { if (actif) { setApercu(a); setErreur(null) } },
      (e: Error) => { if (actif) { setApercu(null); setErreur(e.message) } },
    )
    return () => { actif = false }
  }, [pays, classe])

  async function creer(e: FormEvent) {
    e.preventDefault()
    setEnCours(true)
    setErreur(null)
    try {
      const d = await api.creer({
        pays_origine: pays,
        produit: produit.trim(),
        classe,
        fournisseur: fournisseur.trim() || null,
        cree_par: session.nom,
      })
      window.location.hash = `#/dossiers/${d.id}`
    } catch (err) {
      setErreur((err as Error).message)
      setEnCours(false)
    }
  }

  const aRediger = apercu?.documents.filter((d) => d.nature === 'a_rediger') ?? []
  const aFournir = apercu?.documents.filter((d) => d.nature === 'a_fournir') ?? []

  return (
    <>
      <p><a href="#/">← Dossiers</a></p>
      <h1>Nouveau dossier</h1>
      <div className="deux-colonnes">
        <form className="carte" onSubmit={creer}>
          <label>
            Dispositif médical
            <input value={produit} onChange={(e) => setProduit(e.target.value)} required placeholder="ex. Prothèse orthopédique de hanche" />
          </label>
          <label>
            <span>Fournisseur / fabricant <span className="facultatif">(facultatif)</span></span>
            <input value={fournisseur} onChange={(e) => setFournisseur(e.target.value)} />
          </label>
          <div className="ligne">
            <label>
              Pays d'origine
              <select value={pays} onChange={(e) => setPays(e.target.value)}>
                {['chine', 'inde', 'union_europeenne', 'autre'].map((p) => <option key={p} value={p}>{PAYS[p]}</option>)}
              </select>
            </label>
            <label>
              Classe (Maroc)
              <select value={classe} onChange={(e) => setClasse(e.target.value)}>
                {CLASSES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>
          {erreur && <p className="message erreur" role="alert">{erreur}</p>}
          <button className="principal" disabled={enCours || !produit.trim()}>
            {enCours ? 'Création…' : 'Créer le dossier'}
          </button>
        </form>

        <section className="carte" aria-live="polite">
          <h2>Pièces requises</h2>
          <p className="aide">Liste décidée par le moteur de règles (règles marocaines, pays d'origine, classe).</p>
          {!apercu && !erreur && <p className="aide">Chargement…</p>}
          {apercu && (
            <>
              <h3>À rédiger ({aRediger.length})</h3>
              <ul className="liste-pieces">
                {aRediger.map((d) => <li key={d.id}>{d.nom}</li>)}
              </ul>
              <h3>À obtenir auprès du fournisseur ({aFournir.length})</h3>
              <ul className="liste-pieces">
                {aFournir.map((d) => (
                  <li key={d.id}>
                    {d.nom}
                    <div className="secondaire">
                      Émise par {d.fourni_par}
                      {d.traduction_requise && ' · traduction assermentée'}
                      {d.legalisation_requise && ' · légalisation'}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </>
  )
}
