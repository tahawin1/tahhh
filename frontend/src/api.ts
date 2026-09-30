// Client de l'API backend (src/api.py).
//
// L'adresse du backend vient UNIQUEMENT de la variable d'environnement
// VITE_API_URL, fixée au moment du build (fichier .env.local en local,
// variable d'environnement du projet sur Vercel). Aucune URL en dur.
//
// La clé d'API n'est jamais intégrée au build (un frontend publié est
// lisible par tous) : chaque utilisateur la saisit à la connexion, elle
// reste dans son navigateur.

export const API_URL: string | undefined = import.meta.env.VITE_API_URL?.replace(/\/+$/, '') || undefined

export type Nature = 'a_rediger' | 'a_fournir'
export type StatutPiece =
  | 'a_generer' | 'en_file' | 'en_generation' | 'erreur' | 'a_valider' | 'valide' | 'rejete' | 'a_obtenir'
export type StatutDossier = 'en_preparation' | 'generation_en_cours' | 'pret_pour_depot_manuel'

export interface Source {
  texte_source: string
  pays?: string
  date_version: string
  fichier?: string
  chunk_index?: number
  score?: number
}

export interface Piece {
  id: number
  code: string
  nom: string
  nature: Nature
  fourni_par: string | null
  traduction_requise: boolean
  legalisation_requise: boolean
  origine_regle: string
  statut: StatutPiece
  fichier_disponible: boolean
  sources: Source[] | null
  erreur: string | null
  genere_le: string | null
  valide_par: string | null
  valide_le: string | null
  commentaire: string | null
}

export interface Compteurs {
  total: number
  valides: number
  a_valider: number
  a_obtenir: number
  a_generer: number
  en_cours: number
  erreurs: number
  rejetes: number
}

export interface DossierResume {
  id: number
  produit: string
  pays_origine: string
  pays_destination: string
  classe: string | null
  fournisseur: string | null
  cree_par: string
  cree_le: string
  regles_version: string
  statut: StatutDossier
  compteurs: Compteurs
}

export interface Evenement {
  horodatage: string
  acteur: string
  action: string
  detail: string | null
  document_id: number | null
}

export interface DossierDetail extends DossierResume {
  documents: Piece[]
  evenements: Evenement[]
  prochain_creneau_depot: string | null
}

export interface ApercuPiece {
  id: string
  nom: string
  nature: Nature
  fourni_par: string | null
  traduction_requise: boolean
  legalisation_requise: boolean
  origine_regle: string
}

export interface Apercu {
  produit: string
  pays_origine: string
  documents: ApercuPiece[]
  prochain_creneau_depot: string
}

export interface Sante {
  statut: string
  services: Record<string, boolean>
  authentification: 'cle_api' | 'aucune'
}

export class ErreurApi extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let cleApi = ''
export function definirCleApi(cle: string) {
  cleApi = cle
}

function enTetes(json = false): HeadersInit {
  const h: Record<string, string> = {}
  if (json) h['Content-Type'] = 'application/json'
  if (cleApi) h['X-API-Key'] = cleApi
  return h
}

function messageErreur(corps: unknown, status: number): string {
  const detail = (corps as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')} : ${d.msg}`).join(' ; ')
  }
  return `Erreur HTTP ${status}`
}

async function requete<T>(chemin: string, options: RequestInit = {}): Promise<T> {
  if (!API_URL) throw new ErreurApi(0, 'VITE_API_URL non configurée')
  let reponse: Response
  try {
    reponse = await fetch(`${API_URL}${chemin}`, options)
  } catch {
    throw new ErreurApi(0, `Backend injoignable (${API_URL}). Le serveur ou le tunnel est-il démarré ?`)
  }
  const corps = await reponse.json().catch(() => null)
  if (!reponse.ok) throw new ErreurApi(reponse.status, messageErreur(corps, reponse.status))
  return corps as T
}

const post = <T>(chemin: string, donnees: unknown) =>
  requete<T>(chemin, { method: 'POST', headers: enTetes(true), body: JSON.stringify(donnees) })

export const api = {
  sante: () => requete<Sante>('/health'),
  pays: () => requete<Record<string, { autorite: string; classification: string[] }>>('/pays', { headers: enTetes() }),
  apercu: (pays_origine: string, produit: string, classe: string | null) =>
    post<Apercu>('/dossiers/documents-requis', { pays_origine, produit, classe }),
  dossiers: () => requete<DossierResume[]>('/dossiers', { headers: enTetes() }),
  dossier: (id: number) => requete<DossierDetail>(`/dossiers/${id}`, { headers: enTetes() }),
  creer: (d: { pays_origine: string; produit: string; classe: string | null; fournisseur: string | null; cree_par: string }) =>
    post<DossierDetail>('/dossiers', d),
  genererTout: (id: number, acteur: string) => post<DossierDetail>(`/dossiers/${id}/generer`, { acteur }),
  genererPiece: (id: number, piece: number, acteur: string) =>
    post<DossierDetail>(`/dossiers/${id}/documents/${piece}/generer`, { acteur }),
  valider: (id: number, piece: number, validateur: string, commentaire: string | null) =>
    post<DossierDetail>(`/dossiers/${id}/documents/${piece}/valider`, { validateur, commentaire }),
  rejeter: (id: number, piece: number, validateur: string, commentaire: string) =>
    post<DossierDetail>(`/dossiers/${id}/documents/${piece}/rejeter`, { validateur, commentaire }),
  // Téléchargement via fetch (et non un simple lien) pour pouvoir envoyer la clé d'API
  telecharger: async (id: number, piece: Piece) => {
    if (!API_URL) throw new ErreurApi(0, 'VITE_API_URL non configurée')
    const r = await fetch(`${API_URL}/dossiers/${id}/documents/${piece.id}/fichier`, { headers: enTetes() })
    if (!r.ok) throw new ErreurApi(r.status, messageErreur(await r.json().catch(() => null), r.status))
    const url = URL.createObjectURL(await r.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = `dossier${id}_${piece.code}.docx`
    a.click()
    URL.revokeObjectURL(url)
  },
}
