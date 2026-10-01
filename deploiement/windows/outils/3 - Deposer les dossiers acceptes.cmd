@echo off
rem Outil de conformite DM : lance outils\Deposer-dossiers.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\Deposer-dossiers.ps1"
