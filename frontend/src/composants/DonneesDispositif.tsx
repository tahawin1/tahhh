import { useCallback, useEffect, useState } from 'react'
import { MODE_DEMO, api, type DonneeDispositif, type DonneesDispositif as Donnees, type DossierResume, type Provenance } from '../api'
import Icone from './Icone'

const PROVENANCE: Record<Provenance, { libelle: string; ton: string }> = {
  saisie: { libelle: 'Saisi', ton: 'ok' },
  piece: { libelle: 'Lu dans un document', ton: 'ok' },
  profil: { libelle: "Profil de l'entreprise", ton: 'neutre' },
  dossier: { libelle: 'Dossier', ton: 'neutre' },
  donnee: { libelle: 'Repris', ton: 'neutre' },
  defaut: { libelle: 'Valeur habituelle', ton: 'attention' },
  regle: { libelle: 'Sans objet', ton: 'neutre' },
  manquant: { libelle: 'À compléter', ton: 'erreur' },
}

// Données du dispositif qui remplissent, case par case, la fiche signalétique
// (pièce 2) et l'annexe II (pièce 16). Chaque valeur montre d'où elle vient ;
// l'utilisateur complète ou corrige, puis relance la rédaction de ces pièces.
export default function DonneesDispositif({
  dossierId, acteur, version,
}: {
  dossierId: number
  acteur: string
  /** change quand un document a été lu : les valeurs lues sont rechargées */
  version: string
}) {
  const [donnees, setDonnees] = useState<Donnees | null>(null)
  const [saisies, setSaisies] = useState<Record<string, string>>({})
  const [ouvert, setOuvert] = useState(false)
  const [erreur, setErreur] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [occupe, setOccupe] = useState(false)
  const [autres, setAutres] = useState<DossierResume[]>([])
  const [depuis, setDepuis] = useState('')

  const charger = useCallback(
    () => api.donnees(dossierId).then((d) => { setDonnees(d); setErreur(null) }, (e: Error) => setErreur(e.message)),
    [dossierId],
  )
  useEffect(() => { charger() }, [charger, version])
  useEffect(() => {
    if (ouvert) api.dossiers().then((l) => setAutres(l.filter((d) => d.id !== dossierId)), () => setAutres([]))
  }, [ouvert, dossierId])

  async function agir(appel: () => Promise<Donnees>, ok: string) {
    setOccupe(true)
    setErreur(null)
    try {
      setDonnees(await appel())
      setSaisies({})
      setMessage(ok)
    } catch (e) {
      setErreur((e as Error).message)
    } finally {
      setOccupe(false)
    }
  }

  if (!donnees) return erreur && !MODE_DEMO ? <p className="message erreur">{erreur}</p> : null  // démo : pas de données de dispositif
  const modifiees = Object.keys(saisies).length

  return (
    <div className="panneau donnees-dispositif">
      <div className="section-titre">
        <p>
          <strong>{donnees.a_completer === 0 ? 'Toutes les cases sont remplies' : `${donnees.a_completer} case(s) à compléter`}</strong>
          <span className="secondaire"> — ces données remplissent la fiche signalétique (pièce 2) et l'annexe II (pièce 16).</span>
        </p>
        <button onClick={() => setOuvert(!ouvert)}>{ouvert ? 'Masquer' : 'Voir et compléter'}</button>
      </div>
      {erreur && <p className="message erreur" role="alert">{erreur}</p>}
      {message && !modifiees && <p className="message ok">{message}</p>}
      {ouvert && (
        <>
          {autres.length > 0 && (
            <div className="reprise">
              <label>
                Reprendre les données saisies dans un autre dossier (même fabricant, même gamme)
                <select value={depuis} onChange={(e) => setDepuis(e.target.value)}>
                  <option value="">— choisir un dossier —</option>
                  {autres.map((d) => <option key={d.id} value={d.id}>n°{d.id} — {d.produit}</option>)}
                </select>
              </label>
              <button disabled={!depuis || occupe}
                onClick={() => agir(() => api.reprendreDonnees(dossierId, acteur, Number(depuis)),
                  'Données reprises (les cases déjà saisies ici sont conservées).')}>
                Reprendre
              </button>
            </div>
          )}
          {donnees.sections.map((s) => (
            <fieldset key={s.titre} className="section-donnees">
              <legend>{s.titre}</legend>
              {s.champs.map((c) => (
                <Case key={c.id} champ={c} valeur={saisies[c.id]}
                  changer={(v) => setSaisies((x) => ({ ...x, [c.id]: v }))} />
              ))}
            </fieldset>
          ))}
          <div className="actions collant">
            <button className="principal" disabled={!modifiees || occupe}
              onClick={() => agir(() => api.enregistrerDonnees(dossierId, acteur, saisies),
                'Enregistré. Relancez la rédaction des pièces 2 et 16 pour les mettre à jour.')}>
              <Icone nom="valide" taille={16} />Enregistrer {modifiees ? `(${modifiees})` : ''}
            </button>
            {modifiees > 0 && <button onClick={() => setSaisies({})}>Annuler les modifications</button>}
          </div>
        </>
      )}
    </div>
  )
}

function Case({ champ, valeur, changer }: { champ: DonneeDispositif; valeur?: string; changer: (v: string) => void }) {
  const p = PROVENANCE[champ.provenance]
  const courante = valeur ?? champ.valeur ?? ''
  const id = `donnee-${champ.id}`
  return (
    <div className={`case-donnee ${champ.provenance === 'manquant' && valeur === undefined ? 'vide' : ''}`}>
      <label htmlFor={id}>
        {champ.libelle}
        <span className={`pastille ${champ.a_verifier ? 'attention' : p.ton}`} title={champ.detail ?? undefined}>
          {champ.a_verifier && champ.provenance !== 'defaut' ? 'À vérifier' : p.libelle}
        </span>
      </label>
      {champ.type === 'choix' && champ.options ? (
        <select id={id} value={courante} onChange={(e) => changer(e.target.value)}>
          <option value="">— à compléter —</option>
          {champ.options.map((o) => <option key={o}>{o}</option>)}
          {courante && !champ.options.includes(courante) && <option>{courante}</option>}
        </select>
      ) : champ.type === 'long' || champ.type === 'references' ? (
        <textarea id={id} rows={champ.type === 'references' ? 4 : 3} value={courante}
          placeholder={champ.type === 'references' ? 'MARQUE | NOM COMMERCIAL | RÉFÉRENCE (une ligne par produit)' : ''}
          onChange={(e) => changer(e.target.value)} />
      ) : (
        <input id={id} value={courante} onChange={(e) => changer(e.target.value)} />
      )}
      {champ.detail && champ.provenance !== 'saisie' && <small className="secondaire">{champ.detail}</small>}
    </div>
  )
}
