import type { Compteurs } from '../api'

/** Anneau de progression : part des pièces validées par une personne. */
export function Anneau({ valides, total, taille = 64 }: { valides: number; total: number; taille?: number }) {
  const pct = total ? valides / total : 0
  const r = 26
  const circ = 2 * Math.PI * r
  return (
    <div className="anneau" style={{ width: taille, height: taille }} title={`${valides} pièce(s) validée(s) sur ${total}`}>
      <svg viewBox="0 0 64 64" width={taille} height={taille} aria-hidden="true">
        <circle cx="32" cy="32" r={r} className="anneau-fond" />
        <circle
          cx="32" cy="32" r={r} className="anneau-valeur"
          strokeDasharray={`${circ * pct} ${circ}`} transform="rotate(-90 32 32)"
        />
      </svg>
      <span className="anneau-texte">{Math.round(pct * 100)}<small>%</small></span>
    </div>
  )
}

/** Barre de progression compacte (listes). */
export default function Progression({ compteurs }: { compteurs: Compteurs }) {
  const { total, valides } = compteurs
  const pct = total ? Math.round((valides / total) * 100) : 0
  return (
    <div className="progression" title={`${valides} pièce(s) validée(s) sur ${total}`}>
      <div className="barre"><div className="rempli" style={{ width: `${pct}%` }} /></div>
      <span>{valides}/{total} validées</span>
    </div>
  )
}
