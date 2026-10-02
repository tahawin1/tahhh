# Installe ou met à jour Jenkins (intégration continue), puis ouvre sa page.
# Le mot de passe administrateur est affiché ici, jamais enregistré dans un rapport.
. (Join-Path $PSScriptRoot "_commun.ps1")
Titre "Jenkins — intégration continue (tests, évaluation de Mistral, déploiement validé)"
$code = Executer-Dans-Ubuntu "jenkins" "bash scripts/installer_jenkins.sh"
if ($code -ne 0) { Fin $code }
$port = ((& wsl.exe -d $Distro -u root --exec bash -lc "grep '^JENKINS_PORT=' /opt/conformite/.env | cut -d= -f2-") -join "").Trim()
if (-not $port) { $port = "8081" }
$motDePasse = ((& wsl.exe -d $Distro -u root --exec bash -lc "grep '^JENKINS_ADMIN_PASSWORD=' /opt/conformite/.env | cut -d= -f2-") -join "").Trim()
Write-Host ""
Write-Host "  Adresse      : http://localhost:$port"
Write-Host "  Compte       : admin"
Write-Host "  Mot de passe : $motDePasse" -ForegroundColor Yellow
Write-Host ""
Write-Host "Ne jamais envoyer ce mot de passe par écrit ni en capture d'écran."
Start-Process "http://localhost:$port"
Fin 0
