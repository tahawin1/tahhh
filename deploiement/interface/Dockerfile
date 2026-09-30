# Tableau de bord servi par le serveur de l'entreprise (accès depuis le
# réseau interne : http://IP-du-serveur). nginx sert l'interface et relaie
# /api vers le conteneur de l'API, qui n'est jamais exposé directement.
FROM node:22-alpine AS construction
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# même origine que la page : l'API est jointe via /api (voir nginx.conf)
RUN VITE_API_URL=/api npm run build

FROM nginx:1.27-alpine
COPY deploiement/interface/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=construction /frontend/dist /usr/share/nginx/html
