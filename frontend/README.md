# Frontend — tableau de bord de suivi et de validation

Application React (Vite + TypeScript) qui consomme l'API de `src/api.py` :
liste des dossiers, création (avec aperçu des pièces décidées par le moteur
de règles), lancement de la rédaction des pièces à rédiger, suivi en temps
réel, téléchargement des projets DOCX, validation / rejet nominatifs,
journal d'audit. Aucun dépôt automatique.

## Configuration

L'adresse du backend vient **uniquement** de `VITE_API_URL`, lue au build :

```bash
cp .env.example .env.local          # VITE_API_URL=http://localhost:8000
npm install
npm run dev                         # http://localhost:5173
```

Sans `VITE_API_URL`, l'application affiche « Configuration manquante »
(aucune adresse par défaut). Si le backend ne répond pas, elle reste
utilisable en lecture de l'interface mais affiche « Backend injoignable ».

La clé d'API (si le backend en exige une) n'est jamais intégrée au build :
chaque utilisateur la saisit à la connexion.

## Vérifications

```bash
npx tsc -b && npm run lint && npm run build
# Parcours complet dans Chromium (backend + frontend démarrés) :
../.venv/bin/python e2e/parcours.py http://localhost:4173
```

Déploiement sur Vercel : voir `../DEPLOIEMENT.md`.
