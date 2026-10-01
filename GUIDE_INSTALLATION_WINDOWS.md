# Guide d'installation — serveur Windows Server 2022 (machine physique)

- **Pour :** le collègue qui installe l'outil sur le serveur de l'entreprise.
- **Durée :** 1 h 30 environ, dont 1 h d'attente (téléchargements, indexation).
- **Fichiers remis par Taha :** `conformite-serveur.zip` (l'outil) et ce guide.

Deux types de commandes figurent dans ce guide :

| Encadré | Où le taper |
|---|---|
| **🪟 Windows** | **PowerShell ouvert en administrateur** |
| **🐧 Ubuntu** | **Terminal Ubuntu** (ouvert depuis PowerShell, voir Partie C) |

Copiez-collez les commandes telles quelles. Un clic droit colle le texte dans PowerShell et dans le terminal Ubuntu.

---

## Partie A — Avant de commencer (10 min)

### A1. La virtualisation doit être activée dans le BIOS

Ouvrez le **Gestionnaire des tâches** (Ctrl+Maj+Échap), onglet **Performance**, puis **Processeur**. En bas à droite, la ligne **« Virtualisation »** doit indiquer **Activé**.

Si elle indique **Désactivé** :

1. Redémarrez le serveur et entrez dans le BIOS/UEFI (touche **F2**, **F10**, **Suppr** ou **F12** selon le fabricant, au tout début du démarrage).
2. Activez **Intel Virtualization Technology (VT-x)** ou **AMD-V / SVM Mode**. L'option se trouve souvent dans *Advanced → CPU Configuration*.
3. Enregistrez (souvent **F10**), puis redémarrez.

### A2. Windows à jour

Ouvrez **Paramètres → Windows Update → Rechercher des mises à jour**, puis installez tout et redémarrez si Windows le demande.

### A3. Accès Internet pendant l'installation

Le serveur doit pouvoir joindre ces sites en HTTPS (port 443). Demandez au service informatique de les autoriser si un pare-feu ou un proxy filtre la sortie :

| Site | Pour |
|---|---|
| `github.com`, `objects.githubusercontent.com` | mise à jour de WSL |
| `aka.ms`, `*.microsoft.com`, `*.windowsupdate.com` | WSL et Ubuntu |
| `ollama.com`, `registry.ollama.ai` | Ollama et le modèle Mistral |
| `get.docker.com`, `download.docker.com`, `registry-1.docker.io`, `production.cloudflare.docker.com` | Docker et ses images |
| `archive.ubuntu.com`, `security.ubuntu.com`, `deb.debian.org` | paquets Linux (dont la lecture des scans) |
| `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org` | composants de l'application |

### A4. Copier et extraire le paquet

1. Créez le dossier **`C:\conformite-install`**.
2. Copiez-y **`conformite-serveur.zip`**.
3. Faites un clic droit sur le zip, puis **Extraire tout…**, puis **Extraire**, sans changer le dossier proposé.

Vous obtenez `C:\conformite-install\conformite-serveur\conformite\…`.

---

## Partie B — Installation automatique (≈ 1 h 15)

### B1. Ouvrir PowerShell en administrateur

Menu **Démarrer**, tapez `PowerShell`, faites un clic droit sur **Windows PowerShell**, puis **Exécuter en tant qu'administrateur**, et répondez **Oui**.

### B2. Premier lancement : activation de WSL2

**🪟 Windows**
```powershell
powershell -ExecutionPolicy Bypass -File C:\conformite-install\conformite-serveur\conformite\deploiement\windows\installer_windows.ps1 -Zip C:\conformite-install\conformite-serveur.zip
```

Le script vérifie Windows, la mémoire, le disque et la virtualisation, puis active WSL2. Il s'arrête avec ce message :

```
[!]  Composants WSL2 activés : REDÉMARRER le serveur, puis relancer ce même script.
```

**🪟 Windows** : redémarrez le serveur.
```powershell
Restart-Computer
```

> Si le message **« Le port 80 est déjà utilisé (programme : …, souvent IIS) »** apparaît, ajoutez **` -Port 8080`** à la fin de la commande, ici et dans toutes les relances. L'adresse du tableau de bord sera alors `http://IP-du-serveur:8080`.

### B3. Second lancement : installation complète

Après le redémarrage, rouvrez **PowerShell en administrateur** (B1) et relancez **la même commande** :

**🪟 Windows**
```powershell
powershell -ExecutionPolicy Bypass -File C:\conformite-install\conformite-serveur\conformite\deploiement\windows\installer_windows.ps1 -Zip C:\conformite-install\conformite-serveur.zip
```

Le script enchaîne les étapes suivantes. **Restez devant l'écran pendant les 10 premières minutes** : trois questions vous seront posées.

| Ce qui s'affiche | Ce que vous faites |
|---|---|
| `Mise à jour de WSL (téléchargement direct)…` | Rien, attendre (2 à 5 min) |
| `Installation d'Ubuntu (Ubuntu-24.04)…` puis `Create a default Unix user account:` (ou `Enter new UNIX username:`) | **Question 1** : tapez un nom en minuscules, sans espace (ex. `admin`), puis Entrée |
| `New password:` puis `Retype new password:` | Choisissez un mot de passe et **notez-le**. Rien ne s'affiche pendant la frappe, c'est normal. |
| Une invite verte du type `admin@SERVEUR:~$` | Tapez `exit`, puis Entrée |
| `== 4. Diagnostic` puis une liste de lignes ✓ et ! | Lisez. Des **✓** partout = parfait. **« Pas de GPU »** en `!` est normal. |
| `Continuer l'installation complète (~1 h) ? (O/N)` | **Question 2** : tapez `O`, puis Entrée |
| Beaucoup de lignes défilent pendant ~1 h (Docker, Ollama, téléchargement de Mistral 4 Go, indexation) | Rien, attendre. Ne fermez pas la fenêtre. |
| Une fenêtre **« Compte qui lance Ubuntu au démarrage du serveur »** | **Question 3** : saisissez le **mot de passe de votre compte Windows**, puis OK |
| `== 7. Vérification complète` (≈ 10 min) | Rien, attendre |
| `== Terminé` avec `Tableau de bord : http://…` | **Notez cette adresse** : c'est celle du tableau de bord |

Si le script s'arrête sur une ligne rouge **[X]** ou **✗**, lisez le message : il indique la cause. Corrigez, puis **relancez la même commande**. Le script reprend où il s'était arrêté, sans rien casser.

---

## Partie C — Configuration (15 min)

### C1. Ouvrir le terminal Ubuntu

**🪟 Windows**
```powershell
wsl -d Ubuntu-24.04 -u root
```

L'invite devient `root@SERVEUR:…#`. Vous êtes dans Ubuntu, en administrateur. Placez-vous dans le dossier de l'outil :

**🐧 Ubuntu**
```bash
cd /opt/conformite
```

Toutes les commandes **🐧 Ubuntu** suivantes se tapent dans ce terminal, depuis ce dossier.

### C2. Remplir le profil de l'entreprise (une seule fois)

Ces coordonnées sont reprises dans l'en-tête et le pied de page des courriers rédigés par Mistral.

**🐧 Ubuntu**
```bash
nano config/entreprise.yaml
```

Remplacez chaque valeur entre guillemets : raison sociale, ville, adresse, téléphone, représentant légal, ICE, IF, RC, patente, RIB. Ensuite :

- **Ctrl+O** puis **Entrée** pour enregistrer ;
- **Ctrl+X** pour quitter.

### C3. Déposer les dossiers déjà acceptés par l'AMMPS (les modèles de Mistral)

1. Ouvrez l'**Explorateur Windows** et tapez dans la barre d'adresse :
   ```
   \\wsl.localhost\Ubuntu-24.04\opt\conformite\data\dossiers_valides
   ```
2. Créez un dossier par **pays d'origine** : `union_europeenne`, `chine`, `inde` ou `autre`.
3. Dans ce dossier, créez un dossier par **produit**, par exemple `Ciment osseux`.
4. Copiez-y les PDF du dossier accepté **sans les renommer**. Ils doivent commencer par le numéro de la pièce, par exemple `1-1-Lettre de Demande.pdf`, `2-2-fiche signalétique.pdf` ou `16-16-Certificat d'enregistrement.pdf`.

Puis indexez-les :

**🐧 Ubuntu**
```bash
bash scripts/indexer_modeles.sh
```

Résultat attendu : une ligne **✓** par modèle, pour les pièces 1, 2 et 16. Relancez cette commande **à chaque nouveau dossier accepté** ajouté.

### C4. Vérification complète (≈ 10 min, ne modifie rien)

**🐧 Ubuntu**
```bash
bash scripts/verifier_installation.sh
```

La dernière ligne doit être :
```
RÉSULTAT : installation complète et fonctionnelle.
```

- Les lignes **!** (jaune) sont des conseils.
- Les lignes **✗** (rouge) sont à corriger : voir la Partie G, ou envoyer le résultat à Taha.

### C5. Sauvegarde automatique chaque nuit à 2 h

**🐧 Ubuntu**
```bash
crontab -e
```
Si on vous demande de choisir un éditeur, tapez `1` (nano), puis Entrée. Ajoutez **cette ligne** tout en bas, puis enregistrez (**Ctrl+O**, **Entrée**) et quittez (**Ctrl+X**) :
```
0 2 * * * bash /opt/conformite/scripts/sauvegarder.sh >> /var/log/conformite-sauvegarde.log 2>&1
```

Testez la sauvegarde une première fois :

**🐧 Ubuntu**
```bash
bash scripts/sauvegarder.sh
```

Copiez régulièrement les sauvegardes **hors de Ubuntu**, par exemple une fois par semaine, vers un dossier Windows lui-même sauvegardé :

**🐧 Ubuntu**
```bash
mkdir -p /mnt/c/Sauvegardes-ConformiteDM && cp -r /var/backups/conformite/* /mnt/c/Sauvegardes-ConformiteDM/
```

### C6. Récupérer la clé d'accès au tableau de bord

**🐧 Ubuntu**
```bash
grep API_KEY .env
```

Remettez la valeur à Taha **de vive voix** ou par le gestionnaire de mots de passe de l'entreprise, **jamais par e-mail ou messagerie**.

Pour quitter le terminal Ubuntu :

**🐧 Ubuntu**
```bash
exit
```

---

## Partie D — Premier test depuis un poste de travail

1. Sur un autre ordinateur du réseau, ouvrez un navigateur à l'adresse notée en B3, par exemple `http://192.168.1.20`.
2. La page **« Vos dossiers AMMPS, préparés par un agent. Validés par vous. »** s'affiche.
3. Saisissez votre **nom** et la **clé d'accès** (C6), puis **Accéder au tableau de bord**. En bas à gauche doit apparaître **« Serveur en ligne »**.
4. Cliquez sur **Nouveau dossier** et créez un essai : Union européenne, classe IIb, un nom de produit.
5. Sur la pièce 1 « Lettre de demande », cliquez sur **Lancer la rédaction**. Après 3 à 5 minutes, un projet de lettre apparaît, avec votre en-tête et l'AMMPS comme destinataire.

Si la page ne s'ouvre pas depuis le poste mais fonctionne sur le serveur lui-même (`http://localhost`), c'est le pare-feu réseau : voir la Partie G.

---

## Partie E — Au quotidien

**Redémarrage du serveur : rien à faire.** La tâche planifiée **ConformiteDM-Demarrage** relance Ubuntu, Docker, Mistral et le relais réseau au démarrage de Windows, en 2 à 3 minutes.

### Commandes utiles

| Besoin | Où | Commande |
|---|---|---|
| Ubuntu est-il allumé ? | 🪟 | `wsl --list --verbose` (doit afficher `Running`) |
| Journal du démarrage automatique | 🪟 | `Get-Content C:\ProgramData\ConformiteDM\demarrage.log -Tail 20` |
| Relancer tout l'outil | 🪟 | `wsl --shutdown` puis `Start-ScheduledTask -TaskName ConformiteDM-Demarrage` |
| Relais réseau actif ? | 🪟 | `netsh interface portproxy show v4tov4` |
| Ouvrir le terminal Ubuntu | 🪟 | `wsl -d Ubuntu-24.04 -u root` puis `cd /opt/conformite` |
| État des services | 🐧 | `docker compose --profile api --profile interface ps` |
| Erreurs de l'application | 🐧 | `docker compose logs --tail 100 api` |
| Mistral chargé ? | 🐧 | `ollama ps` |
| Journal de Mistral | 🐧 | `journalctl -u ollama -n 50` |
| Tout vérifier | 🐧 | `bash scripts/verifier_installation.sh` |

---

## Partie F — Mises à jour (quand Taha envoie une nouvelle version)

**Cas 1 : le serveur a accès à GitHub.**

**🪟 Windows**
```powershell
wsl -d Ubuntu-24.04 -u root
```
**🐧 Ubuntu**
```bash
cd /opt/conformite
bash scripts/mettre_a_jour.sh
bash scripts/verifier_installation.sh
```

**Cas 2 : Taha envoie un fichier `maj.bundle`.** Copiez-le dans `C:\conformite-install\`, puis :

**🐧 Ubuntu**
```bash
cd /opt/conformite
bash scripts/mettre_a_jour.sh /mnt/c/conformite-install/maj.bundle
bash scripts/verifier_installation.sh
```

La mise à jour fait d'abord une sauvegarde. Elle ne touche jamais aux dossiers, aux validations, aux documents reçus ni à la clé. Elle se termine par un **rapport** encadré, sans secret, à envoyer à Taha. **Ne modifiez jamais les fichiers de l'outil à la main** : la mise à jour suivante refuserait de s'appliquer.

---

## Partie G — Dépannage

| Symptôme | Cause | Solution |
|---|---|---|
| `[X] La virtualisation est désactivée dans le BIOS` | VT-x / AMD-V désactivé | Partie A1 |
| `[X] WSL n'a pas pu être mis à jour` | pas d'accès à GitHub/Microsoft | autoriser les sites (A3), ou télécharger `wsl.x64.msi` sur https://github.com/microsoft/WSL/releases depuis un autre poste, l'installer (double-clic), puis relancer le script |
| `[X] Le port 80 est déjà utilisé` | IIS ou un autre site web | relancer avec ` -Port 8080` |
| `[X] systemd ne démarre pas dans Ubuntu` | WSL trop ancien | 🪟 `wsl --update --web-download`, puis relancer le script |
| Le script est bloqué sur « exécution de scripts désactivée » | stratégie PowerShell | utiliser exactement la commande du guide (`-ExecutionPolicy Bypass`) |
| Page inaccessible depuis les postes, mais OK sur le serveur | pare-feu réseau ou profil « Public » | 🪟 `Get-NetConnectionProfile` : le réseau doit être *Domain* ou *Private* ; sinon prévenir le service informatique |
| Page inaccessible même sur le serveur après un redémarrage | Ubuntu non démarré | 🪟 `Start-ScheduledTask -TaskName ConformiteDM-Demarrage`, attendre 3 min, lire `demarrage.log` |
| « Serveur hors ligne » dans le tableau de bord | application arrêtée | 🐧 `docker compose --profile api --profile interface up -d` |
| Rédaction en erreur « Mistral a échoué deux fois » | Mistral surchargé ou mémoire pleine | cliquer **Relancer la rédaction** ; si ça se répète : 🐧 `free -h` et `journalctl -u ollama -n 100`, puis envoyer à Taha |
| Rédaction très lente (> 10 min) | serveur sans carte graphique | normal sur ce type de serveur (3 à 5 min habituellement) ; éviter d'autres programmes lourds |
| Le mot de passe Windows a changé | la tâche planifiée utilise l'ancien | relancer le script d'installation (B3) : il recrée la tâche |

---

## Partie H — À renvoyer à Taha

1. La **sortie du diagnostic** (B3, section « 4. Diagnostic »). Une capture d'écran suffit.
2. La **sortie de la vérification complète** (C4).
3. L'**adresse du tableau de bord** (B3, fin).
4. La **clé d'accès** (C6), **de vive voix uniquement**.

**Ne jamais envoyer** le fichier `.env`, ni le contenu de `config/entreprise.yaml`, ni les dossiers des fournisseurs.

---

## Récapitulatif des commandes

**🪟 Windows — installation (2 fois : avant et après le redémarrage)**
```powershell
powershell -ExecutionPolicy Bypass -File C:\conformite-install\conformite-serveur\conformite\deploiement\windows\installer_windows.ps1 -Zip C:\conformite-install\conformite-serveur.zip
Restart-Computer
```

**🪟 Windows — ouvrir Ubuntu**
```powershell
wsl -d Ubuntu-24.04 -u root
```

**🐧 Ubuntu — configuration**
```bash
cd /opt/conformite
nano config/entreprise.yaml
bash scripts/indexer_modeles.sh
bash scripts/verifier_installation.sh
crontab -e
bash scripts/sauvegarder.sh
grep API_KEY .env
exit
```

**🐧 Ubuntu — mise à jour**
```bash
cd /opt/conformite
bash scripts/mettre_a_jour.sh
bash scripts/verifier_installation.sh
```
