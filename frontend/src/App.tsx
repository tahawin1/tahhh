import { useEffect, useState } from 'react'
import { API_URL, MODE_DEMO, api, definirCleApi, type Sante } from './api'
import Icone from './composants/Icone'
import Connexion, { type Session } from './pages/Connexion'
import Accueil from './pages/ListeDossiers'
import NouveauDossier from './pages/NouveauDossier'
import DetailDossier from './pages/DetailDossier'
import Correspondances from './pages/Correspondances'

// Navigation par ancre (#/dossiers/3) : fonctionne sur n'importe quel
// hébergement statique, sans configuration de réécriture d'URL.
type Route = { vue: 'liste' } | { vue: 'nouveau' } | { vue: 'correspondances' } | { vue: 'dossier'; id: number }

function lireRoute(): Route {
  const h = window.location.hash
  const m = h.match(/^#\/dossiers\/(\d+)/)
  if (m) return { vue: 'dossier', id: Number(m[1]) }
  if (h.startsWith('#/nouveau')) return { vue: 'nouveau' }
  if (h.startsWith('#/correspondances')) return { vue: 'correspondances' }
  return { vue: 'liste' }
}

const CLE_SESSION = 'conformite-dm-session'

function lireSession(): Session | null {
  try {
    const brut = localStorage.getItem(CLE_SESSION)
    return brut ? (JSON.parse(brut) as Session) : null
  } catch {
    return null
  }
}

export default function App() {
  const [route, setRoute] = useState<Route>(lireRoute)
  const [session, setSession] = useState<Session | null>(() => {
    const s = lireSession()
    if (s) definirCleApi(s.cleApi)
    return s
  })
  const [sante, setSante] = useState<Sante | null>(null)
  const [santeErreur, setSanteErreur] = useState<string | null>(null)

  // Hébergement qui connaît déjà l'utilisateur (édition claude.ai) : pas d'écran de connexion
  useEffect(() => {
    if (session || !window.conformiteSession) return
    window.conformiteSession.then((s) => { if (s) ouvrirSession(s) }, () => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const surChangement = () => { setRoute(lireRoute()); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', surChangement)
    return () => window.removeEventListener('hashchange', surChangement)
  }, [])

  useEffect(() => {
    if (!API_URL) return
    const verifier = () =>
      api.sante().then(
        (s) => { setSante(s); setSanteErreur(null) },
        (e: Error) => { setSante(null); setSanteErreur(e.message) },
      )
    verifier()
    const t = window.setInterval(verifier, 30000)
    return () => window.clearInterval(t)
  }, [])

  if (!API_URL) {
    return (
      <main className="ecran-seul">
        <div className="carte-seule">
          <span className="icone-rond erreur"><Icone nom="alerte" /></span>
          <h1>Configuration manquante</h1>
          <p>
            L'adresse du backend n'est pas définie. Renseigner la variable d'environnement
            <code> VITE_API_URL</code> (ex. <code>https://api.mon-entreprise.ma</code>, ou <code>demo</code>) puis relancer le build.
          </p>
        </div>
      </main>
    )
  }

  function ouvrirSession(s: Session) {
    try { localStorage.setItem(CLE_SESSION, JSON.stringify(s)) } catch { /* navigation privée */ }
    definirCleApi(s.cleApi)
    setSession(s)
  }

  function fermerSession() {
    try { localStorage.removeItem(CLE_SESSION) } catch { /* rien */ }
    definirCleApi('')
    setSession(null)
  }

  const bandeaux = (
    <>
      {MODE_DEMO && (
        <div className="bandeau-demo" role="note">
          <Icone nom="ia" taille={18} />
          <span>
            <strong>Démonstration</strong> — données réelles d'exemple (dossiers de test, projet rédigé par Mistral,
            certificats spécimens lus par l'agent). Aucun serveur n'est connecté : les validations restent dans cet onglet
            et la rédaction ou la lecture par l'agent sont désactivées.
          </span>
        </div>
      )}
      {santeErreur && (
        <div className="bandeau-erreur" role="alert">
          <Icone nom="alerte" taille={18} />
          <span>
            <strong>Serveur injoignable.</strong> Le tableau de bord ne peut pas contacter <code>{API_URL}</code>.
            Tant que le serveur de l'entreprise ou le tunnel est arrêté, aucune donnée ne peut être chargée.
          </span>
        </div>
      )}
    </>
  )

  if (!session) {
    return (
      <>
        {bandeaux}
        <Connexion sante={sante} surConnexion={ouvrirSession} />
      </>
    )
  }

  const actif = route.vue === 'dossier' ? 'liste' : route.vue

  return (
    <div className="coquille">
      <aside className="barre-laterale">
        <a className="marque" href="#/">
          <span className="logo" aria-hidden><Icone nom="bouclier" taille={22} /></span>
          <span className="marque-texte">
            <strong>Conformité DM</strong>
            <small>Dossiers d'enregistrement · Maroc</small>
          </span>
        </a>
        <nav className="navigation" aria-label="Navigation principale">
          <a href="#/" className={actif === 'liste' ? 'actif' : ''} aria-current={actif === 'liste' ? 'page' : undefined}>
            <Icone nom="accueil" /> <span>Tableau de bord</span>
          </a>
          <a href="#/nouveau" className={actif === 'nouveau' ? 'actif' : ''} aria-current={actif === 'nouveau' ? 'page' : undefined}>
            <Icone nom="plus" /> <span>Nouveau dossier</span>
          </a>
          <a href="#/correspondances" className={actif === 'correspondances' ? 'actif' : ''} aria-current={actif === 'correspondances' ? 'page' : undefined}>
            <Icone nom="monde" /> <span>Correspondances pays</span>
          </a>
        </nav>
        <div className="lateral-bas">
          <EtatServeur sante={sante} erreur={santeErreur} />
          <div className="utilisateur">
            <span className="avatar" aria-hidden>{session.nom.trim().charAt(0).toUpperCase()}</span>
            <span className="utilisateur-nom">{session.nom}</span>
            <button className="bouton-icone" onClick={fermerSession} title="Se déconnecter" aria-label="Se déconnecter">
              <Icone nom="sortir" taille={18} />
            </button>
          </div>
        </div>
      </aside>

      <div className="contenu">
        {bandeaux}
        <main className="page">
          {route.vue === 'nouveau' ? (
            <NouveauDossier session={session} />
          ) : route.vue === 'correspondances' ? (
            <Correspondances />
          ) : route.vue === 'dossier' ? (
            <DetailDossier id={route.id} session={session} />
          ) : (
            <Accueil session={session} sante={sante} />
          )}
        </main>
        <footer className="pied">
          <Icone nom="bouclier" taille={16} />
          Aucun dossier n'est déposé par ce système : le dépôt auprès de l'AMMPS reste une démarche
          manuelle, après validation humaine de chaque pièce.
        </footer>
      </div>
    </div>
  )
}

function EtatServeur({ sante, erreur }: { sante: Sante | null; erreur: string | null }) {
  let ton = 'ok'
  let texte = 'Serveur en ligne'
  let aide = ''
  if (MODE_DEMO) { ton = 'attention'; texte = 'Données de démonstration' }
  else if (erreur) { ton = 'erreur'; texte = 'Serveur hors ligne'; aide = erreur }
  else if (!sante) { ton = 'neutre'; texte = 'Connexion…' }
  else {
    const hs = Object.entries(sante.services).filter(([, ok]) => !ok).map(([n]) => n)
    if (hs.length) { ton = 'attention'; texte = `Partiel : ${hs.join(', ')} hors ligne`; aide = texte }
  }
  return (
    <div className={`etat-serveur ${ton}`} title={aide || texte}>
      <span className="point" aria-hidden /> {texte}
    </div>
  )
}
