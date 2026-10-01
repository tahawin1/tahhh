@echo off
rem Variante si le port 80 est deja utilise (IIS) : tableau de bord sur le port 8080.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer_depuis_cle.ps1" -Port 8080
