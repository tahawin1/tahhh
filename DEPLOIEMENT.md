# Déploiement — serveur de l'entreprise + tunnel + Vercel

```
 Navigateur (n'importe où)
        │  https://<projet>.vercel.app         ← frontend React (Vercel, statique)
        │
        │  appels API (fetch) vers VITE_API_URL
        ▼
 https://api.<votre-domaine>                   ← Cloudflare Tunnel (sortant, aucun port ouvert)
        │
 ┌──────┴──────────── serveur de l'entreprise ────────────────────────┐
 │  cloudflared ──► 127.0.0.1:8000  API FastAPI (docker, profil api)   │
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

## 2. Tunnel : Cloudflare Tunnel (recommandé)

Pourquoi Cloudflare plutôt que ngrok :
- **adresse fixe** (`api.votre-domaine`) : `VITE_API_URL` est saisie une
  fois pour toutes sur Vercel ;
- **Cloudflare Access** (gratuit jusqu'à 50 utilisateurs) : on peut exiger
  une connexion (e-mail de l'entreprise) avant même d'atteindre l'API ;
- pas de quota de requêtes ni de page d'avertissement ;
- connexion **sortante** depuis le serveur : aucun port à ouvrir au pare-feu.

Condition : un nom de domaine géré par Cloudflare (DNS). Sans domaine,
ngrok (`ngrok http 8000 --url <domaine-statique-gratuit>.ngrok-free.app`)
dépanne, mais sa page d'avertissement gêne les appels du navigateur.

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
rédige en tâche de fond) : la limite de 100 s de Cloudflare par requête
n'est donc pas un problème.

## 3. Frontend sur Vercel

Dans Vercel → *Add New Project* → importer ce dépôt GitHub :
- **Root Directory** : `frontend`
- **Framework** : Vite (détecté ; `frontend/vercel.json`)
- **Environment Variables** : `VITE_API_URL = https://api.<votre-domaine>`

Ou en ligne de commande (avec un jeton `VERCEL_TOKEN`) :

```bash
cd frontend
npx vercel link --yes
npx vercel env add VITE_API_URL production    # saisir https://api.<votre-domaine>
npx vercel deploy --prod
```

`VITE_API_URL` est lue **au moment du build** : après l'avoir modifiée,
redéployer. Puis mettre l'URL Vercel obtenue dans `CORS_ORIGINS` (`.env`
du serveur) et `docker compose --profile api up -d`.

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
