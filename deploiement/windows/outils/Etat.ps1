# État du serveur en un coup d'œil (ne modifie rien).
. (Join-Path $PSScriptRoot "_commun.ps1")
Titre "État de l'outil de conformité"

$liste = ((& wsl.exe -l -v) -join "`n") -replace "`0", ""
$ligne = ($liste -split "`n" | Where-Object { $_ -match [regex]::Escape($Distro) } | Select-Object -First 1)
if ($ligne -match "Running") { Write-Host "  [OK] Ubuntu démarré" -ForegroundColor Green }
else { Write-Host "  [X]  Ubuntu arrêté : lancer « 8 - Redemarrer l'outil.cmd »" -ForegroundColor Red }

$tache = Get-ScheduledTask -TaskName "ConformiteDM-Demarrage" -ErrorAction SilentlyContinue
if ($tache) { Write-Host "  [OK] Tâche de démarrage automatique : $($tache.State)" -ForegroundColor Green }
else { Write-Host "  [X]  Tâche de démarrage automatique absente : relancer installer_windows.ps1" -ForegroundColor Red }

$relais = (& netsh.exe interface portproxy show v4tov4) -join "`n"
if ($relais -match "\b$Port\b") { Write-Host "  [OK] Relais réseau du port $Port actif" -ForegroundColor Green }
else { Write-Host "  [X]  Relais réseau du port $Port absent : lancer « 8 - Redemarrer l'outil.cmd »" -ForegroundColor Red }

try {
    $sante = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 "http://127.0.0.1:$Port/api/health").Content
    if ($sante -match '"postgres":true,"qdrant":true,"ollama":true') {
        Write-Host "  [OK] Tableau de bord, base, index et Mistral répondent" -ForegroundColor Green
    } else { Write-Host "  [!]  Réponse partielle : $sante" -ForegroundColor Yellow }
} catch { Write-Host "  [X]  Tableau de bord injoignable sur le port $Port" -ForegroundColor Red }

$journal = Join-Path $Parametres "demarrage.log"
if (Test-Path $journal) {
    Write-Host ""
    Write-Host "Dernières lignes du journal de démarrage ($journal) :"
    Get-Content $journal -Tail 5 | ForEach-Object { Write-Host "    $_" }
}
$sauvegardes = Get-ChildItem (Join-Path $Racine "sauvegardes") -Filter "base_*.dump" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ""
if ($sauvegardes) { Write-Host "Dernière sauvegarde copiée sur Windows : $($sauvegardes.Name)" }
else { Write-Host "Aucune sauvegarde copiée sur Windows pour l'instant." }
Fin 0
