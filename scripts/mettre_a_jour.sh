#!/usr/bin/env bash
# Mise à jour du serveur avec la dernière version publiée sur GitHub.
#
#   cd /opt/conformite && sudo bash scripts/mettre_a_jour.sh                  # depuis GitHub
#   cd /opt/conformite && sudo bash scripts/mettre_a_jour.sh /tmp/maj.bundle  # depuis un fichier envoyé par Taha
#                                                         (serveur sans accès à GitHub)
#
# Étapes : sauvegarde -> récupération du code -> reconstruction et
# redémarrage -> contrôle de santé -> rapport (sans aucun secret) à
# renvoyer à Taha. En cas d'échec du contrôle, rien n'est perdu : la
# sauvegarde du jour est dans /var/backups/conformite.
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo."; exit 1; }
PROFILS=(--profile api --profile interface)
grep -q '^NGROK_AUTHTOKEN=' .env 2>/dev/null && grep -q '^NGROK_URL=' .env && PROFILS+=(--profile ngrok)
set -a; . ./.env; set +a

echo "== 1. Sauvegarde"
bash scripts/sauvegarder.sh

echo "== 2. Code"
git config --global --get-all safe.directory | grep -qx "$PWD" || git config --global --add safe.directory "$PWD"
[ -z "$(git status --porcelain --untracked-files=no)" ] \
  || { echo "  Des fichiers du code ont été modifiés à la main sur le serveur :"; git status --short --untracked-files=no; echo "  Annuler ces modifications (git checkout -- .) ou prévenir Taha, puis relancer."; exit 1; }
AVANT=$(git rev-parse --short HEAD)
BRANCHE=$(git rev-parse --abbrev-ref HEAD)
if [ -n "${1:-}" ]; then
  git bundle verify "$1" >/dev/null || { echo "  Fichier de mise à jour invalide : $1"; exit 1; }
  git pull --ff-only "$1" "$BRANCHE"
else
  git pull --ff-only origin "$BRANCHE"
fi
APRES=$(git rev-parse --short HEAD)
if [ "$AVANT" = "$APRES" ]; then echo "  déjà à jour ($APRES)"; else echo "  $AVANT -> $APRES"; git log --oneline "$AVANT..$APRES" | sed 's/^/    /'; fi

echo "== 3. Reconstruction et redémarrage"
docker compose "${PROFILS[@]}" up -d --build
docker image prune -f >/dev/null

echo "== 4. Contrôle"
for i in $(seq 1 60); do curl -s http://127.0.0.1:8000/health | grep -q '"statut":"ok"' && break; sleep 2; done
SANTE=$(curl -s http://127.0.0.1:8000/health || echo "API injoignable")
INTERFACE=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${INTERFACE_PORT:-80}/api/health" || true)
POINTS=$(curl -s http://127.0.0.1:6333/collections/dossiers_reference | grep -o '"points_count":[0-9]*' | tr -dc '0-9' || true)

echo
echo "===== RAPPORT À ENVOYER À TAHA (ne contient aucun secret) ====="
echo "date        : $(date '+%F %T')"
echo "version     : $APRES ($(git log -1 --format=%s | cut -c1-70))"
echo "api         : $SANTE"
echo "interface   : HTTP $INTERFACE"
echo "index       : ${POINTS:-?} extraits"
echo "modèles     : $(ollama list 2>/dev/null | awk 'NR>1 {print $1}' | tr '\n' ' ')"
echo "gpu         : $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo aucun)"
echo "conteneurs  :"; docker compose "${PROFILS[@]}" ps --format '{{.Name}} {{.Status}}' | sed 's/^/  /'
echo "erreurs API (20 dernières lignes contenant « error ») :"
docker compose logs --tail 500 api 2>&1 | grep -i error | tail -20 | sed 's/^/  /' || true
echo "================================================================="
echo "$SANTE" | grep -q '"postgres":true,"qdrant":true,"ollama":true' && [ "$INTERFACE" = 200 ] \
  && echo "Mise à jour réussie." || { echo "Contrôle en échec : envoyer ce rapport à Taha."; exit 1; }
