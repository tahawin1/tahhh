#!/usr/bin/env bash
# Indexe dans Qdrant les textes des États-Unis, de la Corée du Sud et du
# Pakistan (et le texte pivot IMDRF) extraits par telecharger_textes_pays.sh.
# Un texte absent est signalé et sauté. Relançable (identifiants stables).
set -uo pipefail
cd "$(dirname "$0")/.."
PYTHON=python3; [ -x .venv/bin/python ] && PYTHON=.venv/bin/python
T=data/raw_pdfs/textes

indexer() {  # fichier pays type date libellé
  if [ ! -s "$T/$1" ]; then echo "  ! $1 absent (lancer scripts/telecharger_textes_pays.sh)"; return; fi
  $PYTHON src/ingest.py --source "$T/$1" --pays "$2" --type-document "$3" --date-version "$4" --texte-source "$5"
}
version_cfr() { grep -F "| $1 |" data/raw_pdfs/SOURCES_PAYS.md 2>/dev/null | grep -o 'édition du [0-9-]*' | cut -d' ' -f3; }

echo "=== États-Unis ==="
for part in 801 803 806 807 812 814 820 830 860 888; do
  indexer "etats_unis_21cfr_${part}.txt" etats_unis reglement "$(version_cfr etats_unis_21cfr_${part}.xml || date +%F)" "21 CFR Part ${part}"
done
echo "=== Corée du Sud ==="
indexer coree_medical_devices_act_2025.txt coree_du_sud loi 2025-04-01 "Medical Devices Act (Act No. 20888, 1-4-2025, traduction KLRI)"
indexer coree_decret_application_2025.txt coree_du_sud decret 2025-07-22 "Enforcement Decree of the Medical Devices Act (Presidential Decree No. 35669, 22-7-2025, traduction KLRI)"
indexer coree_arrete_application_2022.txt coree_du_sud reglement 2022-07-21 "Enforcement Rule of the Medical Devices Act (Ordinance No. 1819, traduction MFDS)"
indexer coree_classification_annexe1_2022.txt coree_du_sud annexe_technique 2020-05-01 "Enforcement Rule, annexe 1 — classification des dispositifs (classes I à IV)"
indexer coree_reglement_autorisation_2022.txt coree_du_sud reglement 2022-07-29 "Regulation on the Permission, Notification, Review of Medical Devices (No. 2022-52)"
indexer coree_bpf_gmp_2026.txt coree_du_sud reglement 2026-02-11 "Medical Device GMP Regulations (MFDS, février 2026)"
echo "=== Pakistan ==="
indexer pakistan_drap_act_2012.txt pakistan loi 2012-11-13 "Drug Regulatory Authority of Pakistan Act, 2012 (Pakistan Code)"
indexer pakistan_medical_devices_rules_2017_maj_2022.txt pakistan reglement 2022-04-30 "Medical Devices Rules 2017 (DRAP, mis à jour jusqu'en avril 2022)"
echo "=== Texte pivot (rapprochement) ==="
# Rapprochement des 7 pays (rules/correspondances.yaml) mis en texte, pour que la
# recherche de Mistral le retrouve comme n'importe quel texte indexé
$PYTHON - <<'PY'
import sys, yaml
sys.path.insert(0, "src")
import correspondances as c
d = c.charger()
lignes = [f"RAPPROCHEMENT DES RÉGLEMENTATIONS DES DISPOSITIFS MÉDICAUX — version {d['version']} du {d['date_version']}"]
for pid, p in d["pays"].items():
    classes = " ; ".join(f"niveau {n} : {', '.join(map(str, v))}" for n, v in p["classes"].items())
    lignes += [f"\n{p['nom']} — autorité {p['autorite']} — {p['texte']}", f"Classes : {classes}",
               f"Preuve de mise sur le marché : {p['preuve_mise_sur_le_marche']}",
               f"Certificat pour l'exportation : {p['certificat_pour_export'] or 'sans objet'}",
               f"Système qualité : {p['systeme_qualite']}", f"Certificats étrangers : {p['equivalence_etrangere']}"]
for t in d["themes"]:
    lignes.append(f"\nThème : {t['question']}")
    lignes += [f"  {d['pays'][pid]['nom']} : {ref}" for pid, ref in (t.get("articles") or {}).items()]
for pid, etapes in d.get("parcours_vers_maroc", {}).items():
    lignes.append(f"\nParcours vers le Maroc — {pid} :")
    lignes += [f"  - {e}" for e in etapes]
open("data/raw_pdfs/textes/correspondances_7_pays.txt", "w", encoding="utf-8").write("\n".join(lignes))
PY
indexer correspondances_7_pays.txt international annexe_technique "$(grep -m1 '^date_version' rules/correspondances.yaml | grep -o '[0-9-]\{10\}')" "Rapprochement des réglementations des 7 pays (rules/correspondances.yaml)"
indexer imdrf_ghtf_sg1_n77_2012_classification.txt international annexe_technique 2012-11-02 "GHTF/SG1/N77:2012 — Principles of Medical Devices Classification"
