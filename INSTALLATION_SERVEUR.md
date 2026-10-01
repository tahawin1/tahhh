# Fiche d'installation — serveur de l'entreprise

**Destinataire :** l'administrateur du serveur.
**Objet :** installer en une fois l'outil de conformité des dispositifs médicaux (tableau de bord + agent Mistral), le vérifier et l'exploiter au quotidien.
**Durée :** environ 1 h, dont 45 min d'attente (téléchargements, indexation). Aucune compétence en IA n'est nécessaire.

---

## 0. En bref

Un seul script fait tout : `scripts/installer_serveur.sh`.

| Étape du script | Ce qu'elle fait | Durée indicative |
|---|---|---|
| 1. Diagnostic | Vérifie système, mémoire, disque, GPU, accès Internet | 10 s |
| 2. Docker | Installe Docker si absent | 2–5 min |
| 3. Ollama + modèles | Installe Ollama (moteur IA local), télécharge **Mistral 7B** (4,1 Go) et **bge-m3** (1,2 Go) | 5–20 min selon le débit |
| 4. Secrets | Crée `.env` : mot de passe PostgreSQL et clé d'accès générés au hasard | 1 s |
| 5. Services | Construit et démarre PostgreSQL, Qdrant, l'API et le tableau de bord | 5–10 min |
| 6. Indexation | Lit les textes réglementaires (Maroc, Chine, Inde) et les range dans la base de recherche | ~30 min sur CPU (une seule fois) |

Le script **peut être relancé sans risque** : ce qui est déjà fait est sauté (la clé et les mots de passe existants sont conservés).

À la fin, les utilisateurs ouvrent **`http://IP-du-serveur`** depuis leur poste, sur le réseau de l'entreprise.

---

## 0 bis. Serveur Windows : à lire en premier

L'outil (Docker, PostgreSQL, Qdrant, Mistral) fonctionne sous Linux. Sur un serveur Windows, il tourne dans **Ubuntu sous WSL2**, le sous-système Linux fourni gratuitement par Microsoft. Docker Desktop n'est pas utilisé : il n'est pas pris en charge sur Windows Server et il est payant pour les grandes entreprises.

| Version de Windows | Méthode |
|---|---|
| Windows Server 2022 ou 2025, Windows 10 (2004 et plus) ou 11 | **Script Windows ci-dessous** (WSL2) |
| Windows Server 2019 ou plus ancien | WSL2 indisponible : créer une **machine virtuelle Ubuntu 24.04 dans Hyper-V** (16 Go de mémoire, 80 Go de disque, carte réseau externe), puis suivre cette fiche **à partir du §3**, dans la machine virtuelle |

Si le serveur Windows est lui-même une machine virtuelle (VMware, Hyper-V…), la **virtualisation imbriquée** doit être activée sur l'hôte. Sinon WSL2 ne démarre pas.

**Installation sur Windows (Server 2022/2025, 10, 11), en une commande :**

