import { useEffect, useState } from 'react'
import { api, type DossierResume } from '../api'
import { PAYS, STATUT_DOSSIER, dateHeure } from '../libelles'
import Progression from '../composants/Progression'

export default function ListeDossiers() {
  const [dossiers, setDossiers] = useState<DossierResume[] | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)

  useEffect(() => {
    let actif = true
    const charger = () =>
      api.dossiers().then(
        (d) => { if (actif) { setDossiers(d); setErreur(null) } },
        (e: Error) => { if (actif) setErreur(e.message) },
      )
    charger()
    const t = window.setInterval(charger, 15000)
    return () => { actif = false; window.clearInterval(t) }
  }, [])

  return (
    <>
      <div className="titre-page">
        <h1>Dossiers</h1>
        <a className="bouton principal" href="#/nouveau">Nouveau dossier</a>
      </div>

      {erreur && <p className="message erreur" role="alert">{erreur}</p>}
      {!dossiers && !erreur && <p className="aide">Chargement…</p>}

      {dossiers && dossiers.length === 0 && (
        <div className="carte vide">
          <p>Aucun dossier pour l'instant.</p>
          <a className="bouton principal" href="#/nouveau">Créer le premier dossier</a>
        </div>
      )}

      {dossiers && dossiers.length > 0 && (
        <div className="tableau-conteneur">
          <table className="tableau">
            <thead>
              <tr>
                <th>N°</th>
                <th>Dispositif</th>
                <th>Origine</th>
                <th>Classe</th>
                <th>Avancement</th>
                <th>Statut</th>
                <th>Créé</th>
              </tr>
            </thead>
            <tbody>
              {dossiers.map((d) => (
                <tr key={d.id} onClick={() => { window.location.hash = `#/dossiers/${d.id}` }} className="cliquable">
                  <td className="num">{d.id}</td>
                  <td>
                    <a href={`#/dossiers/${d.id}`}>{d.produit}</a>
                    {d.fournisseur && <div className="secondaire">{d.fournisseur}</div>}
                  </td>
                  <td>{PAYS[d.pays_origine] ?? d.pays_origine}</td>
                  <td>{d.classe ?? '—'}</td>
                  <td><Progression compteurs={d.compteurs} /></td>
                  <td><span className={`pastille ${STATUT_DOSSIER[d.statut].ton}`}>{STATUT_DOSSIER[d.statut].libelle}</span></td>
                  <td className="secondaire">{dateHeure(d.cree_le)}<div>{d.cree_par}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
