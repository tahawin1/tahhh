// Mêmes cas que tests/test_extraction.py, pour le portage JavaScript.
//   node claude_ai/test_controle.js
const assert = require('node:assert/strict')
const C = require('./controle.js')

const TEXTE = `SPECIMEN CERTIFICATION BODY
CERTIFICATE No. SCB-MD-2024-0457
This is to certify that the quality management system of
Hangzhou Specimen Orthopaedics Co., Ltd.
has been assessed and found to comply with ISO 13485:2016
Scope: Design and manufacture of hip joint prostheses
Date of issue: 12 March 2024      Valid until: 11 March 2027`

let n = 0
const cas = (nom, fn) => { fn(); n++; console.log('✓', nom) }

cas('dates : formats FR/EN/CN', () => {
  for (const [brut, attendu] of [
    ['12 March 2024', '2024-03-12'], ['March 12, 2024', '2024-03-12'], ['12/03/2024', '2024-03-12'],
    ['2024-03-12', '2024-03-12'], ['12 mars 2024', '2024-03-12'], ['1er août 2025', '2025-08-01'],
    ['2024年3月12日', '2024-03-12'], ['12.03.2024', '2024-03-12'],
  ]) assert.equal(C.normaliserDate(brut), attendu, brut)
})
cas('dates : illisibles ou impossibles', () => {
  for (const brut of ['bientôt', '31/02/2024', '', null]) assert.equal(C.normaliserDate(brut), null, String(brut))
})
cas('citation exacte malgré casse et espaces', () => assert.ok(C.citationTrouvee('certificate  no. scb-md-2024-0457', TEXTE)))
cas('citation avec une erreur OCR tolérée', () =>
  assert.ok(C.citationTrouvee('Hangzhou Specimen 0rthopaedics Co., Ltd. has been assessed', TEXTE)))
cas('citation inventée refusée', () => assert.ok(!C.citationTrouvee('Rue du Trône, Rabat, Maroc', TEXTE)))
cas('mots piochés dans tout le document refusés', () =>
  assert.ok(!C.citationTrouvee('certificate hip valid 2027 specimen', TEXTE)))
cas('verdicts du contrôle', () => {
  const champs = [
    { nom: 'numero', libelle: 'Numéro' }, { nom: 'titulaire', libelle: 'Titulaire' },
    { nom: 'date_expiration', libelle: "Valable jusqu'au", type: 'date' }, { nom: 'classe_indiquee', libelle: 'Classe' },
  ]
  const r = Object.fromEntries(C.controler({
    numero: { valeur: 'SCB-MD-2024-0457', citation: 'CERTIFICATE No. SCB-MD-2024-0457' },
    titulaire: { valeur: 'Beijing Invented Medical', citation: 'Beijing Invented Medical Co.' },
    date_expiration: { valeur: '11 March 2027', citation: 'Date of issue: 12 March 2024' },
    classe_indiquee: { valeur: null, citation: null },
  }, champs, TEXTE).map((c) => [c.nom, c]))
  assert.equal(r.numero.verification, C.VERIFIE)
  assert.equal(r.titulaire.verification, C.CITATION_INTROUVABLE)
  assert.equal(r.date_expiration.verification, C.VALEUR_HORS_CITATION)
  assert.equal(r.date_expiration.valeur_normalisee, '2027-03-11')
  assert.equal(r.classe_indiquee.verification, C.ABSENT)
})
console.log(`\n${n} cas OK`)
