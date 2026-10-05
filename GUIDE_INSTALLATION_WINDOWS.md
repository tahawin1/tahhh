# Guide d'installation et d'utilisation — serveur Windows Server 2022

- **Pour :** le collègue qui installe et suit l'outil sur le serveur de l'entreprise (machine physique, Windows Server 2022, 16 Go).
- **Durée :** 1 h 30 environ pour l'installation, dont 1 h d'attente.
- **Remis par Taha :** le dossier **`CLE-USB-ConformiteDM`**, à copier tel quel sur une clé USB. Il contient l'outil, l'installateur et ce guide.

**Tout se fait sous Windows** : dans **PowerShell** pour l'installation, puis par **double-clic** sur des outils numérotés. L'outil fonctionne en interne dans un Linux intégré à Windows (WSL2), mais vous n'avez pas à vous en occuper : les scripts le pilotent pour vous.

---

## Partie A — Avant de commencer (10 min)

### A1. Virtualisation activée dans le BIOS

Ouvrez le **Gestionnaire des tâches** (Ctrl+Maj+Échap), onglet **Performance**, puis **Processeur**. En bas à droite, la ligne **« Virtualisation »** doit indiquer **Activé**.

Si elle indique **Désactivé** :

1. Redémarrez et entrez dans le BIOS/UEFI (touche **F2**, **F10**, **Suppr** ou **F12** au tout début du démarrage, selon le fabricant).
2. Activez **Intel Virtualization Technology (VT-x)** ou **AMD-V / SVM Mode**, souvent dans *Advanced → CPU Configuration*.
3. Enregistrez (souvent **F10**), puis redémarrez.

Vérification possible dans PowerShell :

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, VirtualizationFirmwareEnabled
```

`True` signifie que la virtualisation est activée. Si Hyper-V est déjà actif, la valeur peut afficher `False` alors que tout va bien : le script d'installation fait de toute façon la vérification complète.

### A2. Windows à jour

Ouvrez **Paramètres → Windows Update → Rechercher des mises à jour**, installez tout et redémarrez si Windows le demande.

### A3. Accès Internet pendant l'installation

Le serveur doit joindre ces sites en HTTPS (port 443) pendant l'installation. Demandez au service informatique de les autoriser si la sortie est filtrée :

| Site | Pour |
|---|---|
| `github.com`, `objects.githubusercontent.com` | mise à jour du composant Linux de Windows (WSL) |
| `aka.ms`, `*.microsoft.com`, `*.windowsupdate.com` | WSL et Ubuntu |
| `ollama.com`, `registry.ollama.ai` | moteur d'IA et modèle Mistral |
| `get.docker.com`, `download.docker.com`, `registry-1.docker.io`, `production.cloudflare.docker.com` | Docker |
| `archive.ubuntu.com`, `security.ubuntu.com`, `deb.debian.org` | paquets Linux, dont la lecture des documents scannés |
| `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org` | composants de l'application |

Pour tester l'accès, lancez dans PowerShell. Toutes les lignes doivent afficher `True` :

```powershell
"github.com","ollama.com","registry-1.docker.io","pypi.org","registry.npmjs.org" | ForEach-Object { "{0,-25} {1}" -f $_, (Test-NetConnection $_ -Port 443 -WarningAction SilentlyContinue).TcpTestSucceeded }
```

### A4. La clé USB

Copiez le dossier **`CLE-USB-ConformiteDM`** sur une clé USB. Il contient :

| Fichier | Rôle |
|---|---|
| `INSTALLER.cmd` | l'installation, par double-clic |
| `INSTALLER-port-8080.cmd` | variante si le port 80 est déjà pris (IIS) |
| `conformite-serveur.zip` | l'outil complet (ne pas extraire à la main) |
| `empreinte-sha256.txt` | sert à vérifier que le zip n'est pas abîmé |
| `installer_depuis_cle.ps1` | script lancé par INSTALLER.cmd |
| `LISEZ-MOI.txt`, `GUIDE_INSTALLATION_WINDOWS.*` | ce guide et son résumé |

---

## Partie B — Installation (≈ 1 h 15)

### B1. Premier lancement : activation des composants Windows

Branchez la clé sur le serveur et double-cliquez sur **`INSTALLER.cmd`**, puis répondez **Oui** à la demande de droits administrateur.

Le script :

- copie le paquet dans `C:\conformite-install` ;
- vérifie son empreinte (`[OK] Paquet intact`) ;
- l'extrait ;
- vérifie Windows, la mémoire, le disque et la virtualisation ;
- active WSL2.

Il s'arrête sur :

```
[!]  Composants WSL2 activés : REDÉMARRER le serveur, puis relancer ce même script.
```

Redémarrez le serveur (menu Démarrer → Marche/Arrêt → Redémarrer, ou en PowerShell `Restart-Computer`).

> Si le message **« Le port 80 est déjà utilisé (programme : …, souvent IIS) »** apparaît, utilisez **`INSTALLER-port-8080.cmd`** à la place de `INSTALLER.cmd`, ici et à la relance. Le tableau de bord sera alors à l'adresse `http://IP-du-serveur:8080`.

