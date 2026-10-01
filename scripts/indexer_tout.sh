#!/usr/bin/env bash
# Indexe tous les textes réglementaires collectés dans data/raw_pdfs/
# Nécessite que Qdrant tourne (voir docker-compose.yml : docker compose up -d qdrant)
set -e
cd "$(dirname "$0")/.."

# Utilise l'environnement virtuel du projet s'il existe (.venv), sinon python3
PYTHON=python3
[ -x .venv/bin/python ] && PYTHON=.venv/bin/python

echo "=== Maroc ==="
$PYTHON src/ingest.py --source data/raw_pdfs/maroc_loi_84-12.pdf \
  --pays maroc --type-document loi --date-version 2013-08-30 \
  --texte-source "Loi 84-12 relative aux dispositifs médicaux"

$PYTHON src/ingest.py --source data/raw_pdfs/maroc_decret_2-14-607.pdf \
  --pays maroc --type-document decret --date-version 2014-09-18 \
  --texte-source "Décret 2-14-607"

$PYTHON src/ingest.py --source data/raw_pdfs/maroc_arretes_2853-2856.pdf \
  --pays maroc --type-document arrete --date-version 2015-08-04 \
  --texte-source "Arrêtés 2853/2854/2855/2856-15"

echo "=== Chine ==="
$PYTHON src/ingest.py --source data/raw_pdfs/chine_order_739.pdf \
  --pays chine --type-document reglement --date-version 2021-02-09 \
  --texte-source "Order 739 - Regulations on Supervision and Administration of Medical Devices"

echo "=== Inde ==="
$PYTHON src/ingest.py --source data/raw_pdfs/inde_mdr_2017.txt \
  --pays inde --type-document reglement --date-version 2017-01-31 \
  --texte-source "Medical Devices Rules 2017"

$PYTHON src/ingest.py --source data/raw_pdfs/inde_device_definition_2020.pdf \
  --pays inde --type-document annexe_technique --date-version 2020-02-11 \
  --texte-source "S.O. 648(E) - Medical Device Definition"

$PYTHON src/ingest.py --source data/raw_pdfs/inde_exemption_classe_a_2022.pdf \
  --pays inde --type-document annexe_technique --date-version 2022-10-14 \
  --texte-source "G.S.R. 777(E) - Exemption classe A"

$PYTHON src/ingest.py --source data/raw_pdfs/inde_amendement_rule46_2021.pdf \
  --pays inde --type-document annexe_technique --date-version 2021-12-31 \
  --texte-source "G.S.R. 918(E) - Amendement Rule 46 UDI"

# ATTENTION : malgré son nom, data/raw_pdfs/ue_mdr_annexe.txt n'est PAS une
# annexe du MDR européen : c'est la version consolidée des Medical Devices
# Rules 2017 INDIENNES (amendées jusqu'au G.S.R. 777(E) du 14-10-2022).
# Indexée donc sous pays=inde, comme une version distincte (date_version
# différente) de inde_mdr_2017.txt — jamais sous union_europeenne.
$PYTHON src/ingest.py --source data/raw_pdfs/ue_mdr_annexe.txt \
  --pays inde --type-document reglement --date-version 2022-10-14 \
  --texte-source "Medical Devices Rules 2017 (version consolidée, amendée jusqu'au G.S.R. 777(E) du 14-10-2022)"

echo "=== Union européenne ==="
$PYTHON src/ingest.py --source data/raw_pdfs/ue_mdr_2017-745.txt \
  --pays union_europeenne --type-document reglement --date-version 2026-06-29 \
  --texte-source "Règlement (UE) 2017/745 (MDR) - version consolidée (amendements M1 à M8, JO du 29.6.2026)"

echo "=== États-Unis, Corée du Sud, Pakistan (si téléchargés) ==="
bash scripts/indexer_textes_pays.sh

echo ""
echo "Indexation terminée."
