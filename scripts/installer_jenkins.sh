#!/usr/bin/env bash
# Installe (ou met à jour) Jenkins sur le serveur, dans Docker, à côté de
# l'outil. Relançable sans risque.
#
#   cd /opt/conformite && sudo bash scripts/installer_jenkins.sh
#
# Puis : http://localhost:8081 (ou http://IP-du-serveur:8081), compte « admin ».
# Le mot de passe est dans .env (jamais versionné) ; il n'est pas affiché ici
# (la sortie de ce script est enregistrée dans les rapports) : outil Windows
# « 11 - Jenkins », ou : sudo grep JENKINS_ADMIN_PASSWORD /opt/conformite/.env
# La tâche « conformite-dm » est créée d'office et lance son premier build.
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo."; exit 1; }
touch .env && chmod 600 .env

if ! grep -q '^JENKINS_ADMIN_PASSWORD=' .env; then
  echo "JENKINS_ADMIN_PASSWORD=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20)" >> .env
  echo "  mot de passe administrateur Jenkins créé dans .env"
fi
grep -q '^JENKINS_BRANCHE=' .env || echo "JENKINS_BRANCHE=$(git rev-parse --abbrev-ref HEAD)" >> .env
set -a; . ./.env; set +a

mkdir -p /var/jenkins_home /var/backups/conformite
echo "== Construction et démarrage de Jenkins (quelques minutes la première fois)"
docker compose --profile jenkins up -d --build jenkins

PORT=${JENKINS_PORT:-8081}
for i in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/login" || true)
  [ "$code" = "200" ] && break
  sleep 2
done
if [ "${code:-}" != "200" ]; then
  echo "  ✗ Jenkins ne répond pas encore sur le port $PORT : docker logs conformite-jenkins | tail -40"
  exit 1
fi
echo
echo "  ✓ Jenkins prêt : http://localhost:$PORT  (depuis le réseau : http://IP-du-serveur:$PORT)"
echo "    compte      : admin"
echo "    mot de passe: dans $PWD/.env (JENKINS_ADMIN_PASSWORD) — affiché par l'outil Windows « 11 - Jenkins »"
echo "    tâche       : conformite-dm (branche $JENKINS_BRANCHE) — premier build dans une minute"
