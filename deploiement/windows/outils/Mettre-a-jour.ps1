# Mise à jour de l'outil, puis vérification complète.
#   Depuis GitHub          : double-clic sur « 6 - Mettre a jour.cmd »
#   Depuis un fichier .bundle remis par Taha : le copier dans C:\ConformiteDM\maj\
#   (le plus récent est utilisé automatiquement)
param([string]$Bundle = "")
. (Join-Path $PSScriptRoot "_commun.ps1")
Titre "Mise à jour de l'outil"
if (-not $Bundle) {
    $Bundle = Get-ChildItem (Join-Path $Racine "maj") -Filter *.bundle -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if ($Bundle) {
    Write-Host "Fichier de mise à jour : $Bundle"
    # copie sous un nom sans espace (ex. « maj (1).bundle » téléchargé deux fois)
    $enCours = Join-Path $Racine "maj\en_cours.bundle"
    Copy-Item -Force $Bundle $enCours
    $source = "'$(Chemin-Linux $enCours)'"
} else {
    Write-Host "Aucun fichier .bundle dans $Racine\maj : mise à jour depuis GitHub."
    $source = ""
}
$cmd = "bash scripts/mettre_a_jour.sh $source && bash scripts/verifier_installation.sh"
$code = Executer-Dans-Ubuntu "mise_a_jour" $cmd
# les outils Windows eux-mêmes sont rafraîchis depuis le code à jour, même si la
# vérification a un point rouge ; copiés par Windows (\\wsl.localhost) et non par
# Ubuntu dans /mnt/c, qui échoue parfois (« Input/output error »)
$paquet = "\\wsl.localhost\$Distro\opt\conformite\deploiement\windows\outils"
try {
    Copy-Item -Force (Join-Path $paquet "*.ps1") (Join-Path $Racine "outils") -ErrorAction Stop
    Copy-Item -Force (Join-Path $paquet "*.cmd") $Racine -ErrorAction Stop
    Write-Host "Outils Windows mis à jour dans $Racine" -ForegroundColor Green
} catch {
    Write-Host "Outils Windows non recopiés : $($_.Exception.Message)" -ForegroundColor Yellow
}
Remove-Item -Force (Join-Path $Racine "maj\en_cours.bundle") -ErrorAction SilentlyContinue
if ($code -eq 0 -and $Bundle) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Racine "maj\appliques") | Out-Null
    Move-Item -Force $Bundle (Join-Path $Racine "maj\appliques")
}
Fin $code
