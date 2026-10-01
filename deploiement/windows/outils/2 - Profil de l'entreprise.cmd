@echo off
rem Outil de conformite DM : lance outils\Configurer-entreprise.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\Configurer-entreprise.ps1"
