import { useEffect, useState, type FormEvent } from 'react'
import { api, type Apercu } from '../api'
import { PAYS, PAYS_PUCE } from '../libelles'
import Icone from '../composants/Icone'
import type { Session } from './Connexion'

const CLASSES = [
  { id: 'I', aide: 'Risque faible' },
  { id: 'IS', aide: 'Classe I stérile' },
  { id: 'IM', aide: 'Classe I avec mesurage' },
  { id: 'IR', aide: 'Classe I réutilisable' },
  { id: 'IIA', aide: 'Risque modéré' },
  { id: 'IIB', aide: 'Risque élevé' },
  { id: 'III', aide: 'Risque très élevé' },
]
const ORIGINES = [
  { id: 'chine', autorite: 'Certificat NMPA' },
  { id: 'inde', autorite: 'Certificat CDSCO' },
  { id: 'union_europeenne', autorite: 'Marquage CE' },
  { id: 'etats_unis', autorite: 'FDA : 510(k) / PMA + CFG' },
  { id: 'coree_du_sud', autorite: 'MFDS + certificat de libre vente' },
  { id: 'pakistan', autorite: 'DRAP + certificat de libre vente' },
  { id: 'autre', autorite: 'Certificat de libre vente' },
]

export default function NouveauDossier({ session }: { session: Session }) {
  const [produit, setProduit] = useState('')
  const [fournisseur, setFournisseur] = useState('')
  const [pays, setPays] = useState('chine')
  const [classe, setClasse] = useState('IIB')
  const [equipement, setEquipement] = useState(false)
  const [valeur, setValeur] = useState('')
  const valeurUsd = valeur.trim() === '' ? null : Number(valeur.replace(',', '.'))
  const [apercu, setApercu] = useState<Apercu | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [enCours, setEnCours] = useState(false)

  // Aperçu en direct des pièces requises : décidé par le moteur de règles du
  // backend (YAML, déterministe), jamais par le frontend ni par l'IA.
  useEffect(() => {
    let actif = true
    api.apercu(pays, 'aperçu', classe, equipement, valeurUsd).then(
      (a) => { if (actif) { setApercu(a); setErreur(null) } },
      (e: Error) => { if (actif) { setApercu(null); setErreur(e.message) } },
    )
    return () => { actif = false }
  }, [pays, classe, equipement, valeurUsd])

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
        equipement,
        valeur_unitaire_usd: valeurUsd,
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
    <div className="nouveau">
      <a className="lien-retour" href="#/"><Icone nom="retour" taille={18} /> Tableau de bord</a>
      <header className="page-entete">
        <p className="surtitre">Nouveau dossier</p>
        <h1>Quel dispositif voulez-vous enregistrer ?</h1>
        <p className="hero-sous">Trois informations suffisent : les règles officielles donnent aussitôt la liste des pièces.</p>
      </header>

      <div className="nouveau-grille">
        <form className="panneau formulaire" onSubmit={creer}>
          <fieldset>
            <legend><span className="numero">1</span> Le dispositif</legend>
            <label>
              Dispositif médical
              <input value={produit} onChange={(e) => setProduit(e.target.value)} required placeholder="ex. Prothèse totale de hanche" />
            </label>
            <label>
              <span>Fournisseur / fabricant <span className="facultatif">(facultatif)</span></span>
              <input value={fournisseur} onChange={(e) => setFournisseur(e.target.value)} placeholder="ex. Hangzhou Orthopaedics Co., Ltd." />
            </label>
          </fieldset>

          <fieldset>
            <legend><span className="numero">2</span> Pays d'origine</legend>
            <div className="tuiles" role="radiogroup" aria-label="Pays d'origine">
              {ORIGINES.map((o) => {
                const puce = PAYS_PUCE[o.id]
                return (
                  <label key={o.id} className={`tuile ${pays === o.id ? 'choisie' : ''}`}>
                    <input type="radio" name="pays" value={o.id} checked={pays === o.id} onChange={() => setPays(o.id)} />
                    <span className={`puce-pays ${puce.teinte}`} aria-hidden>{puce.code}</span>
                    <span className="tuile-texte">
                      <strong>{PAYS[o.id]}</strong>
                      <small>{o.autorite}</small>
                    </span>
                  </label>
                )
              })}
            </div>
          </fieldset>

          <fieldset>
            <legend><span className="numero">3</span> Classe de risque (Maroc)</legend>
            <div className="segments" role="radiogroup" aria-label="Classe de risque">
              {CLASSES.map((c) => (
                <label key={c.id} className={`segment ${classe === c.id ? 'choisi' : ''}`}>
                  <input type="radio" name="classe" value={c.id} checked={classe === c.id} onChange={() => setClasse(c.id)} />
                  <strong>{c.id}</strong>
                  <small>{c.aide}</small>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend><span className="numero">4</span> Nature et valeur</legend>
            <label className="case-a-cocher">
              <input type="checkbox" checked={equipement} onChange={(e) => setEquipement(e.target.checked)} />
              <span>Équipement médical <small>(ajoute note descriptive, documentation technique et manuel ; pas d'échantillon)</small></span>
            </label>
            <label>
              <span>Valeur unitaire du produit en dollars <span className="facultatif">(échantillon sous 500 $, facture pro-forma au-delà)</span></span>
              <input type="number" min="0" step="0.01" inputMode="decimal" value={valeur}
                onChange={(e) => setValeur(e.target.value)} placeholder="ex. 120" />
            </label>
          </fieldset>

          {erreur && <p className="message erreur" role="alert">{erreur}</p>}
          <button className="principal grand" disabled={enCours || !produit.trim()}>
            {enCours ? 'Création…' : <>Créer le dossier <Icone nom="suite" /></>}
          </button>
        </form>

        <aside className="panneau apercu" aria-live="polite">
          <h2>Pièces exigées</h2>
          <p className="aide">Décidé par les règles officielles selon le pays et la classe, jamais par l'IA.</p>
          {!apercu && !erreur && <p className="aide">Chargement…</p>}
          {apercu && (
            <>
              <div className="groupe-pieces ia">
                <h3><Icone nom="ia" taille={18} /> L'agent les rédige ({aRediger.length})</h3>
                <ul>{aRediger.map((d) => <li key={d.id}>{d.nom}</li>)}</ul>
              </div>
              <div className="groupe-pieces fournisseur">
                <h3><Icone nom="deposer" taille={18} /> Le fournisseur les envoie ({aFournir.length})</h3>
                <ul>
                  {aFournir.map((d) => (
                    <li key={d.id}>
                      {d.nom}
                      <small>
                        Émise par {d.fourni_par}
                        {d.traduction_requise && ' · traduction assermentée'}
                        {d.legalisation_requise && ' · légalisation'}
                      </small>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
