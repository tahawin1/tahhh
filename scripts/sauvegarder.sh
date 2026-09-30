#!/usr/bin/env bash
# Sauvegarde du serveur : base PostgreSQL (dossiers, validations, journal
# d'audit), projets rédigés et documents reçus (output/), fichier .env.
# L'index Qdrant n'est pas sauvegardé : il se reconstruit avec
# scripts/indexer_tout.sh.
#
#   sudo bash scripts/sauvegarder.sh [DOSSIER_DESTINATION]    (défaut : /var/backups/conformite)
#
# Tâche quotidienne à 2 h (sudo crontab -e) :
#   0 2 * * * bash /opt/conformite/scripts/sauvegarder.sh >> /var/log/conformite-sauvegarde.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=${1:-/var/backups/conformite}
HORODATAGE=$(date +%Y-%m-%d_%H%M)
mkdir -p "$DEST" && chmod 700 "$DEST"

docker exec conformite-postgres pg_dump -U conformite -d conformite_dm --format=custom \
  > "$DEST/base_$HORODATAGE.dump"
tar -czf "$DEST/fichiers_$HORODATAGE.tar.gz" output $([ -f .env ] && echo .env)
# garder 30 jours
find "$DEST" -name 'base_*.dump' -mtime +30 -delete
find "$DEST" -name 'fichiers_*.tar.gz' -mtime +30 -delete
echo "$(date '+%F %T') sauvegarde OK : $DEST/base_$HORODATAGE.dump ($(du -h "$DEST/base_$HORODATAGE.dump" | cut -f1)), fichiers_$HORODATAGE.tar.gz"
