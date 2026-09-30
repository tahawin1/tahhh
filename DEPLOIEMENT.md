# Déploiement — serveur de l'entreprise + tunnel + Vercel

> **Pour l'administrateur du serveur : suivre [INSTALLATION_SERVEUR.md](INSTALLATION_SERVEUR.md)**
> (un script installe tout : Docker, Ollama + Mistral, base, API et tableau de
> bord servi par nginx sur `http://IP-du-serveur`, sans tunnel ni Vercel).
> Ce document-ci décrit en plus l'accès depuis l'extérieur (ngrok + Vercel).

```
 Navigateur (n'importe où)
        │  https://<projet>.vercel.app         ← frontend React (Vercel, statique)
        │
        │  appels API (fetch) vers VITE_API_URL
        ▼
 https://<nom>.ngrok-free.app                  ← tunnel ngrok (sortant, aucun port ouvert)
        │
 ┌──────┴──────────── serveur de l'entreprise ────────────────────────┐
 │  ngrok ───────► api:8000  API FastAPI (docker, profil api)         │
 │                    ├── PostgreSQL  (dossiers, validations, journal) │
 │                    ├── Qdrant      (textes réglementaires indexés)  │
 │                    └── Ollama      (Mistral + bge-m3, sur l'hôte)   │
 └────────────────────────────────────────────────────────────────────┘
```

Vercel n'héberge **que** le frontend. Tout le reste tourne sur le serveur
de l'entreprise. **Si le serveur ou le tunnel est arrêté, le frontend
reste accessible mais ne peut plus rien charger** (il affiche « Backend
injoignable »).

## 1. Serveur de l'entreprise

**Méthode rapide (recommandée)** : un seul script fait tout, étape par étape,
et s'arrête avec un message clair si quelque chose manque.

```bash
git clone https://github.com/tahawin1/tahhh.git conformite && cd conformite
git checkout claude/complete-pipeline-setup-ikdsp0
sudo bash scripts/installer_serveur.sh --verifier        # diagnostic seul
sudo NGROK_AUTHTOKEN=<authtoken> NGROK_URL=<domaine>.ngrok-free.app \
     bash scripts/installer_serveur.sh                  # installation
```

Détail des étapes, si on préfère les faire à la main :

Prérequis : Docker + Docker Compose, Git, et idéalement un GPU (sur CPU
seul, Mistral 7B met ~4 minutes par pièce rédigée).

```bash
git clone <ce dépôt> conformite && cd conformite

# Secrets — fichier .env à la racine, jamais versionné (déjà dans .gitignore)
cat > .env <<EOF
POSTGRES_PASSWORD=$(openssl rand -hex 16)
API_KEY=$(openssl rand -hex 32)
CORS_ORIGINS=https://<projet>.vercel.app
EOF
chmod 600 .env

# Ollama sur l'hôte, joignable depuis Docker (bloquer le port 11434 au pare-feu)
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl edit ollama   # ajouter : [Service]  Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
ollama pull mistral
ollama pull bge-m3

# PostgreSQL + Qdrant + API (l'API refuse de démarrer sans API_KEY)
docker compose --profile api up -d --build
curl http://127.0.0.1:8000/health    # postgres, qdrant, ollama : true

# Indexation des textes réglementaires (une fois ; ~30 min sur CPU)
docker compose --profile api run --rm api bash scripts/indexer_tout.sh
```

Les ports de PostgreSQL, Qdrant et de l'API ne sont liés qu'à
`127.0.0.1` : rien n'est exposé sur le réseau, l'accès extérieur passe
uniquement par le tunnel.

## 2. Tunnel ngrok (choix retenu pour l'instant)

1. Créer un compte gratuit sur https://dashboard.ngrok.com, récupérer
   l'**authtoken** (*Your Authtoken*) et réserver le **domaine statique
   gratuit** (*Domains*, ex. `conformite-xxxx.ngrok-free.app`) : l'adresse
   ne changera plus, `VITE_API_URL` est saisie une seule fois sur Vercel.
