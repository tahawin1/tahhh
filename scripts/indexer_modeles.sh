#!/usr/bin/env bash
# Indexe les dossiers acceptés (data/dossiers_valides/) comme modèles de
# rédaction pour Mistral. À relancer après avoir ajouté un dossier accepté.
# Relançable sans risque (un modèle déjà indexé est remplacé).
#
#   sudo bash scripts/indexer_modeles.sh
#
# Rangement attendu (le numéro en tête du nom = numéro de la pièce déposée) :
#   data/dossiers_valides/union_europeenne/Ciment osseux/…/1-1-Lettre de Demande.pdf
#   data/dossiers_valides/union_europeenne/Ciment osseux/…/2-2-fiche signalétique.pdf
#   data/dossiers_valides/union_europeenne/Ciment osseux/…/16-16-Certificat d'enregistrement.pdf
# Dossiers de pays : chine, inde, union_europeenne, autre.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -z "$(find data/dossiers_valides -name '*.pdf' 2>/dev/null | head -1)" ]; then
  echo "Aucun dossier accepté dans data/dossiers_valides/ : rien à indexer (Mistral rédige alors sans modèle)."
  exit 0
fi
# Puis Mistral lit la fiche signalétique et l'annexe II acceptées (mémoire,
# src/memoire.py) : leurs données servent aux dossiers suivants du même fabricant.
echo "Modèles de rédaction, puis mémoire : Mistral lit chaque formulaire accepté (quelques minutes"
echo "par dossier, sans rien afficher pendant la lecture : NE PAS interrompre)."
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx conformite-api; then
  docker exec conformite-api python3 -u src/modeles.py          # serveur : dans le conteneur de l'API
  docker exec conformite-api python3 -u src/memoire.py
else
  PYTHON=python3; [ -x .venv/bin/python ] && PYTHON=.venv/bin/python
  $PYTHON src/modeles.py                                      # développement
  $PYTHON src/memoire.py
fi
