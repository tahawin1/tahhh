#!/usr/bin/env bash
# Sauvegarde du serveur : base PostgreSQL (dossiers, validations, journal
# d'audit), projets rédigés et documents reçus (output/), fichier .env,
# profil de l'entreprise (config/entreprise.yaml).
# Serveur Windows (WSL2) : copie en plus dans C:\ConformiteDM\sauvegardes,
# pour qu'elle soit reprise par les sauvegardes habituelles de Windows.
# L'index Qdrant n'est pas sauvegardé : il se reconstruit avec
# scripts/indexer_tout.sh.
#
#   sudo bash scripts/sauvegarder.sh [DOSSIER_DESTINATION]    (défaut : /var/backups/conformite)
#
# Programmée chaque nuit à 2 h par installer_serveur.sh (/etc/cron.d/conformite-sauvegarde).
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=${1:-/var/backups/conformite}
HORODATAGE=$(date +%Y-%m-%d_%H%M)
mkdir -p "$DEST" && chmod 700 "$DEST"

docker exec conformite-postgres pg_dump -U conformite -d conformite_dm --format=custom \
  > "$DEST/base_$HORODATAGE.dump"
tar -czf "$DEST/fichiers_$HORODATAGE.tar.gz" output $([ -f .env ] && echo .env) $([ -f config/entreprise.yaml ] && echo config/entreprise.yaml)
# garder 30 jours
find "$DEST" -name 'base_*.dump' -mtime +30 -delete
find "$DEST" -name 'fichiers_*.tar.gz' -mtime +30 -delete
# Serveur Windows : copie côté Windows (mêmes 30 jours)
if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null && [ -d /mnt/c ]; then
  COPIE=/mnt/c/ConformiteDM/sauvegardes
  mkdir -p "$COPIE" && cp "$DEST/base_$HORODATAGE.dump" "$DEST/fichiers_$HORODATAGE.tar.gz" "$COPIE/"
  find "$COPIE" -name 'base_*.dump' -mtime +30 -delete
  find "$COPIE" -name 'fichiers_*.tar.gz' -mtime +30 -delete
  echo "  copie Windows : C:\\ConformiteDM\\sauvegardes"
fi
echo "$(date '+%F %T') sauvegarde OK : $DEST/base_$HORODATAGE.dump ($(du -h "$DEST/base_$HORODATAGE.dump" | cut -f1)), fichiers_$HORODATAGE.tar.gz"
