// Édition claude.ai : le tableau de bord (frontend/, inchangé) fonctionne
// sans serveur. Ce moteur répond aux appels de l'API (mêmes routes et mêmes
// règles que src/api.py) avec les capacités de la page claude.ai :
//   db        dossiers, pièces et journal d'audit, partagés entre utilisateurs
//   assets    documents reçus des fournisseurs
//   sample    l'agent : Claude rédige les pièces et lit les documents reçus,
//             en direct (son texte est diffusé dans la carte de la pièce)
//   user      identité de la personne connectée (journal, validations)
//   downloads enregistrement des projets .docx et des documents reçus
//
// Ce qui ne change pas : la liste des pièces vient du moteur de règles
// Python (claude_ai/regles.json, exporté depuis les YAML) ; l'IA ne décide
// jamais des pièces requises ; les pièces « à fournir » ne sont jamais
// rédigées ; chaque valeur lue est confrontée au texte du document
// (controle.js) ; seul un humain nommé valide ; aucun dépôt automatique.
;(function () {
  const BASE = 'https://moteur.claude-ai.invalid'
  const REGLES = JSON.parse(document.getElementById('regles').textContent)
  const C = window.ControleExtraction
  const ONGLET = Math.random().toString(36).slice(2)
  const DELAI_ABANDON_MS = 3 * 60 * 1000 // tâche sans signe de vie : page fermée pendant le travail
  const TAILLE_MAX = 20 * 1024 * 1024
  const TYPES = { pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg' }

  // ------------------------------------------------------------ capacités
  const cap = {}
  const pret = Promise.all(['db', 'assets', 'sample', 'user', 'downloads'].map((nom) =>
    (window.claude?.use ? window.claude.use(nom) : Promise.resolve(null))
      .catch(() => null).then((v) => { cap[nom] = v }),
  ))

  window.conformiteSession = pret.then(async () => {
    const moi = cap.user ? await cap.user.me() : null
    return moi && moi.name ? { nom: moi.name, cleApi: '' } : null
  })

  window.conformiteEnregistrer = async (nom, contenu) => {
    await pret
    if (!cap.downloads) throw new Error("L'enregistrement de fichiers n'est pas disponible dans cette vue.")
    try {
      await cap.downloads.save({ filename: nom, data: contenu })
    } catch (e) {
      if (e && e.code === 'declined') return
      throw new Error(e?.code === 'rejected_extension' ? 'Format de fichier refusé.' : "Enregistrement impossible.")
    }
  }

  // ------------------------------------------------------------ utilitaires
  class ErreurHttp extends Error {
    constructor(status, detail) { super(detail); this.status = status }
  }
  const echec = (status, detail) => { throw new ErreurHttp(status, detail) }
  const maintenant = () => new Date().toISOString()
  const json = (corps, status = 200) =>
    new Response(JSON.stringify(corps), { status, headers: { 'Content-Type': 'application/json' } })

  function exigerDb() {
    if (!cap.db) echec(503, "La base de données du tableau de bord n'est pas disponible : ouvrir la page dans claude.ai, connecté.")
    return cap.db
  }

  async function ecrire(ref, donnees, mode = 'update') {
    try {
      await (mode === 'set' ? ref.set(donnees) : ref.update(donnees))
    } catch (e) {
      if (e?.code === 'invalid_argument') echec(403, 'Accès en lecture seule : vous ne pouvez pas modifier ce tableau de bord.')
      if (e?.code === 'quota_exceeded') echec(507, "Capacité de stockage du tableau de bord atteinte : supprimer d'anciens dossiers.")
      echec(503, 'Base de données momentanément indisponible, réessayer.')
    }
  }

  const refDossier = (id) => exigerDb().doc(`dossiers/${id}`)
  const refPieces = (id) => exigerDb().collection(`dossiers/${id}/pieces`)
  const refPiece = (id, pid) => exigerDb().doc(`dossiers/${id}/pieces/${pid}`)
  const refJournal = (id) => exigerDb().collection(`dossiers/${id}/journal`)

  async function journaliser(dossierId, acteur, action, detail = null, documentId = null) {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    await ecrire(refJournal(dossierId).doc(id), { horodatage: maintenant(), acteur, action, detail, document_id: documentId }, 'set')
  }

  function compteurs(pieces) {
    const c = { total: pieces.length, valides: 0, a_valider: 0, a_obtenir: 0, a_generer: 0, en_cours: 0, erreurs: 0, rejetes: 0 }
    const cle = { valide: 'valides', a_valider: 'a_valider', a_obtenir: 'a_obtenir', a_generer: 'a_generer',
      en_file: 'en_cours', en_generation: 'en_cours', erreur: 'erreurs', rejete: 'rejetes' }
    pieces.forEach((p) => { c[cle[p.statut]] += 1 })
    return c
  }

  function statutDossier(pieces) {
    if (pieces.length && pieces.every((p) => p.statut === 'valide')) return 'pret_pour_depot_manuel'
    if (pieces.some((p) => ['en_file', 'en_generation'].includes(p.statut))) return 'generation_en_cours'
    return 'en_preparation'
  }

  function prochainCreneau() {
    const jours = { dimanche: 0, lundi: 1, mardi: 2, mercredi: 3, jeudi: 4, vendredi: 5, samedi: 6 }
    const autorises = REGLES.jours_depot.map((j) => jours[j])
    const d = new Date()
    for (let i = 0; i < 14; i++) {
      const c = new Date(d.getFullYear(), d.getMonth(), d.getDate() + i)
      if (autorises.includes(c.getDay())) {
        return `${c.getFullYear()}-${String(c.getMonth() + 1).padStart(2, '0')}-${String(c.getDate()).padStart(2, '0')}`
      }
    }
    return null
  }

  // Une tâche « en cours » dont l'onglet a été fermé ne doit pas le rester à vie
  function abandonnee(p) {
    const enCours = ['en_file', 'en_generation'].includes(p.statut) || ['en_file', 'en_cours'].includes(p.extraction_statut)
    return enCours && !taches.has(cleTache(p.dossier_id, p.id)) &&
      (!p.tache_signe_de_vie || Date.now() - Date.parse(p.tache_signe_de_vie) > DELAI_ABANDON_MS)
  }

  async function lirePieces(dossierId) {
    const snap = await refPieces(dossierId).orderBy('ordre').get()
    const pieces = snap.docs.map((d) => ({ ...d.data() }))
    for (const p of pieces) {
      if (!abandonnee(p)) continue
      const correctif = { activite: null, progression: null }
      if (['en_file', 'en_generation'].includes(p.statut)) {
        Object.assign(correctif, { statut: 'erreur', erreur: 'Rédaction interrompue (page fermée pendant le travail de l\'agent) — relancer.' })
      } else {
        Object.assign(correctif, { extraction_statut: 'erreur', extraction_erreur: 'Lecture interrompue (page fermée pendant le travail de l\'agent) — relancer.' })
      }
      Object.assign(p, correctif)
      await refPiece(dossierId, p.id).update(correctif).catch(() => {})
    }
    return pieces
  }

  const PUBLICS = ['id', 'code', 'nom', 'nature', 'fourni_par', 'traduction_requise', 'legalisation_requise', 'origine_regle',
    'statut', 'sources', 'erreur', 'genere_le', 'valide_par', 'valide_le', 'commentaire', 'nom_fichier_recu', 'recu_le',
    'extraction_statut', 'extraction', 'extraction_erreur', 'activite', 'progression']

  function piecePublique(p) {
    const o = {}
    PUBLICS.forEach((k) => { o[k] = p[k] ?? null })
    o.fichier_disponible = !!p.projet_texte
    o.lisible_par_agent = p.nature === 'a_fournir' && (p.champs_a_extraire || []).length > 0
    return o
  }

  function resumeDossier(d, pieces) {
    return {
      id: d.id, produit: d.produit, pays_origine: d.pays_origine, pays_destination: 'maroc', classe: d.classe,
      fournisseur: d.fournisseur, cree_par: d.cree_par, cree_le: d.cree_le, regles_version: d.regles_version,
      statut: statutDossier(pieces), compteurs: compteurs(pieces),
    }
  }

  async function detail(dossierId) {
    const snap = await refDossier(dossierId).get()
    if (!snap.exists) echec(404, `Dossier ${dossierId} introuvable.`)
    const pieces = await lirePieces(dossierId)
    const journal = await refJournal(dossierId).orderBy('horodatage', 'desc').limit(300).get()
    const r = resumeDossier(snap.data(), pieces)
    return {
      ...r,
      documents: pieces.map(piecePublique),
      evenements: journal.docs.map((e) => e.data()),
      prochain_creneau_depot: r.statut === 'pret_pour_depot_manuel' ? prochainCreneau() : null,
    }
  }

  async function majResume(dossierId) {
    const pieces = await lirePieces(dossierId)
    await refDossier(dossierId).update({ statut: statutDossier(pieces), compteurs: compteurs(pieces) }).catch(() => {})
  }

  async function chargerPiece(dossierId, pieceId) {
    const snap = await refPiece(dossierId, pieceId).get()
    if (!snap.exists) echec(404, `Pièce ${pieceId} introuvable dans le dossier ${dossierId}.`)
    return { ...snap.data() }
  }

  // ------------------------------------------------------------ l'agent (Claude)
  const taches = new Map() // tâches lancées par CET onglet
  const cleTache = (d, p) => `${d}/${p}`
  let fileTaches = Promise.resolve() // une tâche à la fois, comme le worker du serveur

  function planifier(dossierId, pieceId, fn) {
    const cle = cleTache(dossierId, pieceId)
    taches.set(cle, true)
    fileTaches = fileTaches.then(() => fn().catch(() => {})).finally(() => taches.delete(cle))
  }

  // Diffuse le texte de l'agent dans la pièce, au plus une écriture toutes les 3 s
  function diffuseur(dossierId, pieceId) {
    let dernier = 0
    let enAttente = null
    let ecriture = Promise.resolve()
    const pousser = (texte) => {
      ecriture = ecriture.then(() => refPiece(dossierId, pieceId)
        .update({ progression: texte.slice(-4000), tache_signe_de_vie: maintenant() }).catch(() => {}))
    }
    return {
      texte(t) {
        enAttente = t
        if (Date.now() - dernier > 3000) { dernier = Date.now(); pousser(enAttente); enAttente = null }
      },
      async fin() { if (enAttente !== null) pousser(enAttente); await ecriture },
    }
  }

  const MESSAGES_SAMPLE = {
    not_granted: "L'agent n'est pas autorisé : accepter l'utilisation de Claude par cette page, puis relancer.",
    sampling_disabled: "Claude n'est pas disponible pour ce compte.",
    rate_limited: "Limite d'utilisation de Claude atteinte : réessayer plus tard.",
    session_expired: 'Session expirée : se reconnecter à claude.ai, puis relancer.',
    refused: "Claude a refusé de traiter cette demande.",
    prompt_too_large: 'Document trop long pour être lu en une fois.',
    images_unavailable: 'Cette vue ne permet pas à Claude de lire des images (document scanné).',
    image_rejected: 'Image du document refusée (format ou taille).',
    invalid_json: "Réponse de l'agent illisible : relancer.",
  }
  const messageSample = (e) => MESSAGES_SAMPLE[e?.code] || "L'agent n'a pas pu terminer (service momentanément indisponible) : relancer."

  function exigerAgent() {
    if (!cap.sample) echec(503, "L'agent (Claude) n'est pas disponible dans cette vue : ouvrir la page dans claude.ai, connecté.")
  }

  async function rediger(dossierId, pieceId) {
    const ref = refPiece(dossierId, pieceId)
    const [dossier, piece, pieces] = [(await refDossier(dossierId).get()).data(), await chargerPiece(dossierId, pieceId), await lirePieces(dossierId)]
    if (piece.statut !== 'en_file') return
    await ref.update({ statut: 'en_generation', erreur: null, activite: 'Claude rédige le projet…', progression: '', tache_signe_de_vie: maintenant() })
    const extraits = REGLES.extraits[piece.code] || []
    const contexte = extraits.map((r, i) =>
      `<<< EXTRAIT ${i + 1} — ${r.texte_source} (version du ${r.date_version})\n${r.texte}\n>>>`).join('\n\n') ||
      '(aucun extrait trouvé — le signaler à la validation humaine)'
    const listePieces = pieces.map((p, i) => `  ${i + 1}. ${p.nom}`).join('\n')
    const prompt = `Tu es un assistant spécialisé en constitution de dossiers réglementaires pour dispositifs médicaux au Maroc.

DOCUMENT À RÉDIGER : ${piece.nom}
Ce que ce document doit contenir : ${piece.consigne_redaction || piece.nom}

Informations connues sur le dossier (à reprendre telles quelles) :
- Dispositif médical : ${dossier.produit}
- Classe du dispositif (classification marocaine) : ${dossier.classe || '[À COMPLÉTER]'}
- Fabricant / fournisseur : ${dossier.fournisseur || '[À COMPLÉTER]'}
- Pays d'origine du fournisseur : ${dossier.pays_origine}
- Pays de destination du dossier : maroc
Pièces composant le dossier (liste fixée par le moteur de règles — ne rien ajouter ni retirer) :
${listePieces}

Extraits de textes réglementaires officiels, fournis UNIQUEMENT comme référence (pour les exigences et le vocabulaire) :
${contexte}

Consignes strictes :
- Rédige le document demandé lui-même, prêt à être complété et signé. Ne recopie PAS les extraits, ne reproduis pas d'en-têtes du Bulletin officiel, ne cite pas les extraits dans le document.
- N'invente aucune information factuelle (nom, adresse, numéro, date, référence) : écris [À COMPLÉTER] à la place.
- N'aborde que ce document, sans parler d'autres procédures (publicité, inspection, sanctions…).
- Si le document énumère les pièces du dossier, reprends EXACTEMENT la liste fixée ci-dessus, sans en ajouter ni en retirer.
- Rédige en français, dans le registre administratif marocain (formule d'appel « Monsieur le Ministre, », formule de politesse administrative, aucune formule familière), sans commentaire avant ou après le document.
- Texte brut uniquement : pas de Markdown (ni #, ni **, ni tableaux).`
    const flux = diffuseur(dossierId, pieceId)
    try {
      const { text } = await cap.sample(prompt, { cache: false, onText: ({ text: t }) => flux.texte(t) })
      await flux.fin()
      await ref.update({
        statut: 'a_valider', projet_texte: text, genere_le: maintenant(), activite: null, progression: null,
        sources: extraits.map(({ texte, ...meta }) => meta), valide_par: null, valide_le: null, commentaire: null,
      })
      await journaliser(dossierId, 'agent (Claude)', 'generation_terminee', piece.nom, pieceId)
    } catch (e) {
      await flux.fin()
      await ref.update({ statut: 'erreur', erreur: messageSample(e), activite: null, progression: null }).catch(() => {})
      await journaliser(dossierId, 'agent (Claude)', 'generation_echec', `${piece.nom} — ${messageSample(e)}`, pieceId).catch(() => {})
    }
    await majResume(dossierId)
  }

  // Texte d'un PDF : couche texte native page par page ; les pages scannées
  // (quasi sans texte) sont rendues en images pour que Claude les lise.
  async function lirePdf(octets) {
    const pdfjs = window.pdfjsLib
    const doc = await pdfjs.getDocument({ data: octets }).promise
    const textes = []
    const images = []
    for (let n = 1; n <= Math.min(doc.numPages, 10); n++) {
      const page = await doc.getPage(n)
      const t = (await page.getTextContent()).items.map((i) => i.str + (i.hasEOL ? '\n' : ' ')).join('')
      if (t.trim().length >= 20) { textes.push(t); continue }
      const vue = page.getViewport({ scale: 1.6 })
      const toile = document.createElement('canvas')
      toile.width = vue.width; toile.height = vue.height
      await page.render({ canvasContext: toile.getContext('2d'), viewport: vue }).promise
      images.push(await new Promise((ok) => toile.toBlob(ok, 'image/png')))
    }
    return { texte: textes.join('\n').trim(), images }
  }

  const fichiersEnMemoire = new Map() // fichier déposé dans cet onglet : pas besoin de le re-télécharger

  async function lireDocument(dossierId, pieceId) {
    const ref = refPiece(dossierId, pieceId)
    const piece = await chargerPiece(dossierId, pieceId)
    if (piece.extraction_statut !== 'en_file') return
    await ref.update({ extraction_statut: 'en_cours', extraction_erreur: null, activite: 'Claude lit le document reçu…', progression: '', tache_signe_de_vie: maintenant() })
    const flux = diffuseur(dossierId, pieceId)
    try {
      let fichier = fichiersEnMemoire.get(piece.fichier_recu_asset)
      if (!fichier) {
        const r = await fetch(`/_blob/${piece.fichier_recu_asset}`)
        if (!r.ok) throw { code: 'fichier', message: 'Document reçu introuvable dans le stockage.' }
        fichier = await r.blob()
      }
      const estPdf = /\.pdf$/i.test(piece.nom_fichier_recu || '')
      let { texte, images } = estPdf ? await lirePdf(new Uint8Array(await fichier.arrayBuffer())) : { texte: '', images: [fichier] }
      const limites = images.length ? await cap.sample.limits().catch(() => null) : null
      if (images.length && !limites?.images) throw { code: 'images_unavailable' }
      if (images.length > (limites?.images?.maxCount ?? 0)) images = images.slice(0, limites.images.maxCount)

      const champs = piece.champs_a_extraire || []
      const liste = champs.map((c) => `- ${c.nom} : ${c.description}`).join('\n')
      const scan = images.length > 0
      const prompt = `Tu lis un document reçu d'un fournisseur de dispositifs médicaux. Il est censé être : ${piece.nom}.
${texte ? `\nTEXTE DU DOCUMENT (extrait du PDF) :\n<<<\n${texte.slice(0, 12000)}\n>>>\n` : ''}${scan ? `\nLes images jointes sont des pages scannées du document${texte ? ' (pages sans texte extractible)' : ''}.\n` : ''}
Pour chaque champ ci-dessous, retrouve l'information DANS CE DOCUMENT :
${liste}

Règles strictes :
- "valeur" : l'information exactement telle qu'elle est écrite dans le document (même langue, même format de date).
- "citation" : le passage du document, recopié mot pour mot (au plus 200 caractères), qui contient cette valeur.
- Si l'information n'est pas dans le document : "valeur": null et "citation": null. Ne devine jamais, ne complète jamais.
${scan ? '- "transcription" : la transcription intégrale et fidèle du texte des pages scannées, ligne par ligne.\n' : ''}
Réponds uniquement avec un objet JSON de la forme :
{${scan ? '"transcription": "…", ' : ''}"champs": {${champs.map((c) => `"${c.nom}": {"valeur": …, "citation": …}`).join(', ')}}}`
      const reponse = await cap.sample.json(prompt, {
        cache: false, ...(scan ? { images } : {}), onText: ({ text }) => flux.texte(text),
      })
      await flux.fin()
      const texteControle = [texte, scan ? String(reponse?.transcription || '') : ''].filter(Boolean).join('\n')
      if (texteControle.trim().length < 20) throw { code: 'illisible', message: 'Aucun texte lisible dans le document.' }
      const resultats = C.controler(reponse?.champs || {}, champs, texteControle)
      const extraction = {
        source_texte: scan ? 'transcription_ia' : 'natif', champs: resultats, resume: C.resume(resultats),
        caracteres_lus: texteControle.length, modele: 'Claude',
      }
      await ref.update({
        extraction_statut: 'terminee', extraction, texte_recu: texteControle.slice(0, 12000), activite: null, progression: null,
      })
      const r = extraction.resume
      await journaliser(dossierId, 'agent (Claude)', 'lecture_terminee',
        `${piece.nom} — ${r.verifie} champ(s) vérifié(s), ${r.citation_introuvable + r.valeur_hors_citation} non vérifié(s), ${r.absent} absent(s)`, pieceId)
    } catch (e) {
      await flux.fin()
      const message = e?.message && !MESSAGES_SAMPLE[e.code] && e.code !== 'upstream_error' ? e.message : messageSample(e)
      await ref.update({ extraction_statut: 'erreur', extraction_erreur: message, activite: null, progression: null }).catch(() => {})
      await journaliser(dossierId, 'agent (Claude)', 'lecture_echec', `${piece.nom} — ${message}`, pieceId).catch(() => {})
    }
  }

  // ------------------------------------------------------------ fichiers .docx
  const xml = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  async function docx(piece) {
    const para = (t, gras = false, taille = 22) =>
      `<w:p><w:r><w:rPr>${gras ? '<w:b/>' : ''}<w:sz w:val="${taille}"/></w:rPr><w:t xml:space="preserve">${xml(t)}</w:t></w:r></w:p>`
    const corps = [
      para(piece.nom, true, 32),
      para('PROJET GÉNÉRÉ AUTOMATIQUEMENT — EN ATTENTE DE VALIDATION HUMAINE. Ne pas déposer avant relecture et validation explicite.', true),
      ...String(piece.projet_texte).split('\n').filter((l) => l.trim()).map((l) => para(l)),
      para('Sources réglementaires utilisées (à vérifier)', true, 26),
      ...(piece.sources || []).map((s) => para(`• ${s.texte_source} — version du ${s.date_version} (${s.fichier}, extrait n°${s.chunk_index})`)),
    ].join('')
    const zip = new window.JSZip()
    zip.file('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    zip.file('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    zip.file('word/document.xml', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${corps}<w:sectPr/></w:body></w:document>`)
    return zip.generateAsync({ type: 'blob', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
  }

  // ------------------------------------------------------------ routes (mêmes que src/api.py)
  async function nouvelId() {
    const snap = await exigerDb().collection('dossiers').get()
    return snap.docs.reduce((m, d) => Math.max(m, Number(d.data().id) || 0), 0) + 1
  }

  function requis(pays, classe) {
    const r = REGLES.requis[`${pays}|${classe}`]
    if (!r) echec(422, "Pays d'origine ou classe inconnus.")
    return r
  }

  const exiger = (v, message) => { if (!v || String(v).trim().length < 2) echec(422, message) }

  async function router(methode, chemin, corps) {
    if (chemin === '/health') {
      await pret
      return json({
        statut: 'ok',
        services: { 'base de données': !!cap.db, 'agent (Claude)': !!cap.sample, 'stockage des documents': !!cap.assets },
        authentification: 'aucune',
        prochain_creneau_depot: prochainCreneau(),
      })
    }
    await pret
    if (chemin === '/pays') return json(REGLES.pays)
    if (chemin === '/dossiers/documents-requis') {
      return json({
        produit: corps.produit, pays_origine: corps.pays_origine, pays_destination: 'maroc',
        documents: requis(corps.pays_origine, corps.classe).map(({ consigne_redaction, champs_a_extraire, ...d }) => d),
        prochain_creneau_depot: prochainCreneau(),
      })
    }
    if (chemin === '/dossiers' && methode === 'GET') {
      const snap = await exigerDb().collection('dossiers').get()
      const dossiers = await Promise.all(snap.docs.map(async (s) => resumeDossier(s.data(), await lirePieces(s.data().id))))
      return json(dossiers.sort((a, b) => b.id - a.id))
    }
    if (chemin === '/dossiers' && methode === 'POST') {
      exiger(corps.produit, 'Indiquer le dispositif médical.')
      exiger(corps.cree_par, 'Créateur du dossier non identifié.')
      const liste = requis(corps.pays_origine, corps.classe)
      const id = await nouvelId()
      const dossier = {
        id, produit: String(corps.produit).slice(0, 300), pays_origine: corps.pays_origine, classe: corps.classe || null,
        fournisseur: corps.fournisseur ? String(corps.fournisseur).slice(0, 300) : null, regles_version: REGLES.regles_version,
        cree_par: corps.cree_par, cree_le: maintenant(),
      }
      await ecrire(refDossier(id), dossier, 'set')
      for (const [ordre, d] of liste.entries()) {
        const pid = id * 100 + ordre + 1
        await ecrire(refPiece(id, pid), {
          id: pid, dossier_id: id, ordre, code: d.id, nom: d.nom, nature: d.nature, fourni_par: d.fourni_par,
          consigne_redaction: d.consigne_redaction, champs_a_extraire: d.champs_a_extraire,
          traduction_requise: d.traduction_requise, legalisation_requise: d.legalisation_requise, origine_regle: d.origine_regle,
          statut: d.nature === 'a_rediger' ? 'a_generer' : 'a_obtenir',
        }, 'set')
      }
      await journaliser(id, corps.cree_par, 'dossier_cree', `${liste.length} pièces décidées par le moteur de règles (règles ${REGLES.regles_version})`)
      await majResume(id)
      return json(await detail(id), 201)
    }

    const m = chemin.match(/^\/dossiers\/(\d+)(?:\/documents\/(\d+))?(?:\/([\w-]+))?$/)
    if (!m) echec(404, 'Not Found')
    const dossierId = Number(m[1])
    const pieceId = m[2] ? Number(m[2]) : null
    const action = m[3] || null

    if (!pieceId && !action && methode === 'GET') return json(await detail(dossierId))

    if (!pieceId && action === 'generer') {
      exiger(corps.acteur, 'Acteur non identifié.')
      exigerAgent()
      const pieces = await lirePieces(dossierId)
      const aLancer = pieces.filter((p) => p.nature === 'a_rediger' && ['a_generer', 'erreur', 'rejete'].includes(p.statut))
      if (!aLancer.length) echec(409, 'Aucune pièce à rédiger en attente de génération.')
      for (const p of aLancer) {
        await ecrire(refPiece(dossierId, p.id), { statut: 'en_file', erreur: null, activite: 'En attente de l\'agent…', tache_signe_de_vie: maintenant() })
        await journaliser(dossierId, corps.acteur, 'generation_demandee', p.nom, p.id)
        planifier(dossierId, p.id, () => rediger(dossierId, p.id))
      }
      await majResume(dossierId)
      return json(await detail(dossierId), 202)
    }

    if (!pieceId) echec(404, 'Not Found')
    const piece = await chargerPiece(dossierId, pieceId)

    if (action === 'generer') {
      exiger(corps.acteur, 'Acteur non identifié.')
      if (piece.nature !== 'a_rediger') echec(409, `'${piece.nom}' est une pièce à fournir par ${piece.fourni_par} : elle n'est jamais rédigée par le système.`)
      if (!['a_generer', 'erreur', 'rejete', 'a_valider'].includes(piece.statut)) echec(409, `Pièce au statut '${piece.statut}' : génération impossible.`)
      exigerAgent()
      await ecrire(refPiece(dossierId, pieceId), { statut: 'en_file', erreur: null, activite: 'En attente de l\'agent…', tache_signe_de_vie: maintenant() })
      await journaliser(dossierId, corps.acteur, 'generation_demandee', piece.nom, pieceId)
      planifier(dossierId, pieceId, () => rediger(dossierId, pieceId))
      await majResume(dossierId)
      return json(await detail(dossierId), 202)
    }

    if (action === 'valider' || action === 'rejeter') {
      exiger(corps.validateur, 'Validateur non identifié.')
      const commentaire = (corps.commentaire || '').trim()
      if (action === 'valider') {
        if (piece.nature === 'a_rediger' && piece.statut !== 'a_valider') echec(409, `Pièce au statut '${piece.statut}' : seul un projet rédigé (statut a_valider) peut être validé.`)
        if (piece.nature === 'a_fournir') {
          if (!['a_obtenir', 'rejete'].includes(piece.statut)) echec(409, `Pièce au statut '${piece.statut}' : déjà validée.`)
          if (!commentaire) echec(422, 'Pour une pièce à fournir, indiquer en commentaire ce qui a été reçu et vérifié (référence, date…).')
        }
      } else {
        if (!commentaire) echec(422, 'Le motif du rejet (commentaire) est obligatoire.')
        const autorises = piece.nature === 'a_rediger' ? ['a_valider', 'valide'] : ['a_obtenir', 'valide']
        if (!autorises.includes(piece.statut)) echec(409, `Pièce au statut '${piece.statut}' : rejet impossible.`)
      }
      await ecrire(refPiece(dossierId, pieceId), {
        statut: action === 'valider' ? 'valide' : 'rejete', valide_par: corps.validateur, valide_le: maintenant(), commentaire: commentaire || null,
      })
      await journaliser(dossierId, corps.validateur, action === 'valider' ? 'piece_validee' : 'piece_rejetee',
        piece.nom + (commentaire ? ` — ${commentaire}` : ''), pieceId)
      await majResume(dossierId)
      return json(await detail(dossierId))
    }

    if (action === 'apercu') {
      if (!piece.projet_texte) echec(404, 'Aucun projet rédigé pour cette pièce.')
      const paragraphes = [
        { genre: 'titre', texte: piece.nom },
        { genre: 'texte', texte: 'PROJET GÉNÉRÉ AUTOMATIQUEMENT — EN ATTENTE DE VALIDATION HUMAINE. Ne pas déposer avant relecture et validation explicite.' },
        ...piece.projet_texte.split('\n').filter((l) => l.trim()).map((l) => ({ genre: 'texte', texte: l })),
        { genre: 'titre', texte: 'Sources réglementaires utilisées (à vérifier)' },
        ...(piece.sources || []).map((s) => ({ genre: 'puce', texte: `${s.texte_source} — version du ${s.date_version} (${s.fichier}, extrait n°${s.chunk_index})` })),
      ]
      return json({ piece: piece.nom, genere_le: piece.genere_le, paragraphes })
    }

    if (action === 'fichier') {
      if (!piece.projet_texte) echec(404, 'Aucun fichier généré pour cette pièce.')
      return new Response(await docx(piece), { status: 200 })
    }

    if (action === 'document-recu' && methode === 'GET') {
      if (!piece.fichier_recu_asset) echec(404, 'Aucun document reçu pour cette pièce.')
      const r = await fetch(`/_blob/${piece.fichier_recu_asset}`)
      if (!r.ok) echec(404, 'Document reçu introuvable dans le stockage.')
      return new Response(await r.blob(), { status: 200 })
    }

    if (action === 'document-recu' && methode === 'POST') {
      const fichier = corps.fichier
      exiger(corps.acteur, 'Acteur non identifié.')
      if (!(fichier instanceof Blob)) echec(422, 'Aucun fichier reçu.')
      const ext = (fichier.name || '').split('.').pop().toLowerCase()
      if (!TYPES[ext]) echec(415, 'Format non pris en charge : déposer un PDF, PNG ou JPG.')
      if (fichier.size > TAILLE_MAX) echec(413, 'Fichier trop volumineux (20 Mo maximum).')
      if (piece.nature !== 'a_fournir') echec(409, 'Seules les pièces à fournir reçoivent un document du fournisseur.')
      if (!(piece.champs_a_extraire || []).length) echec(409, `'${piece.nom}' n'a pas de champs à lire déclarés dans les règles.`)
      if (piece.statut === 'valide') echec(409, 'Pièce déjà validée : la rejeter avant de déposer un nouveau document.')
      if (['en_file', 'en_cours'].includes(piece.extraction_statut) && !abandonnee(piece)) echec(409, 'Une lecture est déjà en cours pour cette pièce.')
      exigerAgent()
      if (!cap.assets) echec(403, "Dépôt de documents réservé aux personnes pouvant modifier ce tableau de bord.")
      let asset
      try {
        asset = await cap.assets.upload(fichier, { type: TYPES[ext] })
      } catch (e) {
        echec(e?.code === 'too_large' ? 413 : e?.code === 'quota_or_state' ? 507 : 503,
          e?.code === 'quota_or_state' ? 'Stockage des documents plein.' : "Le document n'a pas pu être enregistré.")
      }
      fichiersEnMemoire.set(asset.id, fichier)
      await ecrire(refPiece(dossierId, pieceId), {
        fichier_recu_asset: asset.id, nom_fichier_recu: String(fichier.name).slice(0, 300), recu_le: maintenant(),
        extraction_statut: 'en_file', extraction: null, extraction_erreur: null, texte_recu: null,
        activite: "En attente de l'agent…", tache_signe_de_vie: maintenant(),
      })
      await journaliser(dossierId, corps.acteur, 'document_recu_depose', `${piece.nom} — ${fichier.name}`, pieceId)
      planifier(dossierId, pieceId, () => lireDocument(dossierId, pieceId))
      return json(await detail(dossierId), 202)
    }

    if (action === 'relire') {
      exiger(corps.acteur, 'Acteur non identifié.')
      if (!piece.fichier_recu_asset) echec(409, 'Aucun document reçu déposé pour cette pièce.')
      if (['en_file', 'en_cours'].includes(piece.extraction_statut) && !abandonnee(piece)) echec(409, 'Une lecture est déjà en cours pour cette pièce.')
      exigerAgent()
      await ecrire(refPiece(dossierId, pieceId), { extraction_statut: 'en_file', extraction_erreur: null, activite: "En attente de l'agent…", tache_signe_de_vie: maintenant() })
      await journaliser(dossierId, corps.acteur, 'lecture_demandee', piece.nom, pieceId)
      planifier(dossierId, pieceId, () => lireDocument(dossierId, pieceId))
      return json(await detail(dossierId), 202)
    }

    echec(404, 'Not Found')
  }

  const fetchOriginal = window.fetch.bind(window)
  window.fetch = async function (entree, options = {}) {
    const url = typeof entree === 'string' ? entree : entree.url
    if (!url.startsWith(BASE)) return fetchOriginal(entree, options)
    const chemin = new URL(url).pathname
    const methode = (options.method || 'GET').toUpperCase()
    let corps = {}
    if (options.body instanceof FormData) corps = Object.fromEntries(options.body.entries())
    else if (options.body) { try { corps = JSON.parse(options.body) } catch { corps = {} } }
    try {
      return await router(methode, chemin, corps)
    } catch (e) {
      if (e instanceof ErreurHttp) return json({ detail: e.message }, e.status)
      console.error('[moteur]', e)
      return json({ detail: 'Erreur inattendue du tableau de bord : recharger la page.' }, 500)
    }
  }
})()
