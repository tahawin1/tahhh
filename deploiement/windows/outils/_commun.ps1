<#
  Fonctions communes aux outils du serveur Windows (C:\ConformiteDM\outils).
  Chaque outil fait une seule tâche, dans Ubuntu (WSL2), et enregistre son
  rapport daté dans C:\ConformiteDM\rapports. À lancer avec le compte Windows
  qui a installé l'outil (Ubuntu est rattaché à ce compte).
#>
$ErrorActionPreference = "Continue"   # PowerShell 5.1 : voir installer_windows.ps1
$Racine = "C:\ConformiteDM"
$Parametres = "C:\ProgramData\ConformiteDM"
if ($env:CONFORMITE_RACINE) { $Racine = $env:CONFORMITE_RACINE; $Parametres = $env:CONFORMITE_RACINE }  # essais
$Distro = Get-Content (Join-Path $Parametres "distribution.txt") -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Distro) { $Distro = "Ubuntu-24.04" }
$Port = Get-Content (Join-Path $Parametres "port.txt") -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Port) { $Port = "80" }
$Rapports = Join-Path $Racine "rapports"
New-Item -ItemType Directory -Force -Path $Rapports | Out-Null

function Titre($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan; Write-Host "" }

function Fin([int]$Code = 0) {
    Write-Host ""
    if ($Code -eq 0) { Write-Host "Terminé." -ForegroundColor Green }
    else { Write-Host "Terminé avec une erreur (code $Code) : envoyer le rapport à Taha." -ForegroundColor Red }
    if (-not $env:CONFORMITE_SANS_PAUSE) { Read-Host "Appuyer sur Entrée pour fermer" | Out-Null }
    exit $Code
}

function Verifier-Ubuntu {
    $liste = ((& wsl.exe -l -q) -join "`n") -replace "`0", ""
    if ($liste -notmatch [regex]::Escape($Distro)) {
        Write-Host "Ubuntu ($Distro) est introuvable pour le compte « $env:USERNAME »." -ForegroundColor Red
        Write-Host "Lancer cet outil avec le compte Windows qui a fait l'installation." -ForegroundColor Red
        Fin 1
    }
}

# Exécute une commande dans /opt/conformite (root), l'affiche et l'enregistre,
# sans codes couleur, dans C:\ConformiteDM\rapports\<nom>_<date>.txt.
# Retourne le code de retour de la commande.
function Executer-Dans-Ubuntu([string]$Nom, [string]$Commande) {
    Verifier-Ubuntu
    $fichier = Join-Path $Rapports ("{0}_{1:yyyy-MM-dd_HHmm}.txt" -f $Nom, (Get-Date))
    # Aucun guillemet double dans la commande transmise : PowerShell 5.1 ne les
    # échappe pas en appelant wsl.exe (chemins sans espace, voir $Racine).
    $bash = "cd /opt/conformite && { $Commande ; } 2>&1 | tee /tmp/rapport_outil.txt; code=`${PIPESTATUS[0]}; " +
            "sed -r 's/\x1b\[[0-9;]*m//g' /tmp/rapport_outil.txt > `$(wslpath -a '$fichier'); exit `$code"
    & wsl.exe -d $Distro -u root -- bash -lc $bash | Out-Host
    $code = $LASTEXITCODE
    Write-Host ""
    Write-Host "Rapport enregistré : $fichier"
    return $code
}
