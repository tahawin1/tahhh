#!/usr/bin/env bash
# Indexe dans Qdrant les textes des États-Unis, de la Corée du Sud et du
# Pakistan (et le texte pivot IMDRF) extraits par telecharger_textes_pays.sh.
# Un texte absent est signalé et sauté. Relançable (identifiants stables).
set -uo pipefail
cd "$(dirname "$0")/.."
PYTHON=python3; [ -x .venv/bin/python ] && PYTHON=.venv/bin/python
T=data/raw_pdfs/textes

indexer() {  # fichier pays type date libellé
  if [ ! -s "$T/$1" ]; then echo "  ! $1 absent (lancer scripts/telecharger_textes_pays.sh)"; return; fi
  $PYTHON src/ingest.py --source "$T/$1" --pays "$2" --type-document "$3" --date-version "$4" --texte-source "$5"
}
version_cfr() { grep -F "| $1 |" data/raw_pdfs/SOURCES_PAYS.md 2>/dev/null | grep -o 'édition du [0-9-]*' | cut -d' ' -f3; }

echo "=== États-Unis ==="
for part in 801 807 814 820 860; do
  indexer "etats_unis_21cfr_${part}.txt" etats_unis reglement "$(version_cfr etats_unis_21cfr_${part}.xml || date +%F)" "21 CFR Part ${part}"
done
echo "=== Corée du Sud ==="
indexer coree_medical_devices_act.txt coree_du_sud loi 2019-04-23 "Medical Devices Act (Corée du Sud, traduction anglaise, version du 23-04-2019)"
echo "=== Pakistan ==="
indexer pakistan_medical_devices_rules_2017_maj_2022.txt pakistan reglement 2022-04-30 "Medical Devices Rules 2017 (DRAP, mis à jour jusqu'en avril 2022)"
echo "=== Texte pivot (rapprochement) ==="
indexer imdrf_ghtf_sg1_n77_2012_classification.txt international annexe_technique 2012-11-02 "GHTF/SG1/N77:2012 — Principles of Medical Devices Classification"