2. Ajouter au fichier `.env` du serveur :
   ```bash
   NGROK_AUTHTOKEN=<authtoken>
   NGROK_URL=conformite-xxxx.ngrok-free.app
   ```
3. Démarrer l'API **et** le tunnel :
   ```bash
   docker compose --profile api --profile ngrok up -d --build
   curl https://conformite-xxxx.ngrok-free.app/health
   ```

Le frontend envoie l'en-tête `ngrok-skip-browser-warning` à chaque appel :
la page d'avertissement de l'offre gratuite ne bloque donc pas le tableau
de bord. Limites de l'offre gratuite : quota mensuel de requêtes et de
bande passante — largement suffisant pour suivre et partager l'avancement,
pas pour une exploitation en production.

## 2 bis. Alternative à terme : Cloudflare Tunnel

Pourquoi y passer à terme (plutôt que ngrok) :
- adresse sur **votre propre domaine** (`api.votre-domaine`) ;
- **Cloudflare Access** (gratuit jusqu'à 50 utilisateurs) : on peut exiger
  une connexion (e-mail de l'entreprise) avant même d'atteindre l'API ;
- pas de quota de requêtes ni de page d'avertissement ;
- connexion **sortante** depuis le serveur : aucun port à ouvrir au pare-feu.

Condition : un nom de domaine géré par Cloudflare (DNS). Sans domaine,
ngrok (section 2) reste la solution.

```bash
# Sur le serveur
cloudflared tunnel login
cloudflared tunnel create conformite-api
cloudflared tunnel route dns conformite-api api.<votre-domaine>
cat > ~/.cloudflared/config.yml <<EOF
tunnel: conformite-api
credentials-file: /root/.cloudflared/<ID-du-tunnel>.json
ingress:
  - hostname: api.<votre-domaine>
    service: http://127.0.0.1:8000
  - service: http_status:404
EOF
sudo cloudflared service install    # démarre avec le serveur
curl https://api.<votre-domaine>/health
```

La génération est asynchrone (l'API répond en quelques millisecondes et
rédige en tâche de fond) : les limites de durée de requête des tunnels
(100 s chez Cloudflare) ne sont donc pas un problème.

## 3. Frontend sur Vercel

**Pour montrer l'interface sans backend** (mode démonstration, données
d'exemple réelles embarquées) : importer le dépôt en ne gardant que
l'application Vite (*l'extrémité avant*, dossier `frontend`) — ne pas
importer l'application FastAPI : Vercel ne peut pas faire tourner le
backend (PostgreSQL, Qdrant et Mistral doivent tourner en permanence) — et
définir `VITE_API_URL = demo`. Pour passer au vrai backend plus tard, il
suffit de remplacer cette valeur par l'adresse du tunnel et de redéployer.

Dans Vercel → *Add New Project* → importer ce dépôt GitHub :
- **Root Directory** : `frontend`
- **Framework** : Vite (détecté ; `frontend/vercel.json`)
- **Environment Variables** : `VITE_API_URL = https://conformite-xxxx.ngrok-free.app`

Ou en ligne de commande (avec un jeton `VERCEL_TOKEN`) :

```bash
cd frontend
npx vercel link --yes
npx vercel env add VITE_API_URL production    # saisir https://conformite-xxxx.ngrok-free.app
npx vercel deploy --prod
```

`VITE_API_URL` est lue **au moment du build** : après l'avoir modifiée,
redéployer. Puis mettre l'URL Vercel obtenue dans `CORS_ORIGINS` (`.env`
du serveur) et `docker compose --profile api --profile ngrok up -d`.

La clé d'API n'est jamais mise dans Vercel : chaque utilisateur la saisit
à la connexion au tableau de bord.

## 4. Vérification réelle après déploiement

```bash
# Depuis n'importe quelle machine avec Python + Playwright :
python frontend/e2e/parcours.py https://<projet>.vercel.app
```

Le script ouvre le tableau de bord dans Chromium, se connecte, vérifie que
la liste des dossiers et l'aperçu des pièces requises sont chargés depuis
le backend, crée un dossier de test et valide une pièce. Si le backend
exige une clé, définir `E2E_API_KEY`.
