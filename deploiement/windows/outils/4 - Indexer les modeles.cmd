@echo off
rem Outil de conformite DM : lance outils\Indexer-modeles.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\Indexer-modeles.ps1"
