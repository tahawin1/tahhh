@echo off
rem Outil de conformite DM : lance outils\Jenkins.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\Jenkins.ps1"
