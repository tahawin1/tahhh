// Client de l'API backend (src/api.py).
//
// L'adresse du backend vient UNIQUEMENT de la variable d'environnement
// VITE_API_URL, fixée au moment du build (fichier .env.local en local,
// variable d'environnement du projet sur Vercel). Aucune URL en dur.
//
// La clé d'API n'est jamais intégrée au build (un frontend publié est
// lisible par tous) : chaque utilisateur la saisit à la connexion, elle
// reste dans son navigateur.

// VITE_API_URL=demo : mode démonstration sans backend (données d'exemple
// réelles embarquées, voir src/demo/) — pour montrer l'interface, sur Vercel par exemple.
export const MODE_DEMO = import.meta.env.VITE_API_URL === 'demo'
export const API_URL: string | undefined = MODE_DEMO
  ? 'https://demo.invalid'
  : import.meta.env.VITE_API_URL?.replace(/\/+$/, '') || undefined

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

export type Verification = 'verifie' | 'citation_introuvable' | 'valeur_hors_citation' | 'absent'

export interface ChampLu {
  nom: string
  libelle: string
  type: 'texte' | 'date'
  valeur: string | null
  valeur_normalisee: string | null
  citation: string | null
  verification: Verification
}

export interface Extraction {
  /** 'transcription_ia' : document scanné transcrit par l'IA (pas de couche texte) */
  source_texte?: 'natif' | 'ocr' | 'transcription_ia'
  champs: ChampLu[]
  resume: Record<Verification, number>
  caracteres_lus: number
  modele: string
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
  /** place de la pièce dans le dossier déposé (règles v2) */
  numero?: number | null
  /** précision réglementaire, ex. lettre de confirmation 2023/607 */
  remarque?: string | null
  /** article ou pratique qui fonde l'exigence */
  source?: string | null
  statut: StatutPiece
  fichier_disponible: boolean
  sources: Source[] | null
  erreur: string | null
  genere_le: string | null
  valide_par: string | null
  valide_le: string | null
  commentaire: string | null
  lisible_par_agent: boolean
  nom_fichier_recu: string | null
  recu_le: string | null
  extraction_statut: 'en_file' | 'en_cours' | 'terminee' | 'erreur' | null
  extraction: Extraction | null
  extraction_erreur: string | null
  /** Texte que l'agent est en train d'écrire (tâche en cours), si l'hébergement le diffuse */
  progression?: string | null
  /** Ce que fait l'agent en ce moment, ex. « Claude lit le document » */
  activite?: string | null
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
  equipement?: boolean | null
  valeur_unitaire_usd?: number | null
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
  numero?: number | null
  remarque?: string | null
  source?: string | null
}

export interface Apercu {
  produit: string
  pays_origine: string
  documents: ApercuPiece[]
  prochain_creneau_depot: string
}

export interface ApercuProjet {
  piece: string
  genere_le: string | null
  /** 'ligne' : une ligne de tableau d'un formulaire (« libellé | valeur ») */
  paragraphes: { genre: 'titre' | 'puce' | 'texte' | 'ligne'; texte: string }[]
}

export type Provenance = 'saisie' | 'piece' | 'profil' | 'dossier' | 'donnee' | 'defaut' | 'regle' | 'manquant'

/** Une case de la fiche signalétique / de l'annexe II, avec sa provenance */
export interface DonneeDispositif {
  id: string
  libelle: string
  type: 'texte' | 'long' | 'choix' | 'references'
  options: string[] | null
  valeur: string | null
  provenance: Provenance
  detail: string | null
  a_verifier: boolean
}

export interface DonneesDispositif {
  sections: { titre: string; champs: DonneeDispositif[] }[]
  a_completer: number
}

export interface PaysCorrespondance {
  id: string
  nom: string
  statut: 'verifie' | 'partiel' | 'provisoire'
  autorite: string
  texte: string
  classes: Record<string, string[]>
  note_classes?: string
  preuve_mise_sur_le_marche: string
  certificat_pour_export: string | null
  systeme_qualite: string
  equivalence_etrangere: string
}

export interface Correspondances {
  version: number
  date_version: string
  niveaux: { id: string; libelle: string }[]
  pays: PaysCorrespondance[]
  themes: { id: string; question: string; articles?: Record<string, string> }[]
  parcours_vers_maroc: Record<string, string[]>
}

export interface Synthese {
  theme: { id: string; question: string }
  pays: Record<string, { resume: string | null; citation: string | null; verifiee: boolean; reference: string | null; sources: string[] }>
}

export interface Comparaison {
  theme: { id: string; question: string }
  pays: Record<string, (Source & { texte: string })[]>
}

export interface Affectation {
  fichier: string
  piece: number | null
  piece_nom?: string | null
  raison: string
}

