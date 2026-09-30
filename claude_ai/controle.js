// Contrôle des extractions — portage fidèle de src/extraction.py pour
// l'édition claude.ai. Une valeur proposée par l'IA n'est « vérifiée » que
// si la citation qui la justifie est retrouvée dans le texte du document ET
// contient la valeur. Mêmes cas de test que tests/test_extraction.py :
//   node claude_ai/test_controle.js
;(function (racine) {
  const VERIFIE = 'verifie'
  const CITATION_INTROUVABLE = 'citation_introuvable'
  const VALEUR_HORS_CITATION = 'valeur_hors_citation'
  const ABSENT = 'absent'

  const TYPO = { '’': "'", '‘': "'", '“': '"', '”': '"', '–': '-', '—': '-', ' ': ' ' }

  function normaliser(texte) {
    let t = String(texte).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
    t = t.replace(/[’‘“”–— ]/g, (c) => TYPO[c])
    return t.replace(/\s+/g, ' ').trim()
  }

  const mots = (texte) => normaliser(texte).match(/[a-z0-9]+/g) || []

  // Tolère les petites erreurs d'OCR : 85 % des mots de la citation,
  // dans l'ordre, sur un passage compact du document.
  function citationTrouvee(citation, texte) {
    if (!citation || !citation.trim()) return false
    if (normaliser(texte).includes(normaliser(citation))) return true
    const mc = mots(citation)
    const mt = mots(texte)
    if (mc.length < 3) return false
    const fenetre = 2 * mc.length + 3
    for (let debut = 0; debut < mt.length; debut++) {
      if (!mc.slice(0, 3).includes(mt[debut])) continue
      let j = 0
      let trouves = 0
      for (let i = debut; i < Math.min(mt.length, debut + fenetre) && j < mc.length; i++) {
        const k = mc.indexOf(mt[i], j)
        if (k !== -1 && k - j <= 2) { trouves++; j = k + 1 }
      }
      if (trouves / mc.length >= 0.85) return true
    }
    return false
  }

  function valeurDansCitation(valeur, citation) {
    const v = mots(valeur).join(' ')
    return !!v && mots(citation).join(' ').includes(v)
  }

  const MOIS = {
    janvier: 1, fevrier: 2, mars: 3, avril: 4, mai: 5, juin: 6, juillet: 7, aout: 8, septembre: 9, octobre: 10,
    novembre: 11, decembre: 12, january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8,
    september: 9, october: 10, november: 11, december: 12, jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7,
    aug: 8, sep: 9, sept: 9, oct: 10, nov: 11, dec: 12,
  }

  function isoValide(a, m, j) {
    const d = new Date(Date.UTC(a, m - 1, j))
    if (d.getUTCFullYear() !== a || d.getUTCMonth() !== m - 1 || d.getUTCDate() !== j) return null
    return `${a}-${String(m).padStart(2, '0')}-${String(j).padStart(2, '0')}`
  }

  // '12/03/2024', '2024-03-12', '12 mars 2024', 'March 12, 2024', '2024年3月12日' -> '2024-03-12'
  function normaliserDate(valeur) {
    if (!valeur) return null
    const v = normaliser(valeur)
    let m
    if ((m = String(valeur).match(/(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})/))) return isoValide(+m[1], +m[2], +m[3])
    if ((m = v.match(/(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})/))) return isoValide(+m[3], +m[2], +m[1])
    if ((m = v.match(/(\d{1,2})(?:er)?\s+([a-z]+)\.?,?\s+(\d{4})/)) && MOIS[m[2]]) return isoValide(+m[3], MOIS[m[2]], +m[1])
    if ((m = v.match(/([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})/)) && MOIS[m[1]]) return isoValide(+m[3], MOIS[m[1]], +m[2])
    return null
  }

  function controler(reponse, champs, texte) {
    return champs.map((c) => {
      const brut = (reponse && reponse[c.nom]) || {}
      const valeur = (typeof brut.valeur === 'string' && brut.valeur.trim()) || null
      const citation = (typeof brut.citation === 'string' && brut.citation.trim()) || null
      let verification
      if (valeur === null) verification = ABSENT
      else if (!citationTrouvee(citation || '', texte)) verification = CITATION_INTROUVABLE
      else if (!valeurDansCitation(valeur, citation)) verification = VALEUR_HORS_CITATION
      else verification = VERIFIE
      return {
        nom: c.nom, libelle: c.libelle, type: c.type || 'texte', valeur,
        valeur_normalisee: c.type === 'date' ? normaliserDate(valeur) : valeur, citation, verification,
      }
    })
  }

  function resume(resultats) {
    const r = { [VERIFIE]: 0, [CITATION_INTROUVABLE]: 0, [VALEUR_HORS_CITATION]: 0, [ABSENT]: 0 }
    resultats.forEach((c) => { r[c.verification] += 1 })
    return r
  }

  const api = {
    VERIFIE, CITATION_INTROUVABLE, VALEUR_HORS_CITATION, ABSENT,
    normaliser, citationTrouvee, valeurDansCitation, normaliserDate, controler, resume,
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = api
  else racine.ControleExtraction = api
})(typeof window !== 'undefined' ? window : globalThis)
