# Affiche la clé d'accès au tableau de bord (à transmettre de vive voix uniquement).
. (Join-Path $PSScriptRoot "_commun.ps1")
Verifier-Ubuntu
$cle = ((& wsl.exe -d $Distro -u root --exec bash -lc "grep '^API_KEY=' /opt/conformite/.env | cut -d= -f2-") -join "").Trim()
Titre "Clé d'accès au tableau de bord"
if (-not $cle) { Write-Host "Clé introuvable : l'installation est-elle terminée ?" -ForegroundColor Red; Fin 1 }
Write-Host "  $cle" -ForegroundColor Yellow
Write-Host ""
Write-Host "À transmettre DE VIVE VOIX ou par le gestionnaire de mots de passe de l'entreprise."
Write-Host "Ne jamais l'envoyer par e-mail ou messagerie, ne pas l'enregistrer dans un fichier."
Fin 0
