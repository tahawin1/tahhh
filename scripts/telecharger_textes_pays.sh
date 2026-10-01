#!/usr/bin/env bash
# Télécharge les textes officiels des États-Unis, de la Corée du Sud et du
# Pakistan (sources officielles uniquement), en extrait le texte (OCR si le
# PDF est scanné) et tient à jour data/raw_pdfs/SOURCES_PAYS.md (adresse,
# date, empreinte SHA-256). Relançable : un fichier déjà présent est gardé.
#
#   bash scripts/telecharger_textes_pays.sh          # télécharge + extrait le texte
#   puis : bash scripts/indexer_textes_pays.sh       # indexe dans Qdrant
#
# Aucun identifiant nécessaire. Un téléchargement en échec n'arrête pas les
# autres : il est signalé, et le fichier peut être déposé à la main sous le
# même nom dans data/raw_pdfs/.
set -uo pipefail
cd "$(dirname "$0")/.."
DEST=data/raw_pdfs
mkdir -p "$DEST/textes"
PYTHON=python3; [ -x .venv/bin/python ] && PYTHON=.venv/bin/python
UA="Mozilla/5.0 (conformite-dm; telechargement de textes officiels)"
ECHECS=0
MANIFESTE="$DEST/SOURCES_PAYS.md"
[ -f "$MANIFESTE" ] || printf '# Textes officiels — États-Unis, Corée du Sud, Pakistan\n\n| Fichier | Source officielle | Téléchargé le | SHA-256 |\n|---|---|---|---|\n' > "$MANIFESTE"

noter() {  # fichier url
  local empreinte; empreinte=$(sha256sum "$DEST/$1" | cut -c1-16)
  grep -q "| $1 |" "$MANIFESTE" || printf '| %s | %s | %s | %s… |\n' "$1" "$2" "$(date +%F)" "$empreinte" >> "$MANIFESTE"
}

pdf() {  # nom url
  local nom=$1 url=$2
  if [ -s "$DEST/$nom" ]; then echo "  = $nom déjà présent"; return; fi
  if curl -fsSL --retry 3 --retry-delay 4 -m 300 -A "$UA" -o "$DEST/$nom.tmp" "$url" \
     && head -c 5 "$DEST/$nom.tmp" | grep -q '%PDF'; then
    mv "$DEST/$nom.tmp" "$DEST/$nom"; noter "$nom" "$url"; echo "  ✓ $nom"
  else
    rm -f "$DEST/$nom.tmp"; ECHECS=$((ECHECS+1))
    echo "  ✗ $nom : téléchargement impossible ($url) — le déposer à la main sous ce nom"
  fi
}

echo "== États-Unis : 21 CFR (eCFR, édition officielle à jour)"
DATE_CFR=$(curl -fsSL -m 60 -A "$UA" https://www.ecfr.gov/api/versioner/v1/titles.json \
  | $PYTHON -c "import json,sys; print(next(t['latest_issue_date'] for t in json.load(sys.stdin)['titles'] if t['number']==21))" 2>/dev/null)
if [ -z "$DATE_CFR" ]; then
  echo "  ✗ ecfr.gov injoignable"; ECHECS=$((ECHECS+1))
else
  for part in 801 807 814 820 860; do
    nom="etats_unis_21cfr_${part}.xml"
    url="https://www.ecfr.gov/api/versioner/v1/full/${DATE_CFR}/title-21.xml?part=${part}"
    if [ -s "$DEST/$nom" ]; then echo "  = $nom déjà présent"; continue; fi
    if curl -fsSL --retry 3 -m 300 -A "$UA" -o "$DEST/$nom" "$url"; then
      noter "$nom" "$url (édition du $DATE_CFR)"; echo "  ✓ $nom (édition du $DATE_CFR)"
    else rm -f "$DEST/$nom"; ECHECS=$((ECHECS+1)); echo "  ✗ $nom"; fi
  done
fi

echo "== Corée du Sud : Medical Devices Act (traduction anglaise officielle)"
pdf coree_medical_devices_act.pdf \
  "https://importlicensing.wto.org/sites/default/files/members/78/Medical%20Devices%20Act_23.04.2019.pdf"
echo "  (version la plus récente et décret/arrêté d'application : MFDS https://www.mfds.go.kr/eng/brd/m_40/list.do"
echo "   ou KLRI https://elaw.klri.re.kr — à déposer sous coree_*.pdf, puis relancer l'indexation)"

echo "== Pakistan : Medical Devices Rules 2017 (DRAP)"
pdf pakistan_medical_devices_rules_2017_maj_2022.pdf \
  "https://www.dra.gov.pk/wp-content/uploads/2022/10/Medical-Devices-Rules-2017-updated-upto-april-2022-2.pdf"
pdf pakistan_medical_devices_rules_2017_sro32_2018.pdf \
  "https://www.dra.gov.pk/wp-content/uploads/2022/02/FFMedicalDevicesRules2017Notifiedon16-01-2018-1.pdf"

echo "== Texte pivot : principes de classification IMDRF/GHTF (N77:2012)"
pdf imdrf_ghtf_sg1_n77_2012_classification.pdf \
  "https://www.imdrf.org/sites/default/files/docs/ghtf/final/sg1/technical-docs/ghtf-sg1-n77-2012-principles-medical-devices-classification-121102.pdf"

echo "== Extraction du texte (OCR des pages scannées) -> $DEST/textes/"
$PYTHON - "$DEST" <<'PY'
import re, sys
from pathlib import Path
sys.path.insert(0, "src")
dest = Path(sys.argv[1])
for f in sorted(dest.glob("*")):
    if not re.match(r"(etats_unis|coree|pakistan|imdrf)_", f.name) or f.suffix not in (".pdf", ".xml"):
        continue
    sortie = dest / "textes" / (f.stem + ".txt")
    if sortie.exists():
        continue
    if f.suffix == ".xml":  # eCFR : on garde titres et paragraphes, sans balises
        from xml.etree import ElementTree as ET
        racine = ET.parse(f).getroot()
        lignes = []
        for e in racine.iter():
            if e.tag in ("HEAD", "P", "FP", "CITA", "AUTH", "SOURCE") and "".join(e.itertext()).strip():
                lignes.append(("\n" if e.tag == "HEAD" else "") + " ".join("".join(e.itertext()).split()))
        texte = "\n".join(lignes)
    else:
        from ingest import extraire_texte
        texte = extraire_texte(f, langues_ocr="eng")
    sortie.write_text(texte, encoding="utf-8")
    print(f"  ✓ {sortie.name} ({len(texte)} caractères)")
PY

echo
if [ "$ECHECS" -eq 0 ]; then echo "Terminé. Indexer ensuite : bash scripts/indexer_textes_pays.sh"
else echo "Terminé avec $ECHECS échec(s) (voir ✗ ci-dessus)."; exit 1; fi
