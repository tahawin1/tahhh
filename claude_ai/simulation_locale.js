// TESTS LOCAUX UNIQUEMENT — jamais publié. Simule window.claude.use() de
// claude.ai pour éprouver claude_ai/moteur.js hors de claude.ai :
//   db        en mémoire (sous-ensemble fidèle : doc/collection, get/set/update,
//             orderBy, limit)
//   assets    fichiers gardés en mémoire, servis sur /_blob/<id>
//   sample    l'agent est le Mistral LOCAL (Ollama, texte diffusé en direct) ;
//             pas de lecture d'images (Mistral 7B n'a pas de vision)
//   user      « Testeur local » ; downloads : fichier gardé pour inspection
;(function () {
  const donnees = new Map()
  const fichiers = new Map()
  window.__simulation = { donnees, fichiers, enregistres: [] }
  const cloner = (o) => JSON.parse(JSON.stringify(o))
  const parent = (chemin) => chemin.split('/').slice(0, -1).join('/')

  function fusion(cible, source) {
    for (const [k, v] of Object.entries(source)) {
      if (v && typeof v === 'object' && !Array.isArray(v) && cible[k] && typeof cible[k] === 'object' && !Array.isArray(cible[k])) fusion(cible[k], v)
      else cible[k] = v
    }
    return cible
  }

  const instantane = (chemin) => ({
    id: chemin.split('/').pop(), exists: donnees.has(chemin),
    data: () => (donnees.has(chemin) ? cloner(donnees.get(chemin)) : undefined), metadata: { fromCache: false, hasPendingWrites: false },
  })

  function doc(chemin) {
    if (chemin.split('/').length % 2) throw new TypeError(`chemin de document impair : ${chemin}`)
    return {
      id: chemin.split('/').pop(), path: chemin,
      get: async () => instantane(chemin),
      set: async (d) => { donnees.set(chemin, cloner(d)) },
      update: async (d) => {
        if (!donnees.has(chemin)) throw { code: 'invalid_argument', message: 'document absent' }
        donnees.set(chemin, fusion(donnees.get(chemin), cloner(d)))
      },
      delete: async () => { donnees.delete(chemin) },
      collection: (sous) => collection(`${chemin}/${sous}`),
    }
  }

  function collection(chemin, tri = null, max = null) {
    const q = {
      path: chemin,
      doc: (id) => doc(`${chemin}/${id ?? Math.random().toString(36).slice(2)}`),
      orderBy: (champ, sens = 'asc') => collection(chemin, { champ, sens }, max),
      limit: (n) => collection(chemin, tri, n),
      where: () => q,
      get: async () => {
        let docs = [...donnees.keys()].filter((k) => parent(k) === chemin).map(instantane)
        if (tri) docs.sort((a, b) => (a.data()[tri.champ] > b.data()[tri.champ] ? 1 : -1) * (tri.sens === 'desc' ? -1 : 1))
        if (max) docs = docs.slice(0, max)
        return { docs, size: docs.length, empty: !docs.length }
      },
    }
    return q
  }

  async function ollama(prompt, options, formatJson) {
    const r = await fetch('http://127.0.0.1:11434/api/generate', {
      method: 'POST',
      body: JSON.stringify({ model: 'mistral', prompt, stream: true, ...(formatJson ? { format: 'json' } : {}), options: { temperature: 0, num_ctx: 8192, num_predict: 1200 } }),
    })
    const lecteur = r.body.getReader()
    const dec = new TextDecoder()
    let texte = ''
    let reste = ''
    for (;;) {
      const { done, value } = await lecteur.read()
      if (done) break
      const lignes = (reste + dec.decode(value, { stream: true })).split('\n')
      reste = lignes.pop()
      for (const l of lignes) {
        if (!l.trim()) continue
        const delta = JSON.parse(l).response || ''
        if (delta) { texte += delta; options.onText?.({ text: texte, delta }) }
      }
    }
    return texte
  }

  const sample = async (prompt, options = {}) => {
    if (options.images) throw { code: 'images_unavailable', message: 'simulation sans vision' }
    return { text: await ollama(prompt, options, false), truncated: false, modelTierApplied: 'default' }
  }
  sample.json = async (prompt, options = {}) => {
    if (options.images) throw { code: 'images_unavailable', message: 'simulation sans vision' }
    const t = await ollama(prompt, options, true)
    try { return JSON.parse(t) } catch { throw { code: 'invalid_json', message: 'JSON invalide', text: t } }
  }
  sample.limits = async () => ({ maxPromptBytes: 262144 })

  const assets = {
    upload: async (blob, opts = {}) => {
      const id = Math.random().toString(16).slice(2).padEnd(32, '0').slice(0, 32)
      fichiers.set(id, new Blob([await blob.arrayBuffer()], { type: opts.type || blob.type }))
      return { id, url: `/_blob/${id}`, sizeBytes: blob.size, contentType: opts.type || blob.type }
    },
  }

  const capacites = {
    db: { doc, collection: (c) => collection(c) },
    assets,
    sample,
    user: { me: async () => ({ id: 'u_test', name: 'Testeur local', isOwner: true, canEdit: true }) },
    downloads: { save: async ({ filename, data }) => { window.__simulation.enregistres.push({ filename, taille: data.size }); return { status: 'saved' } } },
  }
  window.claude = { use: async (nom) => capacites[nom] ?? null }

  const fetchNatif = window.fetch.bind(window)
  window.fetch = async (entree, options) => {
    const url = typeof entree === 'string' ? entree : entree.url
    const m = url.match(/\/_blob\/([0-9a-f]{32})$/)
    if (m) return fichiers.has(m[1]) ? new Response(fichiers.get(m[1])) : new Response('', { status: 404 })
    return fetchNatif(entree, options)
  }
})()
