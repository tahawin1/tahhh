<#
  Lancé par la tâche planifiée « ConformiteDM-Demarrage » au démarrage de Windows
  (créée par installer_windows.ps1). Ne pas lancer à la main, sauf dépannage.

  1. démarre Ubuntu (WSL2) : systemd y relance Docker, les conteneurs et Ollama
  2. relaie le port du tableau de bord de Windows vers Ubuntu (l'adresse
     interne d'Ubuntu change à chaque démarrage)
  3. garde Ubuntu allumé (WSL s'arrête sinon quand aucun programme ne l'utilise)
  Journal : C:\ProgramData\ConformiteDM\demarrage.log
#>
$Dossier = "C:\ProgramData\ConformiteDM"
$Journal = "$Dossier\demarrage.log"
$Port = [int](Get-Content "$Dossier\port.txt" -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $Port) { $Port = 80 }
$Distro = (Get-Content "$Dossier\distribution.txt" -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $Distro) { $Distro = "Ubuntu-24.04" }

function Noter($t) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $t" | Add-Content -Encoding UTF8 $Journal }

Noter "Démarrage (port $Port, $Distro)"
# 1. Ubuntu, et attendre son adresse interne
$ip = $null
for ($i = 0; $i -lt 60 -and -not $ip; $i++) {
    $sortie = ((& wsl.exe -d $Distro -u root -- hostname -I) -join " ").Trim()
    if ($sortie -match "^(\d+\.\d+\.\d+\.\d+)") { $ip = $Matches[1] } else { Start-Sleep -Seconds 5 }
}
if (-not $ip) { Noter "ÉCHEC : Ubuntu ne répond pas (wsl -d $Distro)"; exit 1 }
Noter "Ubuntu démarré, adresse interne $ip"

# 2. Relais Windows:port -> Ubuntu:port (service « Assistance IP » requis)
Set-Service -Name iphlpsvc -StartupType Automatic
Start-Service -Name iphlpsvc
& netsh.exe interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 2>$null | Out-Null
& netsh.exe interface portproxy add v4tov4 listenport=$Port listenaddress=0.0.0.0 connectport=$Port connectaddress=$ip | Out-Null
Noter "Relais : 0.0.0.0:$Port -> ${ip}:$Port"

# 3. Garder Ubuntu allumé (cette commande ne se termine jamais ; la tâche reste active)
Noter "Ubuntu maintenu allumé"
& wsl.exe -d $Distro -u root -- sleep infinity
Noter "Ubuntu s'est arrêté (la tâche sera relancée)"
exit 1
