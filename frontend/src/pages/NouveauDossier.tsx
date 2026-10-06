import { useEffect, useState, type FormEvent } from 'react'
import { api, type Apercu, type BaseAcceptes, type Preuve } from '../api'
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

// Preuve de mise sur le marché (pièce 4), distincte du pays du fabricant : un
// fabricant chinois ou indien marqué CE présente son certificat CE.
const PREUVES: { id: Preuve; titre: string; aide: string }[] = [
  { id: 'auto', titre: "L'agent la détecte", aide: 'dans la pièce 4 reçue (recommandé)' },
  { id: 'nationale', titre: 'Autorité du pays', aide: 'NMPA, CDSCO, FDA, MFDS…' },
  { id: 'ce', titre: 'Certificat CE', aide: 'fabricant marqué CE' },
]

export default function NouveauDossier({ session }: { session: Session }) {
  const [produit, setProduit] = useState('')
  const [fournisseur, setFournisseur] = useState('')
  const [pays, setPays] = useState('chine')
  const [classe, setClasse] = useState('IIB')
  const [preuve, setPreuve] = useState<Preuve>('auto')
  const fabricantEuropeen = pays === 'union_europeenne'
  const [equipement, setEquipement] = useState(false)
  const [distributeur, setDistributeur] = useState(false)
  const [valeur, setValeur] = useState('')
  const valeurUsd = valeur.trim() === '' ? null : Number(valeur.replace(',', '.'))
  const [apercu, setApercu] = useState<Apercu | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [enCours, setEnCours] = useState(false)

  // Aperçu en direct des pièces requises : décidé par le moteur de règles du
  // backend (YAML, déterministe), jamais par le frontend ni par l'IA.
  useEffect(() => {
    let actif = true
    api.apercu(pays, 'aperçu', classe, equipement, valeurUsd, distributeur, fabricantEuropeen ? 'auto' : preuve).then(
      (a) => { if (actif) { setApercu(a); setErreur(null) } },
      (e: Error) => { if (actif) { setApercu(null); setErreur(e.message) } },
    )
    return () => { actif = false }
  }, [pays, classe, equipement, valeurUsd, distributeur, preuve, fabricantEuropeen])

  // Dossiers acceptés de ce pays déjà dans la base : l'agent s'en inspire.
  const [base, setBase] = useState<BaseAcceptes | null>(null)
  useEffect(() => {
    let actif = true
    api.baseAcceptes(pays, classe).then((b) => { if (actif) setBase(b) }, () => { if (actif) setBase(null) })
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
        equipement,
        valeur_unitaire_usd: valeurUsd,
        fournisseur_distributeur: distributeur,
        preuve: fabricantEuropeen ? 'auto' : preuve,
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
            {!fabricantEuropeen && (
              <div className="preuve-choix">
                <p className="aide">Preuve de mise sur le marché (pièce 4)</p>
                <div className="segments" role="radiogroup" aria-label="Preuve de mise sur le marché">
                  {PREUVES.map((p) => (
                    <label key={p.id} className={`segment ${preuve === p.id ? 'choisi' : ''}`}>
                      <input type="radio" name="preuve" value={p.id} checked={preuve === p.id} onChange={() => setPreuve(p.id)} />
                      <strong>{p.titre}</strong>
                      <small>{p.aide}</small>
                    </label>
                  ))}
                </div>
              </div>
            )}
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
            <label className="case-a-cocher">
              <input type="checkbox" checked={distributeur} onChange={(e) => setDistributeur(e.target.checked)} />
              <span>Le fournisseur est un distributeur, pas le fabricant <small>(ajoute la lettre de lien fabricant – distributeur)</small></span>
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
          {base && (
            <div className="groupe-pieces base">
              <h3><Icone nom="ia" taille={18} /> Base de l'agent pour ce pays ({base.total} dossier{base.total > 1 ? 's' : ''} accepté{base.total > 1 ? 's' : ''})</h3>
              {base.total === 0 ? (
                <p className="aide">Aucun dossier accepté de ce pays : l'agent rédige d'après les textes officiels seulement.
                  Déposer les dossiers acceptés avec l'outil 3, puis lancer l'outil 4.</p>
              ) : (
                <>
                  <p className="aide">{base.meme_classe} de la classe {base.classe ?? '—'}. L'agent reprend leur forme pour
                    les pièces qu'il rédige, et leurs pièces fournisseur pour un même fabricant (sauf certificats) :
                    tout reste à relire.</p>
                  <ul>
                    {base.dossiers.map((d) => (
                      <li key={`${d.produit}-${d.classe}`}>
                        {d.produit}{d.classe && ` (${d.classe})`}{d.meme_classe && ' · même classe'}
                        {d.preuve && ` · ${d.preuve === 'ce' ? 'certificat CE' : 'autorité du pays'}`}
                        <small>{d.fabricant ? `Fabricant ${d.fabricant} · ` : 'Fabricant non appris (outil 4) · '}
                          {d.pieces.length} pièce{d.pieces.length > 1 ? 's' : ''}</small>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
