@echo off
rem Redemarre l'outil (droits administrateur demandes).
powershell.exe -NoProfile -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File %~dp0outils\Redemarrer.ps1'"
