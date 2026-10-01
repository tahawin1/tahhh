# Vérification complète de l'installation (≈ 10 min, ne modifie rien).
. (Join-Path $PSScriptRoot "_commun.ps1")
Titre "Vérification complète de l'outil (ne modifie rien)"
$code = Executer-Dans-Ubuntu "verification" "bash scripts/verifier_installation.sh"
Fin $code
