# Saisie du profil de l'entreprise (en-tête et pied de page des courriers rédigés).
# Pour chaque rubrique : Entrée seule = garder la valeur actuelle entre crochets.
. (Join-Path $PSScriptRoot "_commun.ps1")
Verifier-Ubuntu
Titre "Profil de l'entreprise (repris dans les courriers)"
$rubriques = [ordered]@{
    raison_sociale     = "Raison sociale"
    ville              = "Ville (lieu indiqué avant la date des lettres)"
    adresse            = "Adresse complète"
    telephone          = "Téléphone"
    representant_legal = "Représentant légal (nom affiché sous la signature)"
    ice                = "ICE"
    identifiant_fiscal = "Identifiant fiscal (IF)"
    registre_commerce  = "Registre de commerce (RC)"
    patente            = "Patente"
    banque_rib         = "Banque et RIB (si souhaité en pied de page, sinon laisser vide)"
}
# valeurs actuelles (lignes « cle: "valeur" »)
$actuel = @{}
$texte = (& wsl.exe -d $Distro -u root -- cat /opt/conformite/config/entreprise.yaml) -join "`n"
foreach ($l in $texte -split "`n") {
    if ($l -match '^\s*([a-z_]+)\s*:\s*"(.*)"\s*(#.*)?$') { $actuel[$Matches[1]] = $Matches[2] }
}
$lignes = @("# Profil de l'établissement demandeur — saisi avec Configurer-entreprise.ps1 le $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
foreach ($cle in $rubriques.Keys) {
    $defaut = $actuel[$cle]
    if ($defaut -match "^NOM DE L|^Ville$|^Adresse complète$|^Nom du représentant légal$") { $defaut = "" }  # valeurs d'exemple
    $saisie = Read-Host "$($rubriques[$cle]) [$defaut]"
    if (-not $saisie) { $saisie = $defaut }
    $saisie = $saisie.Trim() -replace '\\', '/' -replace '"', "'"   # pas de caractère qui casserait le fichier
    $lignes += "${cle}: `"$saisie`""
}
Write-Host ""
$lignes | Select-Object -Skip 1 | ForEach-Object { Write-Host "  $_" }
$ok = Read-Host "Enregistrer ce profil ? (O/N)"
if ($ok -notmatch "^[oOyY]") { Write-Host "Rien n'a été modifié."; Fin 0 }
$tmp = Join-Path $Racine "entreprise.tmp.yaml"
[System.IO.File]::WriteAllLines($tmp, $lignes, (New-Object System.Text.UTF8Encoding($false)))
& wsl.exe -d $Distro -u root -- bash -lc "cp `$(wslpath -a '$tmp') /opt/conformite/config/entreprise.yaml && chmod 600 /opt/conformite/config/entreprise.yaml" | Out-Host
$code = $LASTEXITCODE
Remove-Item -Force $tmp -ErrorAction SilentlyContinue
if ($code -eq 0) { Write-Host "Profil enregistré. Il sera utilisé pour les prochaines rédactions." -ForegroundColor Green }
Fin $code
