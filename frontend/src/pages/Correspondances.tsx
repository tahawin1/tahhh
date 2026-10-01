import { useEffect, useState } from 'react'
import { MODE_DEMO, api, type Comparaison, type Correspondances as Donnees } from '../api'
import { PAYS_PUCE } from '../libelles'
import Icone from '../composants/Icone'

const LIGNES: { cle: 'autorite' | 'texte' | 'preuve_mise_sur_le_marche' | 'certificat_pour_export' | 'systeme_qualite' | 'equivalence_etrangere'; libelle: string }[] = [
  { cle: 'autorite', libelle: 'Autorité' },
  { cle: 'texte', libelle: 'Texte de référence' },
  { cle: 'preuve_mise_sur_le_marche', libelle: 'Preuve de mise sur le marché' },
  { cle: 'certificat_pour_export', libelle: "Certificat pour l'exportation (libre vente)" },
  { cle: 'systeme_qualite', libelle: 'Système qualité' },
  { cle: 'equivalence_etrangere', libelle: 'Reconnaissance des certificats étrangers' },
]

// Rapprochement des réglementations : une grille commune (niveaux de risque
// IMDRF A à D) et, par thème, les extraits des textes officiels de chaque pays.
// Indicatif : la classe marocaine et les pièces restent décidées par les règles.
export default function Correspondances() {
  const [donnees, setDonnees] = useState<Donnees | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [theme, setTheme] = useState('')
  const [comparaison, setComparaison] = useState<Comparaison | null>(null)
  const [recherche, setRecherche] = useState<string | null>(null)

  useEffect(() => { api.correspondances().then(setDonnees, (e: Error) => setErreur(e.message)) }, [])

  async function comparer(id: string) {
    setTheme(id)
    setComparaison(null)
    setRecherche(null)
    if (!id) return
    try {
      setComparaison(await api.comparer(id))
    } catch (e) {
      setRecherche((e as Error).message)
    }
  }

  if (!donnees) {
    return erreur ? <p className="message erreur" role="alert">{MODE_DEMO ? 'Non disponible en démonstration.' : erreur}</p>
      : <p className="aide">Chargement…</p>
  }

  return (
    <div className="correspondances">
      <header className="page-entete">
        <p className="surtitre">Rapprochement des réglementations</p>
        <h1>Correspondances entre pays</h1>
        <p className="hero-sous">
          Les classes de chaque pays rapprochées des quatre niveaux de risque de l'IMDRF, et le document qui prouve
          la mise sur le marché dans le pays d'origine. Indicatif : la classe marocaine et les pièces exigées restent
          décidées par les règles marocaines.
        </p>
      </header>

      <section className="panneau">
        <h2><Icone nom="cible" taille={18} /> Classes par niveau de risque</h2>
        <div className="defilement">
          <table className="grille-pays">
            <thead>
              <tr>
                <th scope="col">Niveau IMDRF</th>
                {donnees.pays.map((p) => <th key={p.id} scope="col"><EntetePays id={p.id} nom={p.nom} statut={p.statut} /></th>)}
              </tr>
            </thead>
            <tbody>
              {donnees.niveaux.map((n) => (
                <tr key={n.id}>
                  <th scope="row"><strong>{n.id}</strong> <small>{n.libelle}</small></th>
                  {donnees.pays.map((p) => <td key={p.id}>{(p.classes[n.id] ?? []).join(' / ') || '—'}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="notes-pays">
          {donnees.pays.filter((p) => p.note_classes).map((p) => <li key={p.id}><strong>{p.nom} :</strong> {p.note_classes}</li>)}
        </ul>
      </section>

      <section className="panneau">
        <h2><Icone nom="document" taille={18} /> Documents et exigences</h2>
        <div className="defilement">
          <table className="grille-pays">
            <thead>
              <tr>
                <th scope="col" />
                {donnees.pays.map((p) => <th key={p.id} scope="col"><EntetePays id={p.id} nom={p.nom} statut={p.statut} /></th>)}
              </tr>
            </thead>
            <tbody>
              {LIGNES.map((l) => (
                <tr key={l.cle}>
                  <th scope="row">{l.libelle}</th>
                  {donnees.pays.map((p) => <td key={p.id}>{p[l.cle] ?? '—'}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="aide">
          <span className="pastille encours">Partiel</span> : texte officiel indexé et confronté, les points restant à vérifier sont signalés.{' '}
          <span className="pastille attention">Provisoire</span> : texte officiel pas encore indexé ; à confronter au texte avant de s'y fier.
        </p>
      </section>

      <section className="panneau">
        <h2><Icone nom="lire" taille={18} /> Comparer les textes officiels</h2>
        <label className="choix-theme">
          Thème
          <select value={theme} onChange={(e) => comparer(e.target.value)}>
            <option value="">— choisir un thème —</option>
            {donnees.themes.map((t) => <option key={t.id} value={t.id}>{t.question}</option>)}
          </select>
        </label>
        {recherche && <p className="message erreur">{recherche}</p>}
        {theme && !comparaison && !recherche && <p className="aide">Recherche dans les textes indexés…</p>}
        {comparaison && (
          <div className="comparaison">
            {Object.entries(comparaison.pays).map(([pays, extraits]) => (
              <article key={pays} className="extraits-pays">
                <h3><EntetePays id={pays} nom={donnees.pays.find((p) => p.id === pays)?.nom ?? 'Texte pivot (IMDRF)'} /></h3>
                {extraits.length === 0 ? <p className="aide">Aucun texte indexé pour ce pays.</p> : extraits.map((e, i) => (
                  <blockquote key={i}>
                    <p>{e.texte}</p>
                    <footer>{e.texte_source} — version du {e.date_version}, extrait n°{e.chunk_index}</footer>
                  </blockquote>
                ))}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function EntetePays({ id, nom, statut }: { id: string; nom: string; statut?: string }) {
  const puce = PAYS_PUCE[id] ?? (id === 'maroc' ? { code: 'MA', teinte: 'rouge' } : { code: '··', teinte: 'gris' })
  return (
    <span className="entete-pays">
      <span className={`puce-pays ${puce.teinte}`} aria-hidden>{puce.code}</span> {nom}
      {statut === 'provisoire' && <span className="pastille attention">Provisoire</span>}
      {statut === 'partiel' && <span className="pastille encours" title="Texte indexé ; quelques points restent à vérifier">Partiel</span>}
    </span>
  )
}
