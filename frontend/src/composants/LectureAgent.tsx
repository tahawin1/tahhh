import { useRef, useState } from 'react'
import { api, type DossierDetail, type Piece, type Verification } from '../api'
import { dateHeure } from '../libelles'

const VERDICT: Record<Verification, { libelle: string; ton: string; aide: string }> = {
  verifie: { libelle: 'Vérifié dans le document', ton: 'ok', aide: 'La citation a été retrouvée dans le document et contient la valeur.' },
  citation_introuvable: {
    libelle: 'Non vérifié', ton: 'erreur',
    aide: "La citation proposée par l'IA est introuvable dans le document : valeur possiblement inventée.",
  },
  valeur_hors_citation: {
    libelle: 'Non vérifié', ton: 'erreur', aide: "La valeur n'apparaît pas dans la citation proposée.",
  },
  absent: { libelle: 'Absent du document', ton: 'attention', aide: "L'IA n'a pas trouvé cette information dans le document." },
}

function formatDate(iso: string) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}

// Lecture par l'agent du document reçu du fournisseur. C'est une aide à la
// vérification : elle ne valide rien, la décision reste à la personne.
export default function LectureAgent({
  piece, dossierId, acteur, occupe, executer,
}: {
  piece: Piece
  dossierId: number
  acteur: string
  occupe: boolean
  executer: (libelle: string, appel: () => Promise<DossierDetail>) => Promise<void>
}) {
  const entree = useRef<HTMLInputElement>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const enCours = piece.extraction_statut === 'en_file' || piece.extraction_statut === 'en_cours'
  const modifiable = piece.statut !== 'valide'
  const e = piece.extraction

  return (
    <div className="lecture">
      <input
        ref={entree}
        id={`recu-${piece.id}`}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
        hidden
        onChange={(ev) => {
          const f = ev.target.files?.[0]
          ev.target.value = ''
          if (f) executer('deposer', () => api.deposerRecu(dossierId, piece.id, f, acteur))
        }}
      />

      {piece.nom_fichier_recu ? (
        <p className="secondaire">
          Document reçu : <button className="lien" onClick={() => api.telechargerRecu(dossierId, piece).catch((x: Error) => setErreur(x.message))}>
            {piece.nom_fichier_recu}
          </button>{' '}
          (déposé le {dateHeure(piece.recu_le)})
        </p>
      ) : (
        <p className="secondaire">Aucun document reçu pour l'instant.</p>
      )}

      {enCours && !piece.activite && (
        <p className="message encours">Lecture du document par l'agent en cours (OCR puis extraction, quelques minutes)…</p>
      )}
      {piece.extraction_statut === 'erreur' && <p className="message erreur">Lecture impossible : {piece.extraction_erreur}</p>}
      {erreur && <p className="message erreur">{erreur}</p>}

      {e && piece.extraction_statut === 'terminee' && (
        <>
          <p className="resume-lecture">
            <strong>Lu par l'agent :</strong> {e.resume.verifie} champ(s) vérifié(s) dans le document
            {e.resume.citation_introuvable + e.resume.valeur_hors_citation > 0 && (
              <>, <span className="texte-erreur">{e.resume.citation_introuvable + e.resume.valeur_hors_citation} non vérifié(s)</span></>
            )}
            {e.resume.absent > 0 && <>, {e.resume.absent} absent(s)</>}.
          </p>
          {e.source_texte === 'transcription_ia' && (
            <p className="message attention">
              Document scanné : les citations ont été contrôlées contre la transcription faite par l'IA elle-même,
              pas contre une couche texte. Vérifier les valeurs sur l'original.
            </p>
          )}
          <dl className="champs-lus">
            {e.champs.map((c) => {
              const v = VERDICT[c.verification]
              return (
                <div key={c.nom} className="champ-lu">
                  <dt>
                    <span>{c.libelle}</span>
                    <span className={`pastille ${v.ton}`} title={v.aide}>{v.libelle}</span>
                  </dt>
                  <dd>
                    {c.valeur ? (
                      <>
                        <div className="valeur">
                          {c.type === 'date' && c.valeur_normalisee ? formatDate(c.valeur_normalisee) : c.valeur}
                        </div>
                        {c.citation && <div className="citation">« {c.citation} »</div>}
                      </>
                    ) : (
                      <span className="secondaire">—</span>
                    )}
                  </dd>
                </div>
              )
            })}
          </dl>
        </>
      )}

      {modifiable && (
        <div className="actions">
          <button disabled={occupe || enCours} onClick={() => entree.current?.click()}>
            {piece.nom_fichier_recu ? 'Remplacer le document reçu' : 'Déposer le document reçu'}
          </button>
          {piece.extraction_statut === 'erreur' && (
            <button disabled={occupe} onClick={() => executer('relire', () => api.relire(dossierId, piece.id, acteur))}>
              Relancer la lecture
            </button>
          )}
        </div>
      )}
    </div>
  )
}
