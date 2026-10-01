import { useCallback, useEffect, useState } from 'react'
import { MODE_DEMO, api, type ControlesChecklist as Donnees, type StatutPoint } from '../api'
import Icone from './Icone'

const STATUT: Record<StatutPoint, { libelle: string; ton: string; signe: string }> = {
  ok: { libelle: 'Conforme', ton: 'ok', signe: '✓' },
  ko: { libelle: 'Non conforme', ton: 'erreur', signe: '✗' },
  a_verifier: { libelle: 'À vérifier', ton: 'attention', signe: '!' },
  en_attente: { libelle: 'Document attendu', ton: 'neutre', signe: '…' },
  humain_fait: { libelle: 'Vérifié', ton: 'ok', signe: '✓' },
  humain_a_faire: { libelle: 'À vérifier par vous', ton: 'encours', signe: '☐' },
}

// Contrôles automatiques de la checklist de l'entreprise : l'agent lit chaque
// document, le code compare les documents entre eux ; une personne coche les
// points visuels. Rien n'est validé ici, rien n'est envoyé au fournisseur.
export default function ControlesChecklist({ dossierId, acteur, version }: { dossierId: number; acteur: string; version: string }) {
  const [donnees, setDonnees] = useState<Donnees | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [ouverts, setOuverts] = useState<Record<string, boolean>>({})
  const [copie, setCopie] = useState(false)

  const charger = useCallback(
    () => api.controles(dossierId).then((d) => { setDonnees(d); setErreur(null) }, (e: Error) => setErreur(e.message)),
    [dossierId],
  )
  useEffect(() => { charger() }, [charger, version])

  if (!donnees) return erreur && !MODE_DEMO ? <p className="message erreur">{erreur}</p> : null
  const r = donnees.resume

  async function cocher(element: string, fait: boolean) {
    try {
      setDonnees(await api.cocherPoint(dossierId, acteur, element, fait))
    } catch (e) {
      setErreur((e as Error).message)
    }
  }

  return (
    <div className="controles">
      <div className="compteurs-controles">
        <span className="pastille ok">✓ {r.ok + r.humain_fait} conforme(s)</span>
        <span className="pastille erreur">✗ {r.ko} non conforme(s)</span>
        <span className="pastille attention">! {r.a_verifier} à vérifier</span>
        <span className="pastille encours">☐ {r.humain_a_faire} à cocher par vous</span>
        <span className="pastille neutre">… {r.en_attente} en attente de document</span>
      </div>
      {erreur && <p className="message erreur">{erreur}</p>}

      {donnees.a_reclamer.length > 0 && (
        <div className="panneau a-reclamer">
          <h3><Icone nom="alerte" taille={16} /> Papiers à réclamer au fournisseur ({donnees.a_reclamer.length})</h3>
          <ul>
            {donnees.a_reclamer.map((d, i) => (
              <li key={i}>
                <strong>{d.piece != null && `Pièce ${d.piece} — `}{d.nom}</strong>
                {d.raisons.filter((x) => x !== 'document non reçu').length > 0
                  ? <ul>{d.raisons.filter((x) => x !== 'document non reçu').map((x, j) => <li key={j}>{x}</li>)}</ul>
                  : <span className="secondaire"> : non reçu</span>}
              </li>
            ))}
          </ul>
          {donnees.relance && (
            <details>
              <summary>Projet de relance au fournisseur (à relire, jamais envoyé par l'outil)</summary>
              <pre className="relance">{donnees.relance}</pre>
              <button onClick={() => navigator.clipboard?.writeText(donnees.relance ?? '').then(() => setCopie(true))}>
                {copie ? 'Copié' : 'Copier le texte'}
              </button>
            </details>
          )}
        </div>
      )}

      <div className="docs-controles">
        {donnees.documents.map((d) => {
          const nb = (s: StatutPoint) => d.elements.filter((e) => e.statut === s).length
          const ouvert = ouverts[d.id] ?? nb('ko') > 0
          return (
            <section key={d.id} className="doc-controle">
              <button className="doc-controle-titre" aria-expanded={ouvert} onClick={() => setOuverts((o) => ({ ...o, [d.id]: !ouvert }))}>
                <span>
                  <strong>{d.nom}</strong>
                  <small className="secondaire"> — {d.piece.numero != null ? `pièce ${d.piece.numero}` : d.piece.nom}{d.piece.nature === 'a_rediger' ? ' (rédigée par l\'outil)' : d.piece.recu ? '' : ' (non reçue)'}</small>
                </span>
                <span className="mini-compteurs-controles">
                  {nb('ko') > 0 && <span className="pastille erreur">✗ {nb('ko')}</span>}
                  {nb('a_verifier') > 0 && <span className="pastille attention">! {nb('a_verifier')}</span>}
                  {nb('humain_a_faire') > 0 && <span className="pastille encours">☐ {nb('humain_a_faire')}</span>}
                  <span className="pastille ok">✓ {nb('ok') + nb('humain_fait')}/{d.elements.length}</span>
                </span>
              </button>
              {ouvert && (
                <>
                  {(d.optionnel || d.condition) && <p className="secondaire">{d.optionnel ?? d.condition}</p>}
                  {d.elements.length === 0 && <p className="secondaire">Pièce rédigée par l'outil : contrôlée à la relecture du projet.</p>}
                  <ul className="points-controle">
                    {d.elements.map((e) => {
                      const s = STATUT[e.statut]
                      return (
                        <li key={e.id} className={`point-controle ton-${s.ton}`}>
                          {e.controle === 'humain' ? (
                            <input type="checkbox" checked={e.statut === 'humain_fait'} aria-label={e.texte}
                              onChange={(ev) => cocher(e.id, ev.target.checked)} />
                          ) : <span className={`signe ${s.ton}`} aria-label={s.libelle}>{s.signe}</span>}
                          <span className="point-texte">
                            {e.texte}
                            {e.detail && <small className="secondaire">{e.detail}</small>}
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                </>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}