**Équivalent en PowerShell administrateur**, si vous préférez taper la commande (la clé étant par exemple en `E:`) :

```powershell
powershell -ExecutionPolicy Bypass -File E:\CLE-USB-ConformiteDM\installer_depuis_cle.ps1
```

### B2. Second lancement : installation complète

Après le redémarrage, la clé toujours branchée, **double-cliquez à nouveau sur `INSTALLER.cmd`**, ou sur `INSTALLER-port-8080.cmd` si vous l'avez utilisé.

Restez devant l'écran **pendant les 10 premières minutes, puis à la fin** : le script pose 4 questions.

| Ce qui s'affiche | Ce que vous faites |
|---|---|
| `Mise à jour de WSL (téléchargement direct)…` | Attendre 2 à 5 min |
| `Create a default Unix user account:` (ou `Enter new UNIX username:`) | **Question 1** : tapez un nom en minuscules sans espace (ex. `admin`), puis Entrée |
| `New password:` puis `Retype new password:` | Choisissez un mot de passe et **notez-le**. Rien ne s'affiche pendant la frappe, c'est normal. |
| Une invite du type `admin@SERVEUR:~$` | Tapez `exit`, puis Entrée |
| `== 4. Diagnostic` suivi de lignes ✓ et ! | Lisez. Des **✓** partout = parfait. « Pas de GPU » en ! est normal. |
| `Continuer l'installation complète (~1 h) ? (O/N)` | **Question 2** : `O`, puis Entrée |
| Défilement pendant ~1 h (Docker, Mistral 4 Go, indexation des textes) | Attendre sans fermer la fenêtre |
| Fenêtre **« Compte qui lance Ubuntu au démarrage du serveur »** | **Question 3** : le **mot de passe de votre compte Windows**, puis OK |
| `Remplir maintenant le profil de l'entreprise … ? (O/N)` | **Question 4** : `O`, puis répondez à chaque rubrique (outil 2, Partie C) |
| `== 7. Vérification complète` (≈ 10 min) | Attendre |
| `== Terminé` avec `Tableau de bord : http://…` | **Notez cette adresse** |

Si le script s'arrête sur une ligne rouge **[X]** ou **✗**, le message indique la cause. Corrigez, puis **relancez la même commande** : il reprend où il s'était arrêté.

À la fin, le dossier **`C:\ConformiteDM`** contient les outils, et un raccourci **« Conformite DM »** est créé sur le bureau.

---

## Partie C — Les outils (double-clic dans C:\ConformiteDM)

Ouvrez le raccourci **Conformite DM** du bureau. Chaque outil fait **une seule tâche** et enregistre son **rapport daté** dans `C:\ConformiteDM\rapports`.

