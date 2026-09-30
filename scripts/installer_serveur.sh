#!/usr/bin/env bash
# Installation complète du backend sur le serveur de l'entreprise (Ubuntu/Debian).
#
# Mode d'emploi détaillé pour l'administrateur : INSTALLATION_SERVEUR.md
#
#   sudo git clone --branch claude/complete-pipeline-setup-ikdsp0 https://github.com/tahawin1/tahhh.git /opt/conformite
#   cd /opt/conformite
#   sudo bash scripts/installer_serveur.sh --verifier     # 1) diagnostic seul, ne modifie rien
#   sudo NGROK_AUTHTOKEN=... NGROK_URL=xxx.ngrok-free.app bash scripts/installer_serveur.sh
#                                                          # 2) installation (ngrok facultatif)
#
# Étapes : diagnostic -> Docker -> Ollama + Mistral + bge-m3 -> secrets (.env)
# -> PostgreSQL + Qdrant + API (+ ngrok) -> contrôle de santé -> indexation
# des textes réglementaires (une fois, ~30 min sur CPU). Relançable sans
# risque : chaque étape déjà faite est sautée.
set -euo pipefail
cd "$(dirname "$0")/.."

VERIFIER_SEULEMENT=0
[ "${1:-}" = "--verifier" ] && VERIFIER_SEULEMENT=1

ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
alerte(){ printf '  \033[33m!\033[0m %s\n' "$*"; }
echec() { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }
titre() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# ------------------------------------------------------------------ 1. diagnostic
titre "1. Diagnostic du serveur"
[ "$(id -u)" -eq 0 ] || echec "Lancer avec sudo (installation de Docker/Ollama, services système)."
command -v curl >/dev/null || { [ "$VERIFIER_SEULEMENT" -eq 0 ] && apt-get update -qq && apt-get install -y -qq curl openssl ca-certificates; } \
  || echec "curl absent : sudo apt install -y curl openssl ca-certificates"
. /etc/os-release 2>/dev/null && ok "Système : ${PRETTY_NAME:-inconnu}"
CPU=$(nproc); RAM_GO=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
DISQUE_GO=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
ok "Processeurs : $CPU  |  Mémoire : ${RAM_GO} Go  |  Disque libre : ${DISQUE_GO} Go"
[ "$RAM_GO" -ge 12 ] || alerte "Moins de 12 Go de mémoire : Mistral 7B risque d'être très lent ou de ne pas démarrer."
[ "$DISQUE_GO" -ge 40 ] || alerte "Moins de 40 Go libres : images Docker + modèles (~6 Go) + index peuvent manquer de place."
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  ok "GPU NVIDIA : $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1) (Mistral ~20x plus rapide)"
else
  alerte "Pas de GPU NVIDIA détecté : Mistral tournera sur CPU (~4 min par pièce rédigée)."
fi
for hote in https://ollama.com https://registry-1.docker.io https://pypi.org https://registry.npmjs.org https://github.com; do
  if curl -s -o /dev/null -m 10 "$hote"; then ok "Accès Internet : $hote"; else alerte "Pas d'accès à $hote (proxy ou pare-feu de l'entreprise ?)"; fi
done
command -v docker >/dev/null && ok "Docker présent : $(docker --version)" || alerte "Docker absent (sera installé)"
command -v ollama >/dev/null && ok "Ollama présent" || alerte "Ollama absent (sera installé)"
[ "$VERIFIER_SEULEMENT" -eq 1 ] && { echo; echo "Diagnostic terminé (rien n'a été modifié)."; exit 0; }

# ------------------------------------------------------------------ 2. Docker
titre "2. Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi
docker compose version >/dev/null 2>&1 || echec "Le plugin « docker compose » est absent : installer docker-compose-plugin."
docker buildx version >/dev/null 2>&1 || echec "Le plugin « docker buildx » est absent (Docker trop ancien) : installer docker-buildx-plugin."
ok "Docker prêt"

# ------------------------------------------------------------------ 3. Ollama + modèles
titre "3. Ollama, Mistral et bge-m3"
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
# Ollama doit être joignable depuis les conteneurs (host.docker.internal)
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/conformite.conf <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_LOAD_TIMEOUT=20m"
Environment="OLLAMA_KEEP_ALIVE=2h"
EOF
systemctl daemon-reload && systemctl enable ollama >/dev/null 2>&1 && systemctl restart ollama
for i in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:11434/api/version && break; sleep 1; done
curl -s -o /dev/null http://127.0.0.1:11434/api/version || echec "Ollama ne répond pas (journalctl -u ollama)."
ollama pull mistral
ollama pull bge-m3
ok "Modèles : $(ollama list | awk 'NR>1 {print $1}' | tr '\n' ' ')"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  # D'abord autoriser les conteneurs Docker (l'API doit joindre Ollama), puis fermer le reste
  ufw allow from 172.16.0.0/12 to any port 11434 proto tcp >/dev/null || true
  ufw deny 11434/tcp >/dev/null || true
  ufw allow "${INTERFACE_PORT:-80}"/tcp >/dev/null || true
  ok "Pare-feu : Ollama (11434) réservé à Docker ; tableau de bord (port ${INTERFACE_PORT:-80}) ouvert"
