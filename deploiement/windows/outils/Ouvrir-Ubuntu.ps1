# Ouvre le terminal Ubuntu (administrateur), directement dans /opt/conformite.
. (Join-Path $PSScriptRoot "_commun.ps1")
Verifier-Ubuntu
Write-Host "Terminal Ubuntu (root) dans /opt/conformite — taper « exit » pour fermer."
& wsl.exe -d $Distro -u root --cd /opt/conformite
