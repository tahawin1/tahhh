# Ouvre, dans l'Explorateur Windows, le dossier où déposer les dossiers acceptés :
#   <pays d'origine>\<produit>\<fichiers PDF numérotés : 1-…, 2-…, 16-…>
. (Join-Path $PSScriptRoot "_commun.ps1")
Verifier-Ubuntu
& wsl.exe -d $Distro -u root -- bash -lc "mkdir -p /opt/conformite/data/dossiers_valides/union_europeenne /opt/conformite/data/dossiers_valides/chine /opt/conformite/data/dossiers_valides/inde /opt/conformite/data/dossiers_valides/autre && chown -R 1000:1000 /opt/conformite/data/dossiers_valides" | Out-Host
$chemin = "\\wsl.localhost\$Distro\opt\conformite\data\dossiers_valides"
Write-Host "Ouverture de : $chemin"
Write-Host ""
Write-Host "1. Ouvrir le dossier du pays d'origine (union_europeenne, chine, inde, autre)."
Write-Host "2. Y créer un dossier par produit (ex. « Ciment osseux »)."
Write-Host "3. Y copier les PDF du dossier accepté SANS les renommer (1-…, 2-…, 16-…)."
Write-Host "4. Puis double-cliquer sur « 4 - Indexer les modeles.cmd »."
Start-Process explorer.exe $chemin
Fin 0
