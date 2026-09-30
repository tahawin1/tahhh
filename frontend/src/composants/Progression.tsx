import type { Compteurs } from '../api'

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
