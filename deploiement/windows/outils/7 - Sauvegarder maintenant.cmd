@echo off
rem Outil de conformite DM : lance outils\Sauvegarder.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\Sauvegarder.ps1"
