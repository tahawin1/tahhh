# Sauvegarde immédiate (en plus de la sauvegarde automatique de 2 h du matin).
# Copie dans C:\ConformiteDM\sauvegardes.
. (Join-Path $PSScriptRoot "_commun.ps1")
Titre "Sauvegarde immédiate"
$code = Executer-Dans-Ubuntu "sauvegarde" "bash scripts/sauvegarder.sh"
Fin $code
