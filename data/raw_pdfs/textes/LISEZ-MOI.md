# Textes réglementaires en texte brut (lisibles par Mistral, Ollama et les outils)

Chaque fichier est le texte intégral d'un texte officiel de `data/raw_pdfs/`,
extrait automatiquement : texte natif quand le PDF en a un, **OCR (Tesseract)**
pour les pages scannées (textes marocains du Bulletin officiel notamment).
Sources, dates et empreintes : `../SOURCES_PAYS.md` (États-Unis, Corée, Pakistan)
et `scripts/indexer_tout.sh` (Maroc, UE, Chine, Inde).

| Pays | Fichiers |
|---|---|
| Maroc | `maroc_loi_84-12.txt` (OCR), `maroc_decret_2-14-607.txt`, `maroc_arretes_2853-2856.txt` (OCR : 2853 déclaration, 2854 sous-traitance, 2855 enregistrement, 2856 classification, exigences essentielles, langues) |
| Union européenne | `ue_mdr_2017-745.txt` (règlement 2017/745 consolidé) |
| Chine | `chine_order_739.txt` (règlement du Conseil d'État n°739) |
| Inde | `inde_mdr_2017.txt`, `inde_mdr_2017_consolide_2022.txt`, amendements `inde_*` |
| États-Unis | `etats_unis_21cfr_801/803/807/814/820/860.txt` (eCFR, édition du 2026-09-25) |
| Corée du Sud | `coree_medical_devices_act_2025.txt` (loi, KLRI), `coree_arrete_application_2022.txt`, `coree_classification_annexe1_2022.txt`, `coree_reglement_autorisation_2022.txt`, `coree_bpf_gmp_2026.txt` (MFDS) |
| Pakistan | `pakistan_drap_act_2012.txt` (Pakistan Code) — Medical Devices Rules 2017 à obtenir |
| Tous | `correspondances_7_pays.txt` : rapprochement article par article (généré depuis `rules/correspondances.yaml`) |

Indexation dans Qdrant (recherche de Mistral) : `scripts/indexer_tout.sh`
(Maroc, UE, Chine, Inde) puis `scripts/indexer_textes_pays.sh` (les autres).
Une erreur d'OCR possible : en cas de doute, le PDF d'origine fait foi.
