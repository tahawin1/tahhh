// Icônes au trait (24 × 24), dessinées en SVG : aucune dépendance externe.
// Chaque tracé : chemin SVG, ou "c:cx,cy,r" (cercle), ou "r:x,y,l,h,rayon" (rectangle).
const TRACES: Record<string, string[]> = {
  accueil: ['M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z'],
  dossiers: ['M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'],
  plus: ['M12 5v14', 'M5 12h14'],
  valide: ['M20 6 9 17l-5-5'],
  horloge: ['c:12,12,9', 'M12 7v5l3 2'],
  calendrier: ['r:3,5,18,16,2', 'M16 3v4', 'M8 3v4', 'M3 10h18'],
  alerte: ['M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z', 'M12 9v4', 'M12 17h.01'],
  deposer: ['M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3', 'M16 8l-4-4-4 4', 'M12 4v12'],
  document: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M14 3v5h5', 'M9 13h6', 'M9 17h4'],
  ia: ['M12 3l1.8 4.9L19 9.7l-5.2 1.8L12 16.5l-1.8-5L5 9.7l5.2-1.8z', 'M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z'],
  sortir: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'M16 17l5-5-5-5', 'M21 12H9'],
  suite: ['M5 12h14', 'M13 6l6 6-6 6'],
  retour: ['M19 12H5', 'M11 18l-6-6 6-6'],
  lire: ['M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z', 'c:12,12,3'],
  telecharger: ['M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3', 'M8 11l4 4 4-4', 'M12 4v11'],
  fermer: ['M18 6 6 18', 'M6 6l12 12'],
  relancer: ['M21 4v6h-6', 'M20.5 15a8.5 8.5 0 1 1-2-8.8L21 10'],
  bouclier: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', 'M9 12l2 2 4-4'],
  monde: ['c:12,12,9', 'M3 12h18', 'M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z'],
  personne: ['c:12,8,4', 'M4 21a8 8 0 0 1 16 0'],
  journal: ['M4 5h16', 'M4 12h16', 'M4 19h10'],
  cible: ['c:12,12,9', 'c:12,12,5', 'c:12,12,1'],
}

export type NomIcone = keyof typeof TRACES

export default function Icone({ nom, taille = 20, className }: { nom: NomIcone; taille?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={taille}
      height={taille}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {TRACES[nom].map((t, i) => {
        if (t.startsWith('c:')) {
          const [cx, cy, r] = t.slice(2).split(',').map(Number)
          return <circle key={i} cx={cx} cy={cy} r={r} />
        }
        if (t.startsWith('r:')) {
          const [x, y, l, h, rx] = t.slice(2).split(',').map(Number)
          return <rect key={i} x={x} y={y} width={l} height={h} rx={rx} />
        }
        return <path key={i} d={t} />
      })}
    </svg>
  )
}
