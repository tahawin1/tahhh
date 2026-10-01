# Indexe les dossiers acceptés déposés dans le dossier ouvert par
# « 3 - Deposer les dossiers acceptes.cmd » (modèles de rédaction de Mistral).
. (Join-Path $PSScriptRoot "_commun.ps1")
Titre "Indexation des dossiers acceptés (modèles de Mistral)"
$code = Executer-Dans-Ubuntu "modeles" "bash scripts/indexer_modeles.sh"
Fin $code
