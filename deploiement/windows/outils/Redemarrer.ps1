# Redémarre l'outil (Ubuntu, Docker, Mistral, relais réseau), par exemple
# s'il ne répond plus. Les données ne sont pas touchées. ≈ 3 minutes.
. (Join-Path $PSScriptRoot "_commun.ps1")
Titre "Redémarrage de l'outil"
Write-Host "Arrêt d'Ubuntu…"
& wsl.exe --shutdown
Start-Sleep -Seconds 5
Write-Host "Relance par la tâche de démarrage automatique…"
Start-ScheduledTask -TaskName "ConformiteDM-Demarrage" -ErrorAction SilentlyContinue
if (-not $?) { Write-Host "Tâche introuvable : relancer installer_windows.ps1" -ForegroundColor Red; Fin 1 }
for ($i = 0; $i -lt 36; $i++) {
    Start-Sleep -Seconds 5
    try {
        $r = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$Port/api/health").Content
        if ($r -match '"statut":"ok"') { Write-Host "Outil en ligne." -ForegroundColor Green; Fin 0 }
    } catch { Write-Host "  … en attente ($(($i + 1) * 5) s)" }
}
Write-Host "L'outil ne répond pas après 3 minutes : lancer « 1 - Etat du serveur.cmd » et envoyer le résultat à Taha." -ForegroundColor Red
Fin 1
