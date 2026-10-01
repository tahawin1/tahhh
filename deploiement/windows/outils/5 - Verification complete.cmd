@echo off
rem Outil de conformite DM : lance outils\Verifier.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\Verifier.ps1"
