<#
  Lancé par INSTALLER.cmd depuis la clé USB. Copie le paquet sur le disque du
  serveur, vérifie qu'il est intact, l'extrait, puis lance l'installation.
  À relancer de la même façon après le redémarrage demandé.
#>
param([int]$Port = 80)
# Affichage correct des accents envoyés par Ubuntu (UTF-8) dans la console Windows
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ErrorActionPreference = "Continue"
$Cle = $PSScriptRoot
$Dest = "C:\conformite-install"

# droits administrateur : relance automatique avec élévation
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    # chemin entre guillemets : la clé peut être copiée dans un dossier contenant des espaces
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Port $Port"
    exit 0
}

Write-Host "== Copie du paquet depuis la clé ($Cle) vers $Dest" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item -Force "$Cle\conformite-serveur.zip" "$Dest\conformite-serveur.zip"
Copy-Item -Force "$Cle\GUIDE_INSTALLATION_WINDOWS.html" "$Dest\" -ErrorAction SilentlyContinue

$attendu = (Get-Content "$Cle\empreinte-sha256.txt" | Select-Object -First 1).Trim().ToUpper()
$obtenu = (Get-FileHash "$Dest\conformite-serveur.zip" -Algorithm SHA256).Hash
if ($obtenu -ne $attendu) {
    Write-Host "  [X] Paquet abîmé (empreinte différente) : recopier la clé depuis le fichier envoyé par Taha." -ForegroundColor Red
    Read-Host "Appuyer sur Entrée pour fermer" | Out-Null
    exit 1
}
Write-Host "  [OK] Paquet intact (empreinte vérifiée)" -ForegroundColor Green

Expand-Archive "$Dest\conformite-serveur.zip" -DestinationPath "$Dest\conformite-serveur" -Force
$installeur = "$Dest\conformite-serveur\conformite\deploiement\windows\installer_windows.ps1"
if (-not (Test-Path $installeur)) {
    Write-Host "  [X] Extraction incomplète : $installeur introuvable." -ForegroundColor Red
    Read-Host "Appuyer sur Entrée pour fermer" | Out-Null
    exit 1
}
Write-Host "  [OK] Paquet extrait dans $Dest\conformite-serveur" -ForegroundColor Green

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installeur -Zip "$Dest\conformite-serveur.zip" -Port $Port
Write-Host ""
Read-Host "Appuyer sur Entrée pour fermer" | Out-Null