1. Copier `conformite-serveur.zip` dans `C:\conformite-install\`, puis faire clic droit → **Extraire tout** dans ce même dossier.
2. Ouvrir **PowerShell en tant qu'administrateur** et lancer :

```powershell
powershell -ExecutionPolicy Bypass -File C:\conformite-install\conformite-serveur\conformite\deploiement\windows\installer_windows.ps1 -Zip C:\conformite-install\conformite-serveur.zip
```

Le dossier extrait peut s'appeler `conformite-serveur\conformite` ou `conformite` : adaptez le chemin. Si le port 80 est déjà pris (IIS), ajoutez `-Port 8080` à la fin de la commande.

Ce que fait le script (relançable : ce qui est déjà fait est sauté) :
- **WSL2 absent** : il l'installe, puis demande de **redémarrer le serveur et de relancer la même commande**.
- **Ubuntu** : une invite demande un nom d'utilisateur et un mot de passe Ubuntu. Choisissez-les, notez-les, puis tapez `exit`.
- **Réglages** : il réserve 75 % de la mémoire à Ubuntu (pour Mistral) et active les services (systemd).
- **Diagnostic** (§4) : il le lance, puis **demande de confirmer** avant l'installation complète (§5, ≈ 1 h). Il s'agit du même script que pour un serveur Ubuntu.
- **Réseau et démarrage** :
  - il ouvre le port au pare-feu Windows ;
  - il crée la tâche planifiée **ConformiteDM-Demarrage**. Elle relance Ubuntu, Docker et Mistral à chaque démarrage de Windows et relaie le port vers Ubuntu. Elle **demande le mot de passe de votre compte Windows**.
- **Vérification complète** (§6) : il la lance, puis affiche l'adresse du tableau de bord.

**Ensuite, sur un serveur Windows :**
- Toutes les commandes `bash`/`sudo` de cette fiche (§6 à §11) se tapent dans le **terminal Ubuntu**. On l'ouvre depuis PowerShell avec `wsl -d Ubuntu-24.04 -u root`, puis `cd /opt/conformite`. `sudo` y est facultatif : on est déjà administrateur.
- Le profil et les dossiers acceptés (§5 bis) se déposent aussi depuis l'**Explorateur Windows**, à l'adresse `\\wsl.localhost\Ubuntu-24.04\opt\conformite\data\dossiers_valides`. Lancez ensuite `bash scripts/indexer_modeles.sh` dans le terminal Ubuntu.
- Les fichiers de Windows sont visibles dans Ubuntu sous `/mnt/c/…`. Exemple de mise à jour par fichier : `bash scripts/mettre_a_jour.sh /mnt/c/conformite-install/maj.bundle`.
- Pour copier les sauvegardes hors du serveur, passez par Windows : `cp -r /var/backups/conformite /mnt/c/Sauvegardes/`.
- Le journal du démarrage automatique se trouve dans `C:\ProgramData\ConformiteDM\demarrage.log`.

---

## 1. Mistral doit-il être sur le serveur ? Oui.

L'agent qui **rédige** les pièces (lettre de demande, fiche signalétique…) et qui **lit** les documents envoyés par les fournisseurs (certificats CE, ISO 13485…) est **Mistral**. Il tourne **sur le serveur lui-même**, via Ollama. Le script l'installe automatiquement.

- **Mistral 7B** rédige et lit les documents.
- **bge-m3** sert à retrouver les passages pertinents des textes réglementaires et des dossiers déjà acceptés.
- **Aucun document ne quitte le serveur** : les modèles sont téléchargés une fois, puis tout fonctionne en local, même sans Internet.
- Sans Mistral, le tableau de bord s'ouvre, mais la rédaction (« Lancer la rédaction ») et la lecture des documents déposés affichent une erreur claire (jamais un faux document).

La liste des pièces exigées n'est **pas** décidée par Mistral : elle vient de règles écrites (`rules/*.yaml`). Aucun dépôt n'est fait automatiquement : chaque pièce est validée par une personne nommée.

---

## 2. Prérequis du serveur

| | Minimum | Recommandé |
|---|---|---|
| Système | Ubuntu 22.04 ou 24.04 LTS (64 bits) ; Debian 12 fonctionne ; **Windows Server 2022/2025 ou Windows 10/11 via WSL2 (§0 bis)** | Ubuntu 24.04 LTS |
| Processeur | 4 cœurs | 8 cœurs ou plus |
| Mémoire | 16 Go (12 Go absolu minimum) | 32 Go |
| Disque libre | 40 Go (60 Go sur C: pour Windows) | 100 Go (dossiers, sauvegardes) |
| GPU | aucun (fonctionne sur CPU) | NVIDIA ≥ 8 Go de mémoire vidéo |
| Droits | un compte avec `sudo` | |

**Vitesse de Mistral.** Sur CPU seul, une pièce rédigée prend **3 à 5 minutes** et la lecture d'un certificat 1 à 3 minutes. C'est utilisable pour un pilote. Avec un GPU NVIDIA, comptez 10 à 20 secondes. S'il y a un GPU, **installez le pilote NVIDIA avant le script** (la commande `nvidia-smi` doit afficher la carte) ; Ollama l'utilise alors tout seul.

**Accès Internet sortant (HTTPS, port 443) pendant l'installation**, vers :

| Site | Pour |
|---|---|
| `ollama.com`, `registry.ollama.ai` (et le stockage vers lequel ils redirigent) | Ollama et les modèles Mistral / bge-m3 |
| `get.docker.com`, `download.docker.com` | Docker |
| `registry-1.docker.io`, `production.cloudflare.docker.com` | images PostgreSQL, Qdrant, Python, Node, nginx |
| `pypi.org`, `files.pythonhosted.org` | bibliothèques Python de l'API |
| `registry.npmjs.org` | construction du tableau de bord |
| `deb.debian.org` | Tesseract (lecture des scans) dans l'image de l'API |
| `github.com` | le code |

Après l'installation, Internet n'est plus nécessaire, sauf pour les mises à jour et le tunnel ngrok facultatif.

**Ports.** Seul le port **80** (le tableau de bord) doit être ouvert au réseau interne. Tout le reste est fermé ou limité au serveur lui-même :

| Port | Service | Accessible depuis |
|---|---|---|
| 80 | Tableau de bord | réseau interne |
| 8000 | API | le serveur seul |
| 5432 | PostgreSQL | le serveur seul |
| 6333 / 6334 | Qdrant | le serveur seul |
| 11434 | Ollama | le serveur et ses conteneurs Docker ; bloqué au pare-feu pour le reste |

---

## 3. Étape 1 — Récupérer le code

**Méthode A : le fichier `conformite-serveur.zip` remis par Taha** (recommandée, aucun compte GitHub nécessaire). Copiez-le sur le serveur (clé USB, partage réseau ou `scp conformite-serveur.zip admin@serveur:/tmp/`), puis :

```bash
sudo apt update && sudo apt install -y git curl unzip
sudo unzip /tmp/conformite-serveur.zip -d /opt      # crée /opt/conformite
cd /opt/conformite
git log -1 --oneline                                # affiche la version installée
```

**Méthode B : directement depuis GitHub** (si le serveur y a accès) :

```bash
sudo apt update && sudo apt install -y git curl
sudo git clone --branch claude/complete-pipeline-setup-ikdsp0 \
     https://github.com/tahawin1/tahhh.git /opt/conformite
cd /opt/conformite
```

Si GitHub demande un identifiant (dépôt privé) : le nom d'utilisateur GitHub, puis, à la place du mot de passe, un *jeton d'accès* en lecture seule fourni par Taha, de vive voix ou par le gestionnaire de mots de passe, jamais par e-mail.

Dans les deux cas, le code est dans `/opt/conformite` avec son historique de versions, ce qui permet les mises à jour du §10. Toutes les commandes suivantes se lancent **depuis ce dossier**. **Ne modifiez pas les fichiers du code à la main** : toute correction passe par Taha, sinon la mise à jour suivante s'arrête pour vous prévenir.

---

## 4. Étape 2 — Diagnostic (ne modifie rien)

```bash
cd /opt/conformite
sudo bash scripts/installer_serveur.sh --verifier
```

Exemple de résultat :

```
== 1. Diagnostic du serveur
  ✓ Système : Ubuntu 24.04.4 LTS
  ✓ Processeurs : 8  |  Mémoire : 32 Go  |  Disque libre : 120 Go
  ! Pas de GPU NVIDIA détecté : Mistral tournera sur CPU (~4 min par pièce rédigée).
  ✓ Accès Internet : https://ollama.com
  ✓ Accès Internet : https://registry-1.docker.io
  ...
Diagnostic terminé (rien n'a été modifié).
```

| Ligne `!` | Que faire |
|---|---|
| Moins de 12 Go de mémoire | Ajouter de la mémoire ou prendre un autre serveur : Mistral risque de ne pas démarrer |
| Moins de 40 Go libres | Libérer ou ajouter de l'espace disque |
| Pas de GPU | Rien : l'outil fonctionne, plus lentement |
| Pas d'accès à … | Autoriser ce site au pare-feu ou au proxy (voir §10) |

**Envoyez le résultat complet à Taha** avant de continuer.

---

## 5. Étape 3 — Installation complète

```bash
cd /opt/conformite
sudo bash scripts/installer_serveur.sh
```

Options, à placer entre `sudo` et `bash` :

| Option | Quand |
|---|---|
| `INTERFACE_PORT=8080` | le port 80 est déjà utilisé sur le serveur (l'adresse devient `http://IP:8080`) |
| `NGROK_AUTHTOKEN=… NGROK_URL=xxx.ngrok-free.app` | seulement si Taha demande un accès depuis l'extérieur (tableau de bord Vercel). Sinon, ne rien mettre |

Exemple : `sudo INTERFACE_PORT=8080 bash scripts/installer_serveur.sh`

Laissez le terminal ouvert jusqu'au bout. Si la connexion SSH risque de couper, lancez d'abord `tmux` (ou `screen`). La fin ressemble à ceci :

```
== Terminé
  Tableau de bord   : http://192.168.1.20   (réseau de l'entreprise)
  API locale        : http://127.0.0.1:8000  (clé d'API dans .env : API_KEY)
  Pas de tunnel : relancer avec NGROK_AUTHTOKEN et NGROK_URL pour un accès depuis Vercel.
  Se connecter au tableau de bord avec la clé API_KEY (sudo grep API_KEY .env).
```

**En cas d'arrêt sur une ligne `✗`** : le message indique la cause et la commande à lancer. Corrigez, puis relancez le même script ; il reprend là où il s'était arrêté. Voir aussi le §11.

---

## 5 bis. Profil de l'entreprise et dossiers acceptés (les modèles de Mistral)

Mistral rédige chaque pièce **sur le modèle de la même pièce d'un dossier déjà accepté par l'AMMPS** : même structure, même destinataire, mêmes formules. Il n'y remplace que les données du nouveau dispositif. Les coordonnées de l'entreprise viennent d'un profil. Ces fichiers **restent sur le serveur** : ils ne vont ni sur GitHub ni chez Claude.

**1. Le profil de l'entreprise** : le script a créé `config/entreprise.yaml`. Remplissez-le une fois (raison sociale, ville, adresse, téléphone, représentant légal, ICE, IF, RC, patente, RIB si souhaité) :

```bash
sudo nano /opt/conformite/config/entreprise.yaml
```

**2. Les dossiers acceptés** : copiez chaque dossier accepté dans `data/dossiers_valides/<pays d'origine>/<produit>/`, en gardant les noms de fichiers qui commencent par le **numéro de la pièce**. Les pays d'origine possibles sont `chine`, `inde`, `union_europeenne` et `autre`.

```
/opt/conformite/data/dossiers_valides/
└── union_europeenne/
    └── Ciment osseux/
        ├── 1-1-Lettre de Demande.pdf          ← modèle de la lettre (pièce 1)
        ├── 2-2-fiche signalétique.pdf          ← modèle de la fiche signalétique (pièce 2)
        ├── 16-16-Certificat d'enregistrement.pdf ← modèle du certificat annexe II (pièce 16)
        └── … (les autres pièces peuvent rester, elles sont ignorées)
```

Puis, **après chaque ajout** :

```bash
cd /opt/conformite && sudo bash scripts/indexer_modeles.sh
```

Le script affiche une ligne ✓ par modèle retenu : pièces 1, 2 et 16. Les certificats CE, ISO et autres documents de tiers ne sont jamais des modèles. Un fichier illisible est signalé ✗ et ignoré, sans bloquer les autres. Plus il y a de dossiers acceptés par pays d'origine, plus Mistral trouve un modèle proche.

---

## 6. Étape 4 — Vérifications (à faire toutes)

**Une commande fait toutes les vérifications automatiques** (≈10 min sur CPU, ne modifie rien) :

```bash
cd /opt/conformite && sudo bash scripts/verifier_installation.sh
```

Elle contrôle :
- les 4 conteneurs et Ollama ;
- la santé de l'API et la clé d'accès (sans clé : refusé ; avec la clé : accepté) ;
- le tableau de bord ;
- Mistral (vraie rédaction) et bge-m3 ;
- l'index (596 extraits) ;
- l'OCR (Tesseract fr/en/ar) ;
- les ports fermés, la protection de `.env`, la sauvegarde programmée, le disque et le GPU.

La dernière ligne doit être **« RÉSULTAT : installation complète et fonctionnelle »**. Les lignes `!` sont des conseils ; les lignes `✗` sont à corriger (voir §11), ou envoyez le rapport à Taha.

Ensuite, faites vous-même les contrôles « humains » 7 à 9 du tableau ci-dessous (navigateur, connexion, rédaction d'essai). Le détail des contrôles 1 à 6 est donné pour information.

Toutes ces commandes se lancent depuis `/opt/conformite`.

| # | Commande | Résultat attendu |
|---|---|---|
| 1 | `sudo docker compose --profile api --profile interface ps` | 4 conteneurs `Up` : conformite-postgres, conformite-qdrant, conformite-api, conformite-interface |
| 2 | `curl -s http://127.0.0.1:8000/health` | `"statut":"ok"`, puis `"postgres":true,"qdrant":true,"ollama":true`, puis `"authentification":"cle_api"` |
| 3 | `curl -s http://127.0.0.1/api/health` | la même réponse, passée par le tableau de bord |
| 4 | `ollama list` | `mistral:latest` et `bge-m3:latest` |
| 5 | `curl -s http://127.0.0.1:6333/collections/dossiers_reference \| grep -o '"points_count":[0-9]*'` | `"points_count":596` |
| 6 | `curl -s http://127.0.0.1:11434/api/generate -d '{"model":"mistral","prompt":"Réponds en un mot : bonjour","stream":false}' \| head -c 300` | une réponse en français (le premier appel peut prendre 1 à 2 minutes : chargement du modèle) |
| 7 | Depuis un **poste de travail**, ouvrir `http://IP-du-serveur` | la page de connexion « Vos dossiers AMMPS, préparés par un agent. Validés par vous. » |
| 8 | Se connecter (nom + clé d'API, voir §7) | le bandeau affiche **« Serveur en ligne »** |
| 9 | Créer un dossier d'essai et cliquer sur « Lancer la rédaction » pour une pièce | au bout de 3 à 5 min sur CPU, un projet de document apparaît, à relire |

Si les 9 points sont bons, l'installation est terminée. **Envoyez à Taha le résumé final** du §5 (il ne contient pas la clé) et l'adresse IP du serveur.

---

## 7. Étape 5 — Remettre la clé d'accès aux utilisateurs

Le tableau de bord demande une **clé d'API**. Elle a été générée au hasard par le script :

```bash
sudo grep API_KEY /opt/conformite/.env
```

- Remettez-la **de vive voix** ou par le **gestionnaire de mots de passe** de l'entreprise, jamais par e-mail ou messagerie.
- Chaque utilisateur saisit aussi son **nom** : il est inscrit dans le journal d'audit à chaque validation ou rejet.
- **Changer la clé** (départ d'un utilisateur, fuite) : remplacez la valeur `API_KEY=` dans `.env` par le résultat de `openssl rand -hex 32`, puis lancez `sudo docker compose --profile api --profile interface up -d`.

Le fichier `.env` contient tous les secrets (mot de passe de la base, clé). Il n'est lisible que par root. **Ne jamais le copier, l'envoyer ou le mettre sur GitHub.**

---

## 8. Exploitation au quotidien

**Redémarrage du serveur.** Tout redémarre seul : Docker et Ollama sont des services système, et les conteneurs sont en `restart: unless-stopped`.

Toutes les commandes se lancent depuis `/opt/conformite` :

| Besoin | Commande |
|---|---|
| État des services | `sudo docker compose --profile api --profile interface ps` |
| Journal de l'API (erreurs, rédactions) | `sudo docker compose logs -f --tail 100 api` |
| Journal du tableau de bord | `sudo docker compose logs --tail 100 interface` |
| Journal de Mistral / Ollama | `sudo journalctl -u ollama -f` |
| Modèle chargé en mémoire, CPU ou GPU | `ollama ps` |
| Redémarrer l'outil | `sudo docker compose --profile api --profile interface restart` |
| Redémarrer Ollama | `sudo systemctl restart ollama` |
| Arrêter l'outil | `sudo docker compose --profile api --profile interface stop` |

**Emplacement des données :**
- base PostgreSQL (dossiers, validations, journal) : volume Docker `postgres_data` ;
- index de recherche : volume `qdrant_data` ;
- projets rédigés et documents reçus des fournisseurs : `/opt/conformite/output/` ;
- modèles Mistral / bge-m3 : `/usr/share/ollama/.ollama/models`.

---

## 9. Sauvegardes (à mettre en place dès le premier jour)

Le script `scripts/sauvegarder.sh` sauvegarde la base, les projets et documents reçus (`output/`) et le fichier `.env`. Il garde 30 jours de sauvegardes.

```bash
sudo bash /opt/conformite/scripts/sauvegarder.sh              # vers /var/backups/conformite
```

**Sauvegarde automatique chaque nuit à 2 h** : lancez `sudo crontab -e` et ajoutez la ligne

```
0 2 * * * bash /opt/conformite/scripts/sauvegarder.sh >> /var/log/conformite-sauvegarde.log 2>&1
```

Copiez régulièrement `/var/backups/conformite` **hors du serveur** (NAS, autre machine) : ces fichiers contiennent des documents fournisseurs confidentiels et la clé.

**Restaurer la base** (remplacer le nom du fichier) :

```bash
cd /opt/conformite
sudo sh -c 'docker exec -i conformite-postgres pg_restore -U conformite -d conformite_dm --clean --if-exists \
     < /var/backups/conformite/base_AAAA-MM-JJ_HHMM.dump'
sudo tar -xzf /var/backups/conformite/fichiers_AAAA-MM-JJ_HHMM.tar.gz -C /opt/conformite
sudo docker compose --profile api --profile interface restart
```

L'index Qdrant n'a pas besoin d'être sauvegardé : il se reconstruit avec `sudo docker compose --profile api run --rm api bash scripts/indexer_tout.sh`.

---

## 10. Mise à jour, et cas du proxy d'entreprise

**Mettre à jour l'outil** quand Taha l'annonce : une seule commande, selon la façon dont il envoie la nouvelle version.

```bash
cd /opt/conformite
sudo bash scripts/mettre_a_jour.sh                      # nouvelle version publiée sur GitHub
sudo bash scripts/mettre_a_jour.sh /tmp/maj.bundle      # ou : fichier « .bundle » remis par Taha
```

Le script :
1. sauvegarde la base et les documents ;
2. vérifie que personne n'a modifié le code à la main, sinon il s'arrête ;
3. applique la nouvelle version (un fichier abîmé ou étranger est refusé) ;
4. reconstruit et redémarre les services ;
5. contrôle que tout répond.

Il termine par un **rapport** encadré, sans aucun secret : copiez-le et envoyez-le à Taha. La dernière ligne doit être « Mise à jour réussie ». Les données (dossiers, validations, documents reçus, `.env`) ne sont jamais touchées par une mise à jour.

Les règles réglementaires (`rules/*.yaml`) font partie de l'image : `--build` suffit à les prendre en compte. Si Taha ajoute des textes dans `data/raw_pdfs/`, il précisera la commande de réindexation.

**Si le serveur sort sur Internet par un proxy**, remplacez `http://proxy:3128` par l'adresse réelle.

- Pour le script (la session en cours) :
  ```bash
  export http_proxy=http://proxy:3128 https_proxy=http://proxy:3128 no_proxy=localhost,127.0.0.1
  sudo -E bash scripts/installer_serveur.sh
  ```
- Pour Docker (téléchargement des images) : créez `/etc/systemd/system/docker.service.d/proxy.conf` avec
  ```
  [Service]
  Environment="HTTP_PROXY=http://proxy:3128" "HTTPS_PROXY=http://proxy:3128" "NO_PROXY=localhost,127.0.0.1"
  ```
  puis lancez `sudo systemctl daemon-reload && sudo systemctl restart docker`.
- Pour la construction des images (pip, npm) : créez `/root/.docker/config.json` avec
  ```json
  { "proxies": { "default": { "httpProxy": "http://proxy:3128", "httpsProxy": "http://proxy:3128", "noProxy": "localhost,127.0.0.1" } } }
  ```
- Pour Ollama (téléchargement des modèles) : ajoutez `Environment="HTTPS_PROXY=http://proxy:3128"` dans `/etc/systemd/system/ollama.service.d/conformite.conf`, puis lancez `sudo systemctl daemon-reload && sudo systemctl restart ollama`.

Si le proxy **inspecte le HTTPS** (certificat d'entreprise), prévenez Taha : il faut ajouter ce certificat aux images.

---

## 10 bis. Architecture et circuit des modifications

**Sur le serveur** (rien d'autre n'est installé) :

```
 Postes de l'entreprise (navigateur)
        │  http://IP-du-serveur            (port 80, seul port ouvert)
        ▼
┌─────────────────────────── serveur de l'entreprise ───────────────────────────┐
│  [interface]  nginx : tableau de bord ── /api ──►  [api]  FastAPI (Python)     │
│                                                     │  ├─ moteur de règles     │
│                                                     │  │   rules/*.yaml        │
│                                                     │  │   (décide des pièces) │
│                                                     │  ├─ agent : lecture +    │
│                                                     │  │   rédaction           │
│                                                     │  └─ file de tâches       │
│                       ┌─────────────────────────────┼──────────────┐           │
│                       ▼                             ▼              ▼           │
│               [postgres]                    [qdrant]         Ollama (hôte)     │
│               dossiers, validations,        textes           Mistral 7B        │
│               journal d'audit               réglementaires   bge-m3            │
│                                             indexés                            │
│  output/ : projets rédigés et documents reçus des fournisseurs                 │
└────────────────────────────────────────────────────────────────────────────────┘
   [ … ] = conteneur Docker ; Ollama tourne directement sur la machine (accès au GPU)
```

**Circuit d'une modification** (règles corrigées, nouvelle fonction de l'agent…) :

```
 1. Taha envoie à Claude un dossier accepté ou une anomalie constatée
 2. Claude modifie le code, le teste, et le publie ──► GitHub (ou fichier .bundle remis à Taha)
 3. L'administrateur lance : sudo bash scripts/mettre_a_jour.sh
 4. Le serveur sauvegarde, applique, redémarre, contrôle ──► rapport ──► Taha ──► Claude
```

- Claude **n'a aucun accès au serveur** : il ne voit ni la base, ni les dossiers, ni la clé. Il ne peut rien modifier sur le serveur ; seul l'administrateur applique une version.
- Chaque version est numérotée (`git log -1 --oneline`) et chaque mise à jour est précédée d'une sauvegarde.
- **Revenir à la version précédente** si une mise à jour pose problème : le script affiche `ancienne -> nouvelle` (ex. `b236c4c -> 15d993e`). Lancez `sudo git reset --hard b236c4c && sudo docker compose --profile api --profile interface up -d --build` avec l'ancien code, puis prévenez Taha.
- Les dossiers réels restent sur le serveur. Seuls ceux que la direction autorise sont transmis à Claude pour les tests.
- **Option, sur décision de la direction :** installer Claude Code sur le serveur (`claude remote-control` lancé dans `/opt/conformite`), pour que Claude teste directement sur place avec le vrai Mistral. Contrepartie : il accède au code et aux données du serveur pendant la session. Ne rien installer de tel sans accord écrit.

---

## 11. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `✗ Ollama injoignable depuis le conteneur de l'API` | pare-feu entre Docker et l'hôte | `sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp`, puis relancer le script |
| `✗ Ollama ne répond pas` | service arrêté | `sudo journalctl -u ollama -n 50` puis `sudo systemctl restart ollama` |
| « Lancer la rédaction » échoue avec *timed out waiting for llama-server* | chargement de Mistral trop lent (CPU, disque lent) | vérifier que `/etc/systemd/system/ollama.service.d/conformite.conf` contient `OLLAMA_LOAD_TIMEOUT=20m`, puis lancer `sudo systemctl daemon-reload && sudo systemctl restart ollama` |
| Pièce en erreur « Mistral a échoué deux fois (erreur 500 d'Ollama) » | génération interrompue par Ollama (déjà relancée automatiquement une fois) | cliquer sur « Relancer la rédaction » ; si cela se répète : `sudo journalctl -u ollama -n 100` et `free -h` (mémoire), puis envoyer à Taha |
| Rédaction très lente (> 10 min) | CPU seul et serveur chargé | normal sur CPU ; vérifier `ollama ps` (colonne PROCESSOR) ; un GPU règle le problème |
| Mistral ne démarre pas, *out of memory* | mémoire insuffisante | fermer d'autres services ou ajouter de la mémoire (16 Go minimum) |
| `pull access denied` / `toomanyrequests` | limite de téléchargement de Docker Hub | attendre 1 h et relancer le script, ou `docker login` avec un compte Docker gratuit |
| `Bind for 0.0.0.0:80 failed: port is already allocated` | un autre site web occupe le port 80 | relancer avec `INTERFACE_PORT=8080` (voir §5) |
| Le tableau de bord ne s'ouvre pas depuis un poste | pare-feu du serveur ou du réseau | `sudo ufw allow 80/tcp` ; vérifier que le poste est sur le même réseau |
| Page ouverte mais « Serveur hors ligne » | API arrêtée | `sudo docker compose logs --tail 50 api` |
| « Clé d'API invalide » | mauvaise clé saisie | `sudo grep API_KEY .env` (voir §7) |
| `✗ Le plugin « docker buildx » est absent` | Docker ancien, installé par la distribution | `sudo apt install -y docker-buildx-plugin docker-compose-plugin` (dépôt Docker officiel) |
| `points_count` différent de 596 | indexation interrompue | `sudo docker compose --profile api run --rm api bash scripts/indexer_tout.sh` |
| Disque plein | journaux ou images Docker anciennes | `sudo docker system prune` (ne supprime ni les volumes ni les données) |

Pour tout autre problème, envoyez à Taha la sortie de ces trois commandes, **jamais le contenu de `.env`** :
- `sudo docker compose --profile api --profile interface ps`
- `sudo docker compose logs --tail 100 api`
- `sudo journalctl -u ollama -n 100`

---

## 12. Sécurité — récapitulatif

- Seul le port du tableau de bord (80) est ouvert au réseau interne. L'API, la base, Qdrant et Ollama ne sont joignables que depuis le serveur.
- L'API **refuse de démarrer sans clé d'accès**, et toute requête sans la clé est rejetée.
- Les documents des fournisseurs et les projets restent sur le serveur. Mistral tourne en local : rien n'est envoyé à un service extérieur.
- Le tunnel ngrok (accès depuis Internet) est **désactivé par défaut**. Ne l'activer qu'à la demande de Taha et de la direction.
- Le tableau de bord est en HTTP simple, ce qui convient à un réseau interne de confiance. Pour du HTTPS, placez-le derrière le reverse proxy et le certificat de l'entreprise, s'il en existe.
- L'authentification par comptes nominatifs (Keycloak) est prévue plus tard. Aujourd'hui, la clé est partagée et le nom saisi n'est pas vérifié.

---

## 13. À renvoyer à Taha

1. Le résultat du diagnostic (§4).
2. Le résumé final de l'installation (§5).
3. Le résultat des 9 vérifications (§6).
4. L'adresse du tableau de bord : `http://IP-du-serveur`.