> Utilisez toujours **le compte Windows qui a fait l'installation** : la partie Linux de l'outil est rattachée à ce compte.

| Outil (double-clic) | Ce qu'il fait |
|---|---|
| **1 - Etat du serveur** | Vérifie Linux, le démarrage automatique, le relais réseau, le tableau de bord, Mistral et la dernière sauvegarde. Ne modifie rien. |
| **2 - Profil de l'entreprise** | Saisie des coordonnées reprises dans les courriers : raison sociale, ville, adresse, téléphone, représentant légal, ICE, IF, RC, patente, RIB |
| **3 - Deposer les dossiers acceptes** | Ouvre le dossier où copier les dossiers déjà acceptés par l'AMMPS (modèles de Mistral) |
| **4 - Indexer les modeles** | Prend en compte les dossiers acceptés déposés. À lancer après chaque ajout. |
| **5 - Verification complete** | Contrôle complet en ≈ 10 min : services, sécurité, Mistral, index, lecture des scans, sauvegarde. Ne modifie rien. |
| **6 - Mettre a jour** | Installe la nouvelle version envoyée par Taha (Partie E), puis vérifie |
| **7 - Sauvegarder maintenant** | Sauvegarde immédiate, en plus de la sauvegarde automatique de 2 h du matin |
| **8 - Redemarrer l'outil** | Relance tout si l'outil ne répond plus (≈ 3 min ; droits administrateur demandés) |
| **9 - Cle d'acces** | Affiche la clé à saisir dans le tableau de bord |

Chaque outil peut aussi se lancer dans PowerShell (liste complète dans le récapitulatif en fin de guide). Par exemple :

```powershell
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Etat.ps1
```

### C1. Juste après l'installation, dans cet ordre

1. **1 - Etat du serveur** : toutes les lignes doivent être **[OK]**.
2. **2 - Profil de l'entreprise**, si vous ne l'avez pas rempli à la question 4.
3. **3 - Deposer les dossiers acceptes** (voir C2).
4. **4 - Indexer les modeles** : une ligne ✓ par modèle (pièces 1, 2 et 16).
5. **5 - Verification complete** : la dernière ligne doit être **« RÉSULTAT : installation complète et fonctionnelle »**.
6. **9 - Cle d'acces** : notez la clé et remettez-la à Taha **de vive voix**, jamais par e-mail ni messagerie.

### C2. Déposer un dossier accepté (modèle pour Mistral)

1. Double-cliquez sur **3 - Deposer les dossiers acceptes**. L'Explorateur s'ouvre sur `dossiers_valides`, qui contient les sous-dossiers `union_europeenne`, `chine`, `inde` et `autre`.
2. Ouvrez le dossier du **pays d'origine** du produit et créez-y un dossier au **nom du produit**, par exemple `Ciment osseux`.
3. Copiez-y les PDF du dossier accepté **sans les renommer**. Ils commencent par le numéro de la pièce : `1-1-Lettre de Demande.pdf`, `2-2-fiche signalétique.pdf`, `16-16-Certificat d'enregistrement.pdf`…
4. Double-cliquez sur **4 - Indexer les modeles**.

### C3. Sauvegardes

- **Automatiques chaque nuit à 2 h**, rien à faire. Sont sauvegardés : la base, les projets, les documents reçus, le profil et la clé. Une copie est faite dans **`C:\ConformiteDM\sauvegardes`**, avec 30 jours d'historique.
- Faites inclure `C:\ConformiteDM\sauvegardes` dans les **sauvegardes habituelles de l'entreprise** (NAS, bande, cloud de sauvegarde).
- Ce dossier contient la clé d'accès : il est réservé aux administrateurs. Ne le partagez pas.

---

## Partie D — Premier test depuis un poste de travail

