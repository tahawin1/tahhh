<#
  Installation sur un SERVEUR WINDOWS — préparation de Windows, puis installation
  identique à celle d'un serveur Ubuntu, à l'intérieur d'Ubuntu sous WSL2.

  À lancer dans PowerShell OUVERT EN ADMINISTRATEUR :

    powershell -ExecutionPolicy Bypass -File C:\conformite-install\conformite\deploiement\windows\installer_windows.ps1 `
               -Zip C:\conformite-install\conformite-serveur.zip

  Ce que fait le script (relançable : chaque étape déjà faite est sautée) :
    1. vérifie Windows (WSL2 : Windows Server 2022/2025, Windows 10 2004+ ou 11)
    2. active WSL2 (redémarrage demandé la première fois), le met à jour (le WSL
       intégré à Windows Server 2022 ne gère pas systemd), puis installe Ubuntu
       24.04 — téléchargements directs, sans Microsoft Store
    3. réserve la mémoire de WSL (75 % de la RAM, pour Mistral) et active systemd
    4. copie le paquet dans Ubuntu (/opt/conformite)
    5. lance le diagnostic, puis l'installation (le même script que sous Ubuntu)
    6. ouvre le port du tableau de bord au pare-feu Windows et relaie ce port
       vers Ubuntu ; tâche planifiée au démarrage de Windows (Ubuntu, Docker,
       Mistral et le relais redémarrent seuls)
    7. lance la vérification complète

  Aucun document n'est envoyé hors du serveur ; Mistral tourne dans Ubuntu.
#>
param(
    [string]$Zip = "",
    [int]$Port = 80,
    [string]$Distro = "Ubuntu-24.04"
)

# « Continue » : sous Windows PowerShell 5.1, avec « Stop », un simple message de
# wsl.exe sur la sortie d'erreur interromprait le script. Les erreurs sont
# testées explicitement (codes de retour, -ErrorAction Stop sur les cmdlets).
# Affichage correct des accents envoyés par Ubuntu (UTF-8) dans la console Windows
& chcp.com 65001 | Out-Null  # page de code UTF-8 : sans elle, « vérification » s'affiche « v├®rification »
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = "Continue"
$Dossier = "C:\ProgramData\ConformiteDM"

function Titre($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Ok($t) { Write-Host "  [OK] $t" -ForegroundColor Green }
function Alerte($t) { Write-Host "  [!]  $t" -ForegroundColor Yellow }
function Echec($t) { Write-Host "  [X]  $t" -ForegroundColor Red; exit 1 }

# wsl.exe écrit en UTF-16 : on retire les caractères nuls pour pouvoir comparer
function Wsl-Texte { param([string[]]$Arguments) ((& wsl.exe @Arguments) -join "`n") -replace "`0", "" }
# Chemin Windows -> chemin Linux, calculé ici (pas de wslpath : un shell intermédiaire
# supprimerait les « \ » du chemin Windows). C:\a\b -> /mnt/c/a/b
function Chemin-Linux([string]$Chemin) {
    if ($Chemin -notmatch '^[A-Za-z]:') { return $Chemin }   # déjà un chemin Linux (essais)
    $p = [System.IO.Path]::GetFullPath($Chemin)
    return "/mnt/" + $p.Substring(0, 1).ToLower() + ($p.Substring(2) -replace '\\', '/')
}

# Exécute une commande dans Ubuntu (root) : affiche sa sortie, renvoie SEULEMENT son code de retour
function Dans-Ubuntu {
    param([string]$Commande)
    # --exec : bash est lancé directement, sans shell intermédiaire qui réinterpréterait
    # les « \ », « $ » et guillemets de la commande
    & wsl.exe -d $Distro -u root --exec bash -lc $Commande | Out-Host
    return $LASTEXITCODE
}

# ---------------------------------------------------------------- 1. Windows
Titre "1. Vérification de Windows"
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Echec "Ouvrir PowerShell avec « Exécuter en tant qu'administrateur », puis relancer." }

$os = Get-CimInstance Win32_OperatingSystem
$build = [int]$os.BuildNumber
$ramGo = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Ok "$($os.Caption) (build $build) | mémoire : $ramGo Go"
if ($build -lt 19041) {
    Echec ("Cette version de Windows ne permet pas WSL2 (Windows Server 2019 ou plus ancien). " +
           "Solution : créer une machine virtuelle Ubuntu 24.04 dans Hyper-V (16 Go de mémoire, 80 Go de disque) " +
           "et suivre la fiche d'installation Ubuntu dans cette machine. Prévenir Taha.")
}
if ($ramGo -lt 16) { Alerte "Moins de 16 Go de mémoire : Mistral risque d'être très lent." }
# Machine physique : la virtualisation doit être activée dans le BIOS (Intel VT-x / AMD-V)
$hyperviseur = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
$virtBios = @(Get-CimInstance Win32_Processor | Where-Object { $_.VirtualizationFirmwareEnabled }).Count -gt 0
if (-not $hyperviseur -and -not $virtBios) {
    Echec ("La virtualisation est désactivée dans le BIOS/UEFI du serveur. Redémarrer, entrer dans le BIOS " +
           "(souvent F2, F10 ou Suppr), activer « Intel Virtualization Technology (VT-x) » ou « AMD-V / SVM », " +
           "enregistrer, puis relancer ce script.")
}
Ok "Virtualisation matérielle disponible"
if ((Get-CimInstance Win32_ComputerSystem).Model -match "Virtual|VMware|KVM") {
    Alerte "Ce serveur est lui-même une machine virtuelle : la « virtualisation imbriquée » doit être activée sur l'hôte (sinon WSL2 ne démarre pas)."
}
$libreGo = [math]::Floor((Get-PSDrive C).Free / 1GB)
if ($libreGo -lt 60) { Alerte "Seulement $libreGo Go libres sur C: (Ubuntu, modèles et dossiers y sont stockés) : 60 Go conseillés." }
else { Ok "Disque C: : $libreGo Go libres" }

if (-not $Zip) {
    foreach ($c in @((Join-Path $PSScriptRoot "..\..\..\conformite-serveur.zip"), (Join-Path $PSScriptRoot "..\..\..\..\conformite-serveur.zip"), "$HOME\Downloads\conformite-serveur.zip")) {
        if (Test-Path $c) { $Zip = (Resolve-Path $c).Path; break }
    }
}
if (-not $Zip -or -not (Test-Path $Zip)) { Echec "Paquet introuvable : indiquer -Zip C:\chemin\conformite-serveur.zip" }
$Zip = (Resolve-Path $Zip).Path
Ok "Paquet : $Zip"

$occupe = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.OwningProcess -ne 0 } | Select-Object -First 1
if ($occupe -and -not (Get-Content "$Dossier\port.txt" -ErrorAction SilentlyContinue)) {
    $nom = (Get-Process -Id $occupe.OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Echec "Le port $Port est déjà utilisé sur ce serveur (programme : $nom, souvent IIS). Relancer avec -Port 8080."
}

# ---------------------------------------------------------------- 2. WSL2 et Ubuntu
Titre "2. WSL2 et Ubuntu"
# Windows Server 2022 : pas de Microsoft Store -> téléchargements directs (--web-download)
$fonctions = @("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform")
$manquantes = @($fonctions | Where-Object { (Get-WindowsOptionalFeature -Online -FeatureName $_).State -ne "Enabled" })
if ($manquantes.Count -gt 0 -or -not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Write-Host "  Activation des composants Windows : $($fonctions -join ', ')…"
    foreach ($f in $fonctions) { Enable-WindowsOptionalFeature -Online -FeatureName $f -All -NoRestart -ErrorAction Stop | Out-Null }
    Alerte "Composants WSL2 activés : REDÉMARRER le serveur, puis relancer ce même script."
    exit 0
}
# Le WSL intégré à Windows Server 2022 est trop ancien pour systemd : mise à jour obligatoire
Write-Host "  Mise à jour de WSL (téléchargement direct)…"
& wsl.exe --update --web-download | Out-Host
$version = Wsl-Texte @("--version")
if ($LASTEXITCODE -ne 0 -or $version -notmatch "WSL[^\d]*(\d+)\.(\d+)") {
    Echec ("WSL n'a pas pu être mis à jour (sans accès Internet ?). Installer à la main le paquet " +
           "« wsl.x64.msi » de https://github.com/microsoft/WSL/releases (dernière version), puis relancer ce script.")
}
& wsl.exe --set-default-version 2 | Out-Null
Ok "WSL2 à jour ($($version.Split("`n")[0].Trim()))"