else
  alerte "Vérifier que le port 11434 (Ollama) n'est pas accessible depuis l'extérieur du serveur."
fi

# ------------------------------------------------------------------ 4. secrets
titre "4. Secrets (.env)"
if [ ! -f .env ]; then
  {
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
    echo "API_KEY=$(openssl rand -hex 32)"
    echo "CORS_ORIGINS=${CORS_ORIGINS:-*}"
    [ -n "${INTERFACE_PORT:-}" ] && echo "INTERFACE_PORT=${INTERFACE_PORT}"  # conservé pour les mises à jour
    [ -n "${NGROK_AUTHTOKEN:-}" ] && echo "NGROK_AUTHTOKEN=${NGROK_AUTHTOKEN}"
    [ -n "${NGROK_URL:-}" ] && echo "NGROK_URL=${NGROK_URL}"
  } > .env
  chmod 600 .env
  ok ".env créé (mot de passe et clé d'API générés, lisible par root seulement)"
else
  ok ".env existant conservé"
fi
set -a; . ./.env; set +a

# ------------------------------------------------------------------ 5. services
titre "5. PostgreSQL, Qdrant, API, tableau de bord$( [ -n "${NGROK_AUTHTOKEN:-}" ] && echo ' et tunnel ngrok')"
PROFILS=(--profile api --profile interface)
[ -n "${NGROK_AUTHTOKEN:-}" ] && [ -n "${NGROK_URL:-}" ] && PROFILS+=(--profile ngrok)
docker compose "${PROFILS[@]}" up -d --build
for i in $(seq 1 60); do curl -s http://127.0.0.1:8000/health | grep -q '"statut":"ok"' && break; sleep 2; done
SANTE=$(curl -s http://127.0.0.1:8000/health || true)
echo "  $SANTE"
echo "$SANTE" | grep -q '"postgres":true' || echec "PostgreSQL injoignable par l'API (docker compose logs api)."
echo "$SANTE" | grep -q '"qdrant":true'   || echec "Qdrant injoignable par l'API (docker compose logs qdrant)."
echo "$SANTE" | grep -q '"ollama":true'   || echec "Ollama injoignable depuis le conteneur de l'API (pare-feu entre Docker et l'hôte ?)."
ok "API en ligne sur http://127.0.0.1:8000 (documentation : /docs)"
for i in $(seq 1 30); do curl -s http://127.0.0.1:${INTERFACE_PORT:-80}/api/health | grep -q '"statut":"ok"' && break; sleep 2; done
curl -s http://127.0.0.1:${INTERFACE_PORT:-80}/api/health | grep -q '"statut":"ok"' \
  && ok "Tableau de bord en ligne sur le port ${INTERFACE_PORT:-80}" \
  || echec "Tableau de bord injoignable (docker compose logs interface)."

# ------------------------------------------------------------------ 6. indexation
titre "6. Indexation des textes réglementaires"
POINTS=$(curl -s http://127.0.0.1:6333/collections/dossiers_reference | grep -o '"points_count":[0-9]*' | tr -dc '0-9' || true)
if [ "${POINTS:-0}" -gt 0 ]; then
  ok "Déjà indexé : $POINTS extraits"
else
  echo "  Indexation en cours (OCR des scans marocains + embeddings ; ~30 min sur CPU)…"
  docker compose --profile api run --rm api bash scripts/indexer_tout.sh
  POINTS=$(curl -s http://127.0.0.1:6333/collections/dossiers_reference | grep -o '"points_count":[0-9]*' | tr -dc '0-9')
  ok "Indexé : $POINTS extraits (596 attendus)"
fi

# ------------------------------------------------------------------ résumé
titre "Terminé"
IP_SERVEUR=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "  Tableau de bord   : http://${IP_SERVEUR:-IP-du-serveur}$( [ "${INTERFACE_PORT:-80}" != 80 ] && echo ":${INTERFACE_PORT}")   (réseau de l'entreprise)"
echo "  API locale        : http://127.0.0.1:8000  (clé d'API dans .env : API_KEY)"
if [ -n "${NGROK_URL:-}" ]; then
  echo "  Adresse publique  : https://${NGROK_URL}   (vérifier : curl https://${NGROK_URL}/health)"
  echo "  Sur Vercel        : VITE_API_URL = https://${NGROK_URL}  puis Redeploy"
else
  echo "  Pas de tunnel : relancer avec NGROK_AUTHTOKEN et NGROK_URL pour un accès depuis Vercel."
fi
echo "  Se connecter au tableau de bord avec la clé API_KEY (sudo grep API_KEY .env)."
echo
echo "  Étape suivante : vérification complète (≈10 min, ne modifie rien) :"
echo "    sudo bash scripts/verifier_installation.sh"
