@echo off
rem Outil de conformite DM : lance outils\Mettre-a-jour.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\Mettre-a-jour.ps1"