# Mémoire de WSL : 75 % de la RAM (par défaut 50 %, trop peu pour Mistral + base + index)
$wslconfig = "$env:USERPROFILE\.wslconfig"
if (-not (Test-Path $wslconfig)) {
    $mem = [math]::Max(8, [math]::Floor($ramGo * 0.75))
    "[wsl2]`r`nmemory=${mem}GB`r`nswap=8GB`r`n# conformité DM : réglé par installer_windows.ps1`r`n" | Set-Content -Encoding ASCII $wslconfig
    Ok "Mémoire réservée à Ubuntu : $mem Go ($wslconfig)"
} else { Ok "Réglages WSL existants conservés ($wslconfig)" }

$distros = Wsl-Texte @("-l", "-q")
if ($distros -notmatch [regex]::Escape($Distro)) {
    Write-Host "  Installation d'Ubuntu ($Distro)…"
    Write-Host "  >>> Une invite Ubuntu va demander un NOM D'UTILISATEUR et un MOT DE PASSE :" -ForegroundColor Yellow
    Write-Host "  >>> choisissez-les (à noter), puis tapez  exit  pour revenir ici." -ForegroundColor Yellow
    & wsl.exe --install -d $Distro --web-download
    $distros = Wsl-Texte @("-l", "-q")
    if ($distros -notmatch [regex]::Escape($Distro)) { Echec "Ubuntu n'a pas été installé (voir le message ci-dessus)." }
}
Ok "Ubuntu installé ($Distro)"

