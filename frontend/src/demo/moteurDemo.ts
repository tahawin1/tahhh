/* Adaptateur de démonstration : données JSON non typées, volontairement. */
// Mode démonstration du tableau de bord (VITE_API_URL=demo), pour le
// montrer sans backend, par exemple sur Vercel.
//
// Intercepte les appels vers l'adresse de démonstration et y répond à partir
// d'un instantané des données réelles du backend (instantane.json : dossiers,
// projet rédigé par Mistral, documents lus par l'agent), en appliquant les
// mêmes règles que src/api.py pour la validation et le rejet. Les actions
// restent dans la mémoire de l'onglet ; la rédaction et la lecture par
// l'agent nécessitent le vrai serveur et sont signalées comme indisponibles.
import instantaneBrut from './instantane.json'

export function installerDemo(base: string) {
  const BASE = base
  const instantane: any = structuredClone(instantaneBrut)
  const dossiers = new Map<number, any>(instantane.dossiers.map((d: any) => [d.id, d]))
  let prochainId = Math.max(0, ...dossiers.keys()) + 1
  let prochainePiece = Math.max(0, ...instantane.dossiers.flatMap((d: any) => d.documents.map((x: any) => x.id))) + 1

  // Connexion préremplie : le visiteur arrive directement sur la liste
  try {
    if (!localStorage.getItem('conformite-dm-session')) {
      localStorage.setItem('conformite-dm-session', JSON.stringify({ nom: 'Visiteur (démo)', cleApi: '' }))
    }
  } catch { /* stockage indisponible : l'écran de connexion s'affiche */ }

  const maintenant = () => new Date().toISOString()
  const reponse = (corps: unknown, status = 200) =>
    new Response(JSON.stringify(corps), { status, headers: { 'Content-Type': 'application/json' } })
  const erreur = (status: number, detail: string) => reponse({ detail }, status)

  function compteurs(docs: any[]) {
    const c: any = { total: docs.length, valides: 0, a_valider: 0, a_obtenir: 0, a_generer: 0, en_cours: 0, erreurs: 0, rejetes: 0 }
    const cle: any = { valide: 'valides', a_valider: 'a_valider', a_obtenir: 'a_obtenir', a_generer: 'a_generer',
      en_file: 'en_cours', en_generation: 'en_cours', erreur: 'erreurs', rejete: 'rejetes' }
    docs.forEach((d: any) => { c[cle[d.statut]] += 1 })
    return c
  }

  function prochainCreneau() {
    const j = new Date()
    for (let i = 0; i < 14; i++) {
      const c = new Date(j.getFullYear(), j.getMonth(), j.getDate() + i)
      if (c.getDay() === 3 || c.getDay() === 4) {
        return `${c.getFullYear()}-${String(c.getMonth() + 1).padStart(2, '0')}-${String(c.getDate()).padStart(2, '0')}`
      }
    }
  }

  function recalculer(d: any) {
    d.compteurs = compteurs(d.documents)
    d.statut = d.documents.length && d.documents.every((x: any) => x.statut === 'valide')
      ? 'pret_pour_depot_manuel'
      : d.documents.some((x: any) => ['en_file', 'en_generation'].includes(x.statut)) ? 'generation_en_cours' : 'en_preparation'
    d.prochain_creneau_depot = d.statut === 'pret_pour_depot_manuel' ? prochainCreneau() : null
    return d
  }

  const resume = (d: any) => {
    const r = { ...d }
    delete r.documents
    delete r.evenements
    delete r.prochain_creneau_depot
    return r
  }

  function journaliser(d: any, acteur: string, action: string, detail: string, document_id: number | null = null) {
    d.evenements.unshift({ horodatage: maintenant(), acteur, action, detail, document_id })
  }

  function decider(d: any, piece: any, corps: any, action: string) {
    const validateur = (corps.validateur || '').trim()
    const commentaire = (corps.commentaire || '').trim()
    if (validateur.length < 2) return erreur(422, 'validateur : au moins 2 caractères')
    if (action === 'valider') {
      if (piece.nature === 'a_rediger' && piece.statut !== 'a_valider') {
        return erreur(409, `Pièce au statut '${piece.statut}' : seul un projet rédigé (statut a_valider) peut être validé.`)
      }
      if (piece.nature === 'a_fournir') {
        if (!['a_obtenir', 'rejete'].includes(piece.statut)) return erreur(409, `Pièce au statut '${piece.statut}' : déjà validée.`)
        if (!commentaire) return erreur(422, 'Pour une pièce à fournir, indiquer en commentaire ce qui a été reçu et vérifié (référence, date…).')
      }
      piece.statut = 'valide'
    } else {
      if (!commentaire) return erreur(422, 'Le motif du rejet (commentaire) est obligatoire.')
      const autorises = piece.nature === 'a_rediger' ? ['a_valider', 'valide'] : ['a_obtenir', 'valide']
      if (!autorises.includes(piece.statut)) return erreur(409, `Pièce au statut '${piece.statut}' : rejet impossible.`)
      piece.statut = 'rejete'
    }
    piece.valide_par = validateur
    piece.valide_le = maintenant()
    piece.commentaire = commentaire || null
    journaliser(d, validateur, action === 'valider' ? 'piece_validee' : 'piece_rejetee',
      piece.nom + (commentaire ? ` — ${commentaire}` : ''), piece.id)
    return reponse(recalculer(d))
  }

  function router(methode: string, chemin: string, corps: any): Response {
    if (methode === 'GET' && chemin === '/health') {
      return reponse({ ...instantane.health, authentification: 'aucune', prochain_creneau_depot: prochainCreneau() })
    }
    if (methode === 'GET' && chemin === '/pays') return reponse(instantane.pays)
    if (chemin === '/dossiers/documents-requis') {
      const r = instantane.requis[`${corps.pays_origine}|${corps.classe}`]
      return r ? reponse({ ...r, produit: corps.produit }) : erreur(400, 'Combinaison inconnue')
    }
    if (chemin === '/dossiers') {
      if (methode === 'GET') return reponse([...dossiers.values()].sort((a, b) => b.id - a.id).map(resume))
      const requis = instantane.requis[`${corps.pays_origine}|${corps.classe}`]
      if (!requis) return erreur(400, 'Combinaison inconnue')
      const d = {
        id: prochainId++, produit: corps.produit, pays_origine: corps.pays_origine, pays_destination: 'maroc',
        classe: corps.classe, fournisseur: corps.fournisseur, cree_par: corps.cree_par, cree_le: maintenant(),
        regles_version: instantane.dossiers[0]?.regles_version ?? '—', evenements: [],
        documents: requis.documents.map((x: any) => ({
          id: prochainePiece++, code: x.id, nom: x.nom, nature: x.nature, fourni_par: x.fourni_par,
          traduction_requise: x.traduction_requise, legalisation_requise: x.legalisation_requise,
          origine_regle: x.origine_regle, statut: x.nature === 'a_rediger' ? 'a_generer' : 'a_obtenir',
          fichier_disponible: false, sources: null, erreur: null, genere_le: null,
          valide_par: null, valide_le: null, commentaire: null,
        })),
      }
      journaliser(d, corps.cree_par, 'dossier_cree', `${d.documents.length} pièces décidées par le moteur de règles (règles ${d.regles_version})`)
      dossiers.set(d.id, recalculer(d))
      return reponse(d, 201)
    }
    const m = chemin.match(/^\/dossiers\/(\d+)(?:\/documents\/(\d+))?(?:\/([\w-]+))?$/)
    if (!m) return erreur(404, 'Not Found')
    const d = dossiers.get(Number(m[1]))
    if (!d) return erreur(404, `Dossier ${m[1]} introuvable.`)
    const piece = m[2] ? d.documents.find((x: any) => x.id === Number(m[2])) : null
    if (m[2] && !piece) return erreur(404, `Pièce ${m[2]} introuvable dans le dossier ${m[1]}.`)
    const action = m[3]
    if (!action && methode === 'GET') return reponse(d)
    if (action === 'generer') {
      return erreur(503, "Démonstration : la rédaction par Mistral s'exécute sur le serveur de l'entreprise, qui n'est pas connecté à cette page.")
    }
    if (action === 'apercu') {
      const a = instantane.apercus[`${d.id}/${piece.id}`]
      return a ? reponse(a) : erreur(404, 'Aucun projet rédigé pour cette pièce.')
    }
    if ((action === 'document-recu' && methode === 'POST') || action === 'relire') {
      return erreur(503, "Démonstration : la lecture d'un document par l'agent (OCR + Mistral) s'exécute sur le serveur de l'entreprise, qui n'est pas connecté à cette page.")
    }
    if (action === 'document-recu') {
      return erreur(404, 'Démonstration : le document original reste sur le serveur ; les champs lus sont affichés ci-dessous.')
    }
    if (action === 'fichier') {
      return erreur(404, 'Démonstration : téléchargement indisponible ici. Utiliser « Lire le projet ».')
    }
    if (action === 'valider' || action === 'rejeter') return decider(d, piece, corps, action)
    return erreur(404, 'Not Found')
  }

  const fetchOriginal = window.fetch.bind(window)
  window.fetch = async function (entree: RequestInfo | URL, options: RequestInit = {}) {
    const url = typeof entree === 'string' ? entree : entree instanceof URL ? entree.href : entree.url
    if (!url.startsWith(BASE)) return fetchOriginal(entree, options)
    const chemin = new URL(url).pathname
    const methode = (options.method || 'GET').toUpperCase()
    let corps: any = {}
    try { corps = options.body ? JSON.parse(String(options.body)) : {} } catch { corps = {} }
    await new Promise((r) => setTimeout(r, 120)) // latence réseau réaliste
    return router(methode, chemin, corps)
  }
}
