import type { DossierDetail, Piece } from './api'

// Les 5 étapes d'un dossier, déduites de l'état réel de ses pièces (rien n'est
// saisi à la main) — affichées en frise dans la page du dossier.
export type EtatEtape = 'fait' | 'en_cours' | 'a_venir'
export interface Etape { cle: string; titre: string; detail: string; etat: EtatEtape }

const aFournir = (d: DossierDetail) => d.documents.filter((p) => p.nature === 'a_fournir')
const aRediger = (d: DossierDetail) => d.documents.filter((p) => p.nature === 'a_rediger')
const recu = (p: Piece) => !!p.nom_fichier_recu || p.statut === 'valide' || !p.lisible_par_agent
const redige = (p: Piece) => ['a_valider', 'valide'].includes(p.statut)

export function etapes(d: DossierDetail): Etape[] {
  const f = aFournir(d)
  const r = aRediger(d)
  const nbRecus = f.filter(recu).length
  const nbRediges = r.filter(redige).length
  const nbValides = d.compteurs.valides
  const brut: Omit<Etape, 'etat'>[] = [
    { cle: 'regles', titre: 'Pièces définies', detail: `${d.compteurs.total} pièces fixées par les règles` },
    { cle: 'fournisseur', titre: 'Documents fournisseur', detail: `${nbRecus}/${f.length} reçus` },
    { cle: 'redaction', titre: "Rédaction par l'agent", detail: `${nbRediges}/${r.length} rédigées` },
    { cle: 'verification', titre: 'Vérification humaine', detail: `${nbValides}/${d.compteurs.total} validées` },
    { cle: 'depot', titre: 'Prêt pour dépôt', detail: d.statut === 'pret_pour_depot_manuel' ? 'Dossier complet' : "Dépôt manuel à l'AMMPS" },
  ]
  const faits = [true, nbRecus === f.length, nbRediges === r.length, nbValides === d.compteurs.total, d.statut === 'pret_pour_depot_manuel']
  const premierNonFait = faits.findIndex((x) => !x)
  return brut.map((e, i) => ({ ...e, etat: faits[i] ? 'fait' : i === premierNonFait ? 'en_cours' : 'a_venir' }))
}

export interface ProchaineAction { titre: string; detail: string; ton: 'accent' | 'attention' | 'ok' | 'erreur' | 'encours' }

/** La chose la plus utile à faire maintenant sur ce dossier. */
export function prochaineAction(d: DossierDetail): ProchaineAction {
  const erreurs = d.documents.filter((p) => p.statut === 'erreur' || p.extraction_statut === 'erreur')
  if (erreurs.length) {
    return { ton: 'erreur', titre: `${erreurs.length} tâche(s) de l'agent à relancer`, detail: erreurs.map((p) => p.nom).join(' · ') }
  }
  if (d.statut === 'generation_en_cours' || d.documents.some((p) => ['en_file', 'en_cours'].includes(p.extraction_statut ?? ''))) {
    return { ton: 'encours', titre: "L'agent travaille sur ce dossier", detail: 'Vous pouvez suivre son texte en direct dans les pièces concernées.' }
  }
  const aLancer = d.documents.filter((p) => p.nature === 'a_rediger' && ['a_generer', 'rejete'].includes(p.statut))
  if (aLancer.length) {
    return { ton: 'accent', titre: `Lancer la rédaction de ${aLancer.length} pièce(s) par l'agent`, detail: 'Bouton « Lancer la rédaction » ci-dessous.' }
  }
  const manquants = d.documents.filter((p) => p.nature === 'a_fournir' && p.lisible_par_agent && !p.nom_fichier_recu && p.statut !== 'valide')
  if (manquants.length) {
    return { ton: 'attention', titre: `${manquants.length} document(s) du fournisseur à déposer`, detail: manquants.map((p) => p.nom).join(' · ') }
  }
  const aRelire = d.documents.filter((p) => p.statut === 'a_valider' || (p.nature === 'a_fournir' && ['a_obtenir', 'rejete'].includes(p.statut)))
  if (aRelire.length) {
    return { ton: 'attention', titre: `${aRelire.length} pièce(s) à vérifier et valider`, detail: 'Relisez les projets et les champs lus par l\'agent, puis validez.' }
  }
  if (d.statut === 'pret_pour_depot_manuel') {
    return { ton: 'ok', titre: 'Dossier complet : prêt pour le dépôt', detail: 'Toutes les pièces sont validées par une personne.' }
  }
  return { ton: 'accent', titre: 'Dossier en préparation', detail: '' }
}
