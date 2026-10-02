# Ouvre, dans l'Explorateur Windows, le dossier où déposer les dossiers acceptés :
#   <pays d'origine>\<produit>\<fichiers PDF numérotés : 1-…, 2-…, 16-…>
. (Join-Path $PSScriptRoot "_commun.ps1")
Verifier-Ubuntu
& wsl.exe -d $Distro -u root --exec bash -lc "cd /opt/conformite/data && mkdir -p dossiers_valides/union_europeenne dossiers_valides/chine dossiers_valides/inde dossiers_valides/etats_unis dossiers_valides/coree_du_sud dossiers_valides/pakistan dossiers_valides/autre && chown -R 1000:1000 /opt/conformite/data/dossiers_valides" | Out-Host
$chemin = "\\wsl.localhost\$Distro\opt\conformite\data\dossiers_valides"
Write-Host "Ouverture de : $chemin"
Write-Host ""
Write-Host "1. Ouvrir le dossier du pays d'origine (union_europeenne, chine, inde, etats_unis, coree_du_sud, pakistan, autre)."
Write-Host "2. Y créer un dossier par produit AVEC SA CLASSE entre parenthèses (ex. « Ciment osseux (IIb) »)."
Write-Host "3. Y copier les PDF du dossier accepté SANS les renommer (1-…, 2-…, 16-…)."
Write-Host "4. Puis double-cliquer sur « 4 - Indexer les modeles.cmd »."
Start-Process explorer.exe $chemin
Fin 0
