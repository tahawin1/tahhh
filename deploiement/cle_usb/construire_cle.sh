#!/usr/bin/env bash
# Prépare le dossier à copier sur la clé USB pour installer le serveur Windows.
#
#   bash deploiement/cle_usb/construire_cle.sh DOSSIER_SORTIE
#
# Produit DOSSIER_SORTIE/CLE-USB-ConformiteDM/ : paquet (clone de la branche
# avec son historique, relié à GitHub), empreinte, lanceurs, lisez-moi, guide.
set -euo pipefail
RACINE=$(cd "$(dirname "$0")/../.." && pwd)
SORTIE="${1:?dossier de sortie}/CLE-USB-ConformiteDM"
BRANCHE=$(git -C "$RACINE" rev-parse --abbrev-ref HEAD)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$SORTIE"
git clone -q --single-branch --branch "$BRANCHE" "$RACINE" "$TMP/conformite"
git -C "$TMP/conformite" remote set-url origin https://github.com/tahawin1/tahhh.git
( cd "$TMP" && zip -qr -X conformite-serveur.zip conformite )
cp "$TMP/conformite-serveur.zip" "$SORTIE/"
sha256sum "$SORTIE/conformite-serveur.zip" | cut -c1-64 | tr 'a-f' 'A-F' > "$SORTIE/empreinte-sha256.txt"
cp "$RACINE"/deploiement/cle_usb/{INSTALLER.cmd,INSTALLER-port-8080.cmd,installer_depuis_cle.ps1,LISEZ-MOI.txt} "$SORTIE/"
cp "$RACINE/GUIDE_INSTALLATION_WINDOWS.md" "$SORTIE/"
echo "Clé prête : $SORTIE (version $(git -C "$RACINE" rev-parse --short HEAD))"
ls -la "$SORTIE"
