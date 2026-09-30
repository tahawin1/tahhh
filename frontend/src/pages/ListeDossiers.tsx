import { useEffect, useState } from 'react'
import { api, type DossierResume, type Sante } from '../api'
import { PAYS, PAYS_PUCE, STATUT_DOSSIER, dateCourte, dateHeure, joursAvant, prenom } from '../libelles'
import Icone, { type NomIcone } from '../composants/Icone'
import { Anneau } from '../composants/Progression'
import type { Session } from './Connexion'

interface Tache { icone: NomIcone; ton: string; texte: string; dossier: DossierResume }

// Ce qui attend une action humaine, dossier par dossier, du plus urgent au moins urgent
function tachesDe(dossiers: DossierResume[]): Tache[] {
  const t: Tache[] = []
  for (const d of dossiers) {
    const c = d.compteurs
    if (c.erreurs) t.push({ icone: 'alerte', ton: 'erreur', texte: `${c.erreurs} tâche(s) de l'agent à relancer`, dossier: d })
    if (c.a_valider) t.push({ icone: 'lire', ton: 'attention', texte: `${c.a_valider} projet(s) rédigé(s) à relire`, dossier: d })
    if (c.a_generer) t.push({ icone: 'ia', ton: 'accent', texte: `${c.a_generer} pièce(s) à faire rédiger par l'agent`, dossier: d })
    if (c.a_obtenir) t.push({ icone: 'deposer', ton: 'neutre', texte: `${c.a_obtenir} pièce(s) du fournisseur à recevoir et vérifier`, dossier: d })
  }
  const ordre = ['erreur', 'attention', 'accent', 'neutre']
  return t.sort((a, b) => ordre.indexOf(a.ton) - ordre.indexOf(b.ton))
}

function salutation() {
  const h = new Date().getHours()
  return h < 18 ? 'Bonjour' : 'Bonsoir'
}

