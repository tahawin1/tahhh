import { useEffect, useState } from 'react'
import { API_URL, api, definirCleApi, type Sante } from './api'
import Connexion, { type Session } from './pages/Connexion'
import ListeDossiers from './pages/ListeDossiers'
import NouveauDossier from './pages/NouveauDossier'
import DetailDossier from './pages/DetailDossier'

// Navigation par ancre (#/dossiers/3) : fonctionne sur n'importe quel
// hébergement statique, sans configuration de réécriture d'URL.
type Route = { vue: 'liste' } | { vue: 'nouveau' } | { vue: 'dossier'; id: number }

function lireRoute(): Route {
  const h = window.location.hash
  const m = h.match(/^#\/dossiers\/(\d+)/)
  if (m) return { vue: 'dossier', id: Number(m[1]) }
  if (h.startsWith('#/nouveau')) return { vue: 'nouveau' }
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
    const surChangement = () => setRoute(lireRoute())
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
      <main className="page etroite">
        <div className="carte alerte erreur">
          <h1>Configuration manquante</h1>
          <p>
            L'adresse du backend n'est pas définie. Renseigner la variable d'environnement
            <code> VITE_API_URL</code> (ex. <code>https://api.mon-entreprise.ma</code>) puis relancer le build.
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

  return (
    <>
      <header className="entete">
        <a className="marque" href="#/">
          <span className="logo" aria-hidden>DM</span>
          <span>
            <strong>Conformité dispositifs médicaux</strong>
            <small>Dossiers d'enregistrement — Maroc</small>
          </span>
        </a>
        <div className="entete-droite">
          <EtatBackend sante={sante} erreur={santeErreur} />
          {session && (
            <span className="utilisateur">
              {session.nom}
              <button className="lien" onClick={fermerSession}>Se déconnecter</button>
            </span>
          )}
        </div>
      </header>

      {santeErreur && (
        <div className="bandeau-erreur" role="alert">
          <strong>Backend injoignable.</strong> Le tableau de bord ne peut pas contacter <code>{API_URL}</code>.
          Tant que le serveur de l'entreprise ou le tunnel est arrêté, aucune donnée ne peut être chargée.
        </div>
      )}

      <main className="page">
        {!session ? (
          <Connexion sante={sante} surConnexion={ouvrirSession} />
        ) : route.vue === 'nouveau' ? (
          <NouveauDossier session={session} />
        ) : route.vue === 'dossier' ? (
          <DetailDossier id={route.id} session={session} />
        ) : (
          <ListeDossiers />
        )}
      </main>

      <footer className="pied">
        Aucun dossier n'est déposé par ce système : le dépôt auprès de la DMP reste une démarche
        manuelle, après validation humaine de chaque pièce.
      </footer>
    </>
  )
}

function EtatBackend({ sante, erreur }: { sante: Sante | null; erreur: string | null }) {
  if (erreur) return <span className="pastille erreur" title={erreur}>Backend hors ligne</span>
  if (!sante) return <span className="pastille neutre">Connexion…</span>
  const hs = Object.entries(sante.services).filter(([, ok]) => !ok).map(([n]) => n)
  if (hs.length) return <span className="pastille attention" title={`Indisponible : ${hs.join(', ')}`}>Services partiels : {hs.join(', ')} hors ligne</span>
  return <span className="pastille ok">Backend en ligne</span>
}