1. Sur un autre ordinateur du réseau, ouvrez dans un navigateur l'adresse notée en B2, par exemple `http://192.168.1.20`.
2. La page **« Vos dossiers AMMPS, préparés par un agent. Validés par vous. »** s'affiche.
3. Saisissez votre **nom** et la **clé d'accès**. En bas à gauche doit s'afficher **« Serveur en ligne »**.
4. Cliquez sur **Nouveau dossier** et créez un essai : Union européenne, classe IIb, un nom de produit.
5. Sur la pièce 1 « Lettre de demande », cliquez sur **Lancer la rédaction**. Après 3 à 5 minutes, un projet de lettre apparaît, avec l'en-tête de l'entreprise et l'AMMPS comme destinataire.

---

## Partie E — Mises à jour et lien avec GitHub

L'outil installé est **relié au dépôt GitHub public de Taha** : `github.com/tahawin1/tahhh`, branche `claude/complete-pipeline-setup-ikdsp0`. Aucun mot de passe ni jeton n'est nécessaire.

```
 Taha (avec Claude) ── publie une nouvelle version ──► GitHub (tahawin1/tahhh)
                                                          │
                       double-clic « 6 - Mettre a jour » sur le serveur
                                                          ▼
                              le serveur télécharge la version, l'installe, vérifie
```

**Cas habituel (serveur connecté à Internet)** : quand Taha annonce une nouvelle version, double-cliquez sur **6 - Mettre a jour**. Le dossier `C:\ConformiteDM\maj\` doit être vide.

**Sans accès à GitHub** : Taha envoie un fichier `.bundle`. Copiez-le dans **`C:\ConformiteDM\maj\`**, puis double-cliquez sur **6 - Mettre a jour**. Le fichier le plus récent est utilisé, puis rangé dans `maj\appliques`.

Ce qui transite par GitHub : **uniquement le code de l'outil**. Les dossiers, documents des fournisseurs, profil de l'entreprise et clé d'accès restent sur le serveur et n'y vont jamais.

La mise à jour :

- fait d'abord une **sauvegarde** ;
- ne touche **jamais** aux dossiers, validations, documents reçus, profil ni clé ;
- se termine par une **vérification complète** ;
- met aussi à jour les outils de `C:\ConformiteDM`.

Envoyez ensuite à Taha le rapport `C:\ConformiteDM\rapports\mise_a_jour_<date>.txt`.

---

## Partie E bis — Jenkins (intégration continue)

Jenkins fait passer à l'agent **toutes les étapes du métier**, à chaque nouvelle
version publiée sur GitHub (vérifié toutes les 15 minutes), et lui donne une note :

| Étape Jenkins | Ce qui est vérifié |
|---|---|
| Tests et matrice des règles | 7 pays × 7 classes × 5 situations : la liste des pièces ne change jamais sans qu'on l'ait voulu ; chaque pièce cite son article |
| Lecture par Mistral | 3 documents fictifs (dont un scan) : bonnes valeurs lues, aucune valeur fausse acceptée |
| RAG et recommandations | le bon texte du bon pays est retrouvé ; les synthèses de Mistral citent le texte mot pour mot |
| Agent de bout en bout | création du dossier → rangement des fichiers → lecture → checklist (certificat expiré détecté) → fiche et annexe II → lettre → ZIP → reprise des documents du même fabricant |
| Rejeu des dossiers acceptés | l'agent refait chaque dossier accepté par l'AMMPS **sans le voir** ; sa fiche, son annexe II et sa lettre sont comparées au dossier accepté |
| Déploiement | seulement si « DEPLOYER » est coché **et** qu'une personne clique « Déployer » |

**Deux niveaux, pour limiter le bruit du PC :**
- **rapide** (par défaut, à chaque nouvelle version) : code, lois → pièces, interface.
  2 à 3 minutes, sans Mistral, le PC reste silencieux ;
- **complet** (chaque nuit vers 2 h si le PC est allumé, ou à la demande : « Lancer
  un build avec des paramètres » → NIVEAU = complet) : en plus la lecture par Mistral,
  le RAG, l'agent de bout en bout et les dossiers acceptés. 30 min à 2 h, le PC chauffe.

**Lire le résultat :** dans la liste des builds, chaque build affiche une ligne de
résumé (ex. « [complet] Code ✓ · Lois → pièces ✓ · Lecture par Mistral ✓ 18/20 · … »).
Pour le détail : cliquer sur le build → **Artefacts** → `rapports-ci/rapport.html` :
une ligne par étape du métier, la lettre produite par Mistral, la note des dossiers
acceptés et la liste de ce qui est à corriger.

Vert : tout est bon. Orange : le code est bon mais la qualité de l'IA est sous
le seuil, ou Ollama était arrêté. Rouge : une règle, un test ou la construction
est cassé.

**Plus il y a de dossiers acceptés, plus l'évaluation est sérieuse.** Déposez-les
avec l'outil 3, dans le dossier du pays d'origine, en mettant **la classe entre
parenthèses dans le nom du dossier** : `Ciment osseux (IIb)`, `Gants d'examen (Is)`.
Lancez ensuite l'outil 4 : Mistral apprend leurs formulaires, et Jenkins s'en
sert comme corrigé.