export interface Sante {
  statut: string
  services: Record<string, boolean>
  authentification: 'cle_api' | 'aucune'
  prochain_creneau_depot?: string
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
  // Tunnel ngrok (offre gratuite) : sans cet en-tête, ngrok renvoie sa page
  // d'avertissement HTML au lieu de la réponse de l'API. Sans effet ailleurs.
  const h: Record<string, string> = { 'ngrok-skip-browser-warning': 'true' }
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

async function telechargerFichier(chemin: string, nom: string) {
  if (!API_URL) throw new ErreurApi(0, 'VITE_API_URL non configurée')
  const r = await fetch(`${API_URL}${chemin}`, { headers: enTetes() })
  if (!r.ok) throw new ErreurApi(r.status, messageErreur(await r.json().catch(() => null), r.status))
  const contenu = await r.blob()
  if (window.conformiteEnregistrer) return window.conformiteEnregistrer(nom, contenu)
  const url = URL.createObjectURL(contenu)
  const a = document.createElement('a')
  a.href = url
  a.download = nom
  a.click()
  URL.revokeObjectURL(url)
}

export const api = {
  sante: () => requete<Sante>('/health', { headers: enTetes() }),
  pays: () => requete<Record<string, { autorite: string; classification: string[] }>>('/pays', { headers: enTetes() }),
  apercu: (pays_origine: string, produit: string, classe: string | null, equipement = false, valeur_unitaire_usd: number | null = null) =>
    post<Apercu>('/dossiers/documents-requis', { pays_origine, produit, classe, equipement, valeur_unitaire_usd }),
  dossiers: () => requete<DossierResume[]>('/dossiers', { headers: enTetes() }),
  dossier: (id: number) => requete<DossierDetail>(`/dossiers/${id}`, { headers: enTetes() }),
  creer: (d: { pays_origine: string; produit: string; classe: string | null; fournisseur: string | null;
    equipement: boolean; valeur_unitaire_usd: number | null; cree_par: string }) =>
    post<DossierDetail>('/dossiers', d),
  genererTout: (id: number, acteur: string) => post<DossierDetail>(`/dossiers/${id}/generer`, { acteur }),
  genererPiece: (id: number, piece: number, acteur: string) =>
    post<DossierDetail>(`/dossiers/${id}/documents/${piece}/generer`, { acteur }),
  valider: (id: number, piece: number, validateur: string, commentaire: string | null) =>
    post<DossierDetail>(`/dossiers/${id}/documents/${piece}/valider`, { validateur, commentaire }),
  rejeter: (id: number, piece: number, validateur: string, commentaire: string) =>
    post<DossierDetail>(`/dossiers/${id}/documents/${piece}/rejeter`, { validateur, commentaire }),
  deposerRecu: (id: number, piece: number, fichier: File, acteur: string) => {
    const donnees = new FormData()
    donnees.append('fichier', fichier)
    donnees.append('acteur', acteur)
    // pas de Content-Type : le navigateur fixe lui-même la frontière multipart
    return requete<DossierDetail>(`/dossiers/${id}/documents/${piece}/document-recu`, {
      method: 'POST', headers: enTetes(), body: donnees,
    })
  },
  deposerGroupe: (id: number, fichiers: File[], acteur: string) => {
    const donnees = new FormData()
    for (const f of fichiers) donnees.append('fichiers', f)
    donnees.append('acteur', acteur)
    return requete<{ dossier: DossierDetail; affectations: Affectation[] }>(`/dossiers/${id}/documents-recus`, {
      method: 'POST', headers: enTetes(), body: donnees,
    })
  },
  correspondances: () => requete<Correspondances>('/correspondances', { headers: enTetes() }),
  synthese: (theme: string) => post<Synthese>(`/correspondances/synthese/${theme}`, {}),
  comparer: (theme: string) => requete<Comparaison>(`/correspondances/comparer/${theme}`, { headers: enTetes() }),
  donnees: (id: number) => requete<DonneesDispositif>(`/dossiers/${id}/donnees-dispositif`, { headers: enTetes() }),
  enregistrerDonnees: (id: number, acteur: string, valeurs: Record<string, string>) =>
    requete<DonneesDispositif>(`/dossiers/${id}/donnees-dispositif`, {
      method: 'PUT', headers: enTetes(true), body: JSON.stringify({ acteur, valeurs }),
    }),
  reprendreDonnees: (id: number, acteur: string, depuis: number) =>
    post<DonneesDispositif>(`/dossiers/${id}/donnees-dispositif/reprendre`, { acteur, depuis }),
  relire: (id: number, piece: number, acteur: string) =>
    post<DossierDetail>(`/dossiers/${id}/documents/${piece}/relire`, { acteur }),
  apercuProjet: (id: number, piece: number) =>
    requete<ApercuProjet>(`/dossiers/${id}/documents/${piece}/apercu`, { headers: enTetes() }),
  // Téléchargement via fetch (et non un simple lien) pour pouvoir envoyer la clé d'API
  telecharger: (id: number, piece: Piece) =>
    telechargerFichier(`/dossiers/${id}/documents/${piece.id}/fichier`, `dossier${id}_${piece.code}.docx`),
  telechargerRecu: (id: number, piece: Piece) =>
    telechargerFichier(`/dossiers/${id}/documents/${piece.id}/document-recu`, piece.nom_fichier_recu ?? `${piece.code}.pdf`),
}