# systemd (Docker et Ollama sont des services) — appliqué au redémarrage de WSL
$pid1 = (& wsl.exe -d $Distro -u root -- ps -p 1 -o comm=) -join ""
if ($pid1.Trim() -ne "systemd") {
    Dans-Ubuntu "grep -q '^systemd=true' /etc/wsl.conf 2>/dev/null || printf '[boot]\nsystemd=true\n' >> /etc/wsl.conf" | Out-Null
    & wsl.exe --shutdown
    Start-Sleep -Seconds 8
    $pid1 = (& wsl.exe -d $Distro -u root -- ps -p 1 -o comm=) -join ""
    if ($pid1.Trim() -ne "systemd") { Echec "systemd ne démarre pas dans Ubuntu (mettre WSL à jour : wsl --update)." }
}
Ok "systemd actif dans Ubuntu"

# ---------------------------------------------------------------- 3. Copie du paquet
Titre "3. Copie du paquet dans Ubuntu (/opt/conformite)"
if ((Dans-Ubuntu "test -d /opt/conformite/.git") -eq 0) {
    Ok "Déjà présent : conservé (mettre à jour avec scripts/mettre_a_jour.sh, voir la fiche §10)"
} else {
    $zipLinux = Chemin-Linux $Zip
    $code = Dans-Ubuntu "apt-get update -qq && apt-get install -y -qq unzip git curl >/dev/null && unzip -q '$zipLinux' -d /opt && test -d /opt/conformite/.git"
    if ($code -ne 0) { Echec "Décompression du paquet impossible dans Ubuntu." }
    Ok "Paquet décompressé dans /opt/conformite"
}
# dossiers acceptés : déposables depuis l'Explorateur Windows (\\wsl.localhost\...) par l'utilisateur Ubuntu
Dans-Ubuntu "mkdir -p /opt/conformite/data/dossiers_valides && chown -R 1000:1000 /opt/conformite/data/dossiers_valides" | Out-Null

# ---------------------------------------------------------------- 4. Diagnostic puis installation
Titre "4. Diagnostic (ne modifie rien)"
Dans-Ubuntu "cd /opt/conformite && bash scripts/installer_serveur.sh --verifier" | Out-Null
$reponse = Read-Host "  Continuer l'installation complète (~1 h) ? (O/N)"
if ($reponse -notmatch "^[oOyY]") { Write-Host "  Arrêt demandé. Relancer ce script pour reprendre."; exit 0 }

Titre "5. Installation dans Ubuntu (Docker, Ollama + Mistral, base, API, tableau de bord, indexation)"
$code = Dans-Ubuntu "cd /opt/conformite && INTERFACE_PORT=$Port bash scripts/installer_serveur.sh"
if ($code -ne 0) { Echec "L'installation s'est arrêtée (message ci-dessus). Corriger puis relancer ce script : il reprend où il s'était arrêté." }

