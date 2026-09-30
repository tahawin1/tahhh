import type { StatutDossier, StatutPiece } from './api'

export const PAYS: Record<string, string> = {
  chine: 'Chine',
  inde: 'Inde',
  union_europeenne: 'Union européenne',
  autre: 'Autre pays',
  maroc: 'Maroc',
}

export const STATUT_PIECE: Record<StatutPiece, { libelle: string; ton: string }> = {
  a_generer: { libelle: 'À rédiger', ton: 'neutre' },
  en_file: { libelle: 'En file de rédaction', ton: 'encours' },
  en_generation: { libelle: 'Rédaction en cours…', ton: 'encours' },
  erreur: { libelle: 'Échec de rédaction', ton: 'erreur' },
  a_valider: { libelle: 'Projet à relire', ton: 'attention' },
  a_obtenir: { libelle: 'À obtenir', ton: 'neutre' },
  valide: { libelle: 'Validée', ton: 'ok' },
  rejete: { libelle: 'Rejetée', ton: 'erreur' },
}

export const STATUT_DOSSIER: Record<StatutDossier, { libelle: string; ton: string }> = {
  en_preparation: { libelle: 'En préparation', ton: 'neutre' },
  generation_en_cours: { libelle: 'Rédaction en cours', ton: 'encours' },
  pret_pour_depot_manuel: { libelle: 'Prêt pour dépôt manuel', ton: 'ok' },
}

export const ACTIONS: Record<string, string> = {
  dossier_cree: 'Dossier créé',
  generation_demandee: 'Rédaction demandée',
  generation_terminee: 'Projet rédigé',
  generation_echec: 'Échec de rédaction',
  piece_validee: 'Pièce validée',
  piece_rejetee: 'Pièce rejetée',
}

export function dateHeure(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
}

export function dateLongue(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  })
}
