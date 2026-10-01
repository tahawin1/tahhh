@echo off
rem Installation de l outil de conformite DM (droits administrateur demandes).
rem A relancer de la meme facon apres le redemarrage demande par le script.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer_depuis_cle.ps1"