Installation : double-clic sur **11 - Jenkins**. L'outil installe Jenkins,
affiche le mot de passe du compte `admin` (à garder pour vous, jamais en
capture d'écran) et ouvre http://localhost:8081. La tâche `conformite-dm`
existe déjà et lance son premier build dans la minute.

Résultats : tâche `conformite-dm` → dernier build → **Test Result** (un contrôle
par ligne) et **Artefacts** (`dossiers-acceptes.md` : la note de l'agent par
dossier ; `matrice-regles.md` ; `agent.json` avec la lettre produite).

## Partie F — Au quotidien

- **Redémarrage du serveur** : rien à faire. Tout redémarre seul en 2 à 3 minutes (tâche planifiée *ConformiteDM-Demarrage*).
- **Un doute ?** Lancez **1 - Etat du serveur**.
- **L'outil ne répond plus ?** Lancez **8 - Redemarrer l'outil**, puis **1 - Etat du serveur**.

Commandes PowerShell utiles au service informatique :

- État du composant Linux (doit afficher `Running`) :
  ```powershell
  wsl --list --verbose
  ```
- Tâche de démarrage automatique :
  ```powershell
  Get-ScheduledTaskInfo -TaskName ConformiteDM-Demarrage
  ```
- Journal du démarrage automatique :
  ```powershell
  Get-Content C:\ProgramData\ConformiteDM\demarrage.log -Tail 20
  ```
- Relais réseau du port du tableau de bord :
  ```powershell
  netsh interface portproxy show v4tov4
  ```
- Règle du pare-feu Windows :
  ```powershell
  Get-NetFirewallRule -DisplayName "Conformite DM - tableau de bord"
  ```
- Profil réseau (doit être *DomainAuthenticated* ou *Private*) :
  ```powershell
  Get-NetConnectionProfile
  ```
- Santé de l'application :
  ```powershell
  (Invoke-WebRequest -UseBasicParsing http://127.0.0.1/api/health).Content
  ```
- Cinq derniers rapports des outils :
  ```powershell
  Get-ChildItem C:\ConformiteDM\rapports | Sort-Object LastWriteTime -Descending | Select-Object -First 5
  ```

---

## Partie G — Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `[X] La virtualisation est désactivée dans le BIOS` | VT-x / AMD-V désactivé | Partie A1 |
| `[X] WSL n'a pas pu être mis à jour` | pas d'accès à GitHub/Microsoft | autoriser les sites (A3), ou télécharger `wsl.x64.msi` sur https://github.com/microsoft/WSL/releases depuis un autre poste, l'installer par double-clic, puis relancer B2 |
| `[X] Le port 80 est déjà utilisé` | IIS ou un autre site web | relancer avec `INSTALLER-port-8080.cmd` |
| `[X] systemd ne démarre pas` | composant Linux trop ancien | PowerShell administrateur : `wsl --update --web-download`, puis relancer B2 |
| « l'exécution de scripts est désactivée » | stratégie PowerShell | utiliser les commandes du guide (`-ExecutionPolicy Bypass`) ou les outils `.cmd` |
| « Ubuntu introuvable pour le compte … » | outil lancé avec un autre compte Windows | se connecter avec le compte qui a fait l'installation |
| Tableau de bord inaccessible depuis les postes, mais OK sur le serveur | pare-feu réseau ou profil réseau « Public » | `Get-NetConnectionProfile` ; sinon service informatique |
| Tableau de bord inaccessible après un redémarrage | démarrage automatique en échec | **8 - Redemarrer l'outil**, puis lire `C:\ProgramData\ConformiteDM\demarrage.log` |
| « Serveur hors ligne » dans le tableau de bord | application arrêtée | **8 - Redemarrer l'outil** |
| Pièce en erreur « Mistral a échoué deux fois » | Mistral surchargé ou mémoire pleine | **Relancer la rédaction** ; si ça se répète, **5 - Verification complete** et envoyer le rapport à Taha |
| Rédaction lente (3 à 5 min par pièce) | serveur sans carte graphique | normal ; éviter d'autres programmes lourds sur ce serveur |
| Mot de passe du compte Windows changé | la tâche planifiée utilise l'ancien | relancer B2 : il recrée la tâche |

---

## Partie H — À renvoyer à Taha

1. La **capture du diagnostic** (B2, « 4. Diagnostic »).
2. Le rapport **`C:\ConformiteDM\rapports\verification_<date>.txt`** (outil 5).
3. L'**adresse du tableau de bord** (fin de B2).
4. La **clé d'accès** (outil 9), **de vive voix uniquement**.

En cas de problème, envoyez le dernier rapport de `C:\ConformiteDM\rapports` et le fichier `C:\ProgramData\ConformiteDM\demarrage.log`. Ils ne contiennent aucun secret.

**Ne jamais envoyer** : la clé d'accès par écrit, le dossier `C:\ConformiteDM\sauvegardes`, ni les documents des fournisseurs.

---

## Récapitulatif

**Installation** (clé USB branchée sur le serveur)

1. Double-clic sur `INSTALLER.cmd`, puis **Oui**.
2. Redémarrer le serveur.
3. Double-clic sur `INSTALLER.cmd` à nouveau, puis répondre aux questions.

Équivalent en PowerShell administrateur (clé en `E:`), à lancer avant et après le redémarrage :

```powershell
powershell -ExecutionPolicy Bypass -File E:\CLE-USB-ConformiteDM\installer_depuis_cle.ps1
Restart-Computer
```

**Vérifications avant installation**

```powershell
Get-CimInstance Win32_Processor | Select-Object Name, VirtualizationFirmwareEnabled
"github.com","ollama.com","registry-1.docker.io","pypi.org","registry.npmjs.org" | ForEach-Object { "{0,-25} {1}" -f $_, (Test-NetConnection $_ -Port 443 -WarningAction SilentlyContinue).TcpTestSucceeded }
```

**Outils** (ou double-clic dans `C:\ConformiteDM`)

```powershell
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Etat.ps1
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Configurer-entreprise.ps1
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Deposer-dossiers.ps1
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Indexer-modeles.ps1
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Verifier.ps1
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Mettre-a-jour.ps1
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Sauvegarder.ps1
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Redemarrer.ps1
powershell -ExecutionPolicy Bypass -File C:\ConformiteDM\outils\Cle-acces.ps1
```

---

## Annexe — assistance technique uniquement

L'outil **10 - Terminal Ubuntu (avance)** ouvre la console Linux interne, dans `/opt/conformite`. Ne l'utilisez qu'à la demande de Taha : toute modification manuelle des fichiers de l'outil bloque les mises à jour suivantes.
