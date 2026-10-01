#!/usr/bin/env bash
# Vérifie de bout en bout une installation (à lancer après installer_serveur.sh
# ou mettre_a_jour.sh). Ne modifie rien. Rapport sans aucun secret, à
# renvoyer à Taha.
#
#   cd /opt/conformite && sudo bash scripts/verifier_installation.sh
set -uo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" -eq 0 ] || { echo "Lancer avec sudo."; exit 1; }
[ -f .env ] && { set -a; . ./.env; set +a; }
PORT=${INTERFACE_PORT:-80}
[ -x /usr/lib/wsl/lib/nvidia-smi ] && PATH="$PATH:/usr/lib/wsl/lib"  # GPU vu depuis WSL2
ECHECS=0
ok()    { printf '  \033[32m✓\033[0m %s\n' "$*"; }
ko()    { printf '  \033[31m✗\033[0m %s\n' "$*"; ECHECS=$((ECHECS+1)); }
alerte(){ printf '  \033[33m!\033[0m %s\n' "$*"; }
verifier() { local libelle=$1; shift; if "$@" >/dev/null 2>&1; then ok "$libelle"; else ko "$libelle"; fi; }

echo "== Vérification de l'installation — $(date '+%F %T') — version $(git rev-parse --short HEAD 2>/dev/null || echo '?')"

echo "-- Services"
for c in conformite-postgres conformite-qdrant conformite-api conformite-interface; do
  verifier "conteneur $c démarré" test "$(docker inspect -f '{{.State.Running}}' $c 2>/dev/null)" = true
done
verifier "Ollama démarré (service système)" curl -sf http://127.0.0.1:11434/api/version
SANTE=$(curl -s -m 10 http://127.0.0.1:8000/health || true)
verifier "API : PostgreSQL, Qdrant et Ollama joignables" grep -q '"postgres":true,"qdrant":true,"ollama":true' <<<"$SANTE"
verifier "API : clé d'accès activée" grep -q '"authentification":"cle_api"' <<<"$SANTE"
verifier "tableau de bord : http://127.0.0.1:$PORT répond" curl -sf -o /dev/null "http://127.0.0.1:$PORT/"
verifier "tableau de bord : relais /api vers l'API" curl -sf -o /dev/null "http://127.0.0.1:$PORT/api/health"
verifier "sécurité : requête sans clé refusée (401)" test "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/api/dossiers)" = 401
if [ -n "${API_KEY:-}" ]; then
  verifier "sécurité : requête avec la clé acceptée" test "$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: $API_KEY" http://127.0.0.1:$PORT/api/dossiers)" = 200
fi

echo "-- Modèles et index"
MODELES=$(ollama list 2>/dev/null | awk 'NR>1 {print $1}' | tr '\n' ' ')
verifier "Mistral installé" grep -q mistral <<<"$MODELES"
verifier "bge-m3 installé" grep -q bge-m3 <<<"$MODELES"
POINTS=$(curl -s http://127.0.0.1:6333/collections/dossiers_reference | grep -o '"points_count":[0-9]*' | tr -dc '0-9')
if [ "${POINTS:-0}" -ge 596 ]; then ok "textes réglementaires indexés : $POINTS extraits"; else ko "textes réglementaires indexés : ${POINTS:-0} extraits (596 attendus)"; fi
verifier "bge-m3 répond (recherche)" curl -sf -m 120 http://127.0.0.1:11434/api/embed -d '{"model":"bge-m3","input":"certificat CE"}'
echo "  … test de rédaction par Mistral (jusqu'à 10 min sur CPU au premier appel : chargement du modèle)"
DEBUT=$(date +%s)
REPONSE=$(curl -s -m 600 http://127.0.0.1:11434/api/generate \
  -d '{"model":"mistral","prompt":"Réponds uniquement par le mot : conforme","stream":false,"options":{"num_predict":10}}' || true)
if grep -qi conforme <<<"$REPONSE"; then ok "Mistral rédige ($(( $(date +%s) - DEBUT )) s)"; else ko "Mistral ne répond pas correctement : ${REPONSE:0:150}"; fi
verifier "API → Mistral depuis le conteneur (host.docker.internal)" docker exec conformite-api python3 -c \
  "import urllib.request; urllib.request.urlopen('http://host.docker.internal:11434/api/version', timeout=10)"

echo "-- Modèles de rédaction et profil de l'entreprise"
if [ -f config/entreprise.yaml ] && ! grep -q "NOM DE L'ÉTABLISSEMENT" config/entreprise.yaml; then
  ok "profil de l'entreprise rempli (config/entreprise.yaml)"
else
  alerte "profil de l'entreprise absent ou non rempli : les courriers auront [À COMPLÉTER] à la place des coordonnées (fiche §5 bis)"
fi
MODELES_IDX=$(curl -s http://127.0.0.1:6333/collections/modeles_dossiers | grep -o '"points_count":[0-9]*' | tr -dc '0-9')
if [ "${MODELES_IDX:-0}" -gt 0 ]; then ok "modèles de rédaction indexés : $MODELES_IDX pièce(s) de dossiers acceptés"
else alerte "aucun modèle de rédaction : ajouter les dossiers acceptés (fiche §5 bis) puis sudo bash scripts/indexer_modeles.sh"; fi

echo "-- Lecture des documents scannés (OCR)"
LANGUES=$(docker exec conformite-api tesseract --list-langs 2>/dev/null | tr '\n' ' ')
for l in fra eng ara; do verifier "Tesseract : langue $l" grep -qw $l <<<"$LANGUES"; done

echo "-- Sécurité réseau"
for p in 8000 5432 6333 11434; do
  if ss -ltn | awk '{print $4}' | grep -E "(^|:)$p$" | grep -qvE '^(127\.0\.0\.1|\[::1\]):'; then
    [ "$p" = 11434 ] && alerte "port 11434 (Ollama) ouvert sur toutes les interfaces : vérifier qu'il est bloqué au pare-feu (ufw status)" \
                     || ko "port $p accessible depuis le réseau (devrait être réservé au serveur)"
  else ok "port $p réservé au serveur"; fi
done
verifier "fichier .env protégé (lisible par root seulement)" test "$(stat -c %a .env 2>/dev/null)" = 600

echo "-- Exploitation"
crontab -l 2>/dev/null | grep -q sauvegarder.sh && ok "sauvegarde automatique programmée" \
  || alerte "sauvegarde automatique non programmée (fiche §9 : sudo crontab -e)"
DISQUE=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
[ "$DISQUE" -ge 10 ] && ok "disque libre : ${DISQUE} Go" || alerte "disque libre : ${DISQUE} Go seulement"
nvidia-smi >/dev/null 2>&1 && ok "GPU : $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)" \
  || alerte "pas de GPU : 2 à 5 min par pièce rédigée"

echo
if [ "$ECHECS" -eq 0 ]; then
  ADRESSE=$(hostname -I | awk '{print $1}')
  grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null && ADRESSE="IP-du-serveur-Windows"  # WSL2 : relais Windows
  echo "RÉSULTAT : installation complète et fonctionnelle. Adresse : http://$ADRESSE$( [ "$PORT" != 80 ] && echo ":$PORT")"
else
  echo "RÉSULTAT : $ECHECS point(s) en échec (✗) — envoyer ce rapport à Taha (il ne contient aucun secret)."
  exit 1
fi