export default function Accueil({ session, sante }: { session: Session; sante: Sante | null }) {
  const [dossiers, setDossiers] = useState<DossierResume[] | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const [jour] = useState(() => ({
    date: new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' }),
    salut: salutation(),
  }))

  useEffect(() => {
    let actif = true
    const charger = () =>
      api.dossiers().then(
        (d) => { if (actif) { setDossiers(d); setErreur(null) } },
        (e: Error) => { if (actif) setErreur(e.message) },
      )
    charger()
    const t = window.setInterval(charger, 15000)
    return () => { actif = false; window.clearInterval(t) }
  }, [])

  const liste = dossiers ?? []
  const enCours = liste.filter((d) => d.statut !== 'pret_pour_depot_manuel')
  const prets = liste.filter((d) => d.statut === 'pret_pour_depot_manuel')
  const aRelire = liste.reduce((n, d) => n + d.compteurs.a_valider, 0)
  const aObtenir = liste.reduce((n, d) => n + d.compteurs.a_obtenir, 0)
  const taches = tachesDe(liste)
  const creneau = sante?.prochain_creneau_depot
  const jours = creneau ? joursAvant(creneau) : null

  return (
    <div className="accueil">
      <section className="hero">
        <div className="hero-texte">
          <p className="surtitre">{jour.date}</p>
          <h1>{jour.salut} {prenom(session.nom)}</h1>
          <p className="hero-sous">
            {dossiers === null
              ? 'Chargement de vos dossiers…'
              : taches.length
                ? `${taches.length} action(s) vous attendent. L'agent prépare le reste.`
                : liste.length
                  ? 'Tout est à jour. Beau travail.'
                  : 'Créez votre premier dossier : l\'agent s\'occupe du reste.'}
          </p>
        </div>
        <a className="bouton principal grand" href="#/nouveau"><Icone nom="plus" /> Nouveau dossier</a>
      </section>

      {erreur && <p className="message erreur" role="alert">{erreur}</p>}

      <section className="indicateurs" aria-label="Indicateurs">
        <Indicateur icone="dossiers" valeur={enCours.length} libelle="Dossiers en cours" ton="accent" />
        <Indicateur icone="lire" valeur={aRelire} libelle="Projets à relire" ton="attention" />
        <Indicateur icone="deposer" valeur={aObtenir} libelle="Pièces fournisseur en attente" ton="neutre" />
        <Indicateur icone="valide" valeur={prets.length} libelle="Prêts pour dépôt" ton="ok" />
      </section>

      <div className="accueil-grille">
        <section className="panneau">
          <div className="panneau-titre">
            <h2><Icone nom="cible" /> À faire maintenant</h2>
          </div>
          {dossiers === null ? (
            <p className="aide">Chargement…</p>
          ) : taches.length === 0 ? (
            <div className="vide-doux">
              <span className="icone-rond ok"><Icone nom="valide" /></span>
              <p>Aucune action en attente.</p>
            </div>
          ) : (
            <ul className="taches">
              {taches.slice(0, 7).map((t, i) => (
                <li key={i}>
                  <a href={`#/dossiers/${t.dossier.id}`} className="tache">
                    <span className={`icone-rond ${t.ton}`}><Icone nom={t.icone} taille={18} /></span>
                    <span className="tache-texte">
                      <strong>{t.texte}</strong>
                      <small>Dossier n°{t.dossier.id} · {t.dossier.produit}</small>
                    </span>
                    <Icone nom="suite" taille={18} className="tache-fleche" />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panneau creneau">
          <h2><Icone nom="calendrier" /> Prochain dépôt à la DMP</h2>
          {creneau ? (
            <>
              <p className="creneau-jour">{dateCourte(creneau)}</p>
              <p className="creneau-delai">{jours === 0 ? "C'est aujourd'hui" : jours === 1 ? 'Demain' : `Dans ${jours} jours`}</p>
              <p className="aide">Dépôt physique le mercredi ou le jeudi uniquement.
                {prets.length > 0 && ` ${prets.length} dossier(s) prêt(s) à déposer.`}</p>
            </>
          ) : (
            <p className="aide">Mercredi ou jeudi (règle DMP).</p>
          )}
        </section>
      </div>

      <section>
        <div className="section-titre">
          <h2>Vos dossiers</h2>
          <span className="compte">{liste.length}</span>
        </div>
        {dossiers !== null && liste.length === 0 && (
          <div className="carte-vide">
            <span className="icone-rond accent grand"><Icone nom="dossiers" taille={26} /></span>
            <h3>Aucun dossier pour l'instant</h3>
            <p>Indiquez le produit, le pays d'origine et la classe : les pièces exigées par la DMP s'affichent aussitôt.</p>
            <a className="bouton principal" href="#/nouveau"><Icone nom="plus" /> Créer le premier dossier</a>
          </div>
        )}
        <div className="cartes-dossiers">
          {liste.map((d) => <CarteDossier key={d.id} d={d} />)}
        </div>
      </section>
    </div>
  )
}

function Indicateur({ icone, valeur, libelle, ton }: { icone: NomIcone; valeur: number; libelle: string; ton: string }) {
  return (
    <div className={`indicateur ${ton}`}>
      <span className="icone-rond"><Icone nom={icone} /></span>
      <span className="indicateur-valeur">{valeur}</span>
      <span className="indicateur-libelle">{libelle}</span>
    </div>
  )
}

function CarteDossier({ d }: { d: DossierResume }) {
  const st = STATUT_DOSSIER[d.statut]
  const puce = PAYS_PUCE[d.pays_origine] ?? PAYS_PUCE.autre
  const c = d.compteurs
  return (
    <a className="carte-dossier" href={`#/dossiers/${d.id}`}>
      <div className="carte-dossier-haut">
        <span className={`puce-pays ${puce.teinte}`} title={PAYS[d.pays_origine]}>{puce.code}</span>
        <span className={`pastille ${st.ton}`}>{st.libelle}</span>
      </div>
      <h3>{d.produit}</h3>
      <p className="secondaire">{d.fournisseur ?? 'Fournisseur non renseigné'}</p>
      <div className="carte-dossier-bas">
        <Anneau valides={c.valides} total={c.total} taille={56} />
        <ul className="mini-compteurs">
          <li><span className="point ok" />{c.valides} validée(s)</li>
          <li><span className="point attention" />{c.a_valider} à relire</li>
          <li><span className="point neutre" />{c.a_obtenir} à recevoir</li>
        </ul>
      </div>
      <p className="carte-dossier-pied">
        <span>N°{d.id} · {PAYS[d.pays_origine] ?? d.pays_origine} · Classe {d.classe ?? '—'}</span>
        <span>{dateHeure(d.cree_le)}</span>
      </p>
    </a>
  )
}