# ---------------------------------------------------------------- 6. Réseau et démarrage automatique
Titre "6. Accès depuis le réseau et démarrage automatique"
New-Item -ItemType Directory -Force -Path $Dossier | Out-Null
Copy-Item -Force -ErrorAction Stop (Join-Path $PSScriptRoot "demarrer_conformite.ps1") "$Dossier\demarrer_conformite.ps1"
"$Port" | Set-Content -Encoding ASCII "$Dossier\port.txt"
"$Distro" | Set-Content -Encoding ASCII "$Dossier\distribution.txt"

if (-not (Get-NetFirewallRule -DisplayName "Conformite DM - tableau de bord" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "Conformite DM - tableau de bord" -Direction Inbound -Protocol TCP `
        -LocalPort $Port -Action Allow -Profile Domain, Private -ErrorAction Stop | Out-Null
}
Ok "Pare-feu Windows : port $Port ouvert (réseaux du domaine et privés)"

Write-Host "  La tâche de démarrage tourne sous VOTRE compte Windows : saisissez son mot de passe."
$cred = Get-Credential -UserName "$env:USERDOMAIN\$env:USERNAME" -Message "Compte qui lance Ubuntu au démarrage du serveur"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Dossier\demarrer_conformite.ps1`""
$declencheur = New-ScheduledTaskTrigger -AtStartup
$reglages = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "ConformiteDM-Demarrage" -Action $action -Trigger $declencheur -Settings $reglages `
    -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Highest -Force -ErrorAction Stop | Out-Null
Start-ScheduledTask -TaskName "ConformiteDM-Demarrage"
Ok "Tâche « ConformiteDM-Demarrage » créée et lancée (démarre Ubuntu et le relais du port $Port à chaque démarrage)"

Start-Sleep -Seconds 15
try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 "http://127.0.0.1:$Port/api/health"
    if ($r.Content -match '"statut":"ok"') { Ok "Tableau de bord joignable depuis Windows (port $Port)" }
    else { Alerte "Réponse inattendue du tableau de bord : $($r.Content)" }
} catch { Alerte "Tableau de bord pas encore joignable depuis Windows : voir $Dossier\demarrage.log" }

# ---------------------------------------------------------------- 6 bis. Outils Windows
Titre "6 bis. Outils (C:\ConformiteDM)"
$Outils = "C:\ConformiteDM"
foreach ($d in @("$Outils\outils", "$Outils\rapports", "$Outils\maj", "$Outils\sauvegardes")) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}
Copy-Item -Force (Join-Path $PSScriptRoot "outils\*.ps1") "$Outils\outils\"
Copy-Item -Force (Join-Path $PSScriptRoot "outils\*.cmd") "$Outils\"
# sauvegardes : contiennent la clé d'accès -> administrateurs et système uniquement (SID, quelle que soit la langue)
& icacls.exe "$Outils\sauvegardes" /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" | Out-Null
# raccourci sur le bureau de tous les utilisateurs
$raccourci = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:PUBLIC\Desktop\Conformite DM.lnk")
$raccourci.TargetPath = $Outils
$raccourci.Save()
Ok "Outils installés dans $Outils (raccourci « Conformite DM » sur le bureau)"

$reponse = Read-Host "  Remplir maintenant le profil de l'entreprise (raison sociale, adresse, ICE…) ? (O/N)"
if ($reponse -match "^[oOyY]") {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Outils\outils\Configurer-entreprise.ps1"
}

# ---------------------------------------------------------------- 7. Vérification complète
Titre "7. Vérification complète (≈10 min, ne modifie rien)"
Dans-Ubuntu "cd /opt/conformite && bash scripts/verifier_installation.sh" | Out-Null

$ip = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch "^(127\.|169\.254\.)" -and $_.InterfaceAlias -notmatch "vEthernet|WSL|Loopback" } |
    Select-Object -First 1 -ExpandProperty IPAddress
$suffixe = ""
if ($Port -ne 80) { $suffixe = ":$Port" }
Titre "Terminé"
Write-Host "  Tableau de bord : http://$ip$suffixe   (depuis les postes du réseau de l'entreprise)"
Write-Host "  Outils (double-clic) : dossier C:\ConformiteDM — raccourci « Conformite DM » sur le bureau"
Write-Host "     1 Etat du serveur | 2 Profil de l'entreprise | 3 Deposer les dossiers acceptes | 4 Indexer les modeles"
Write-Host "     5 Verification complete | 6 Mettre a jour | 7 Sauvegarder | 8 Redemarrer | 9 Cle d'acces"
Write-Host "  Rapports de chaque outil : C:\ConformiteDM\rapports"
