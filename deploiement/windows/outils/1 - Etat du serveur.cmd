@echo off
rem Outil de conformite DM : lance outils\Etat.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\Etat.ps1"
