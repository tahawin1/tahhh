# Agent IA — Conformité documentaire dispositifs médicaux

Génère, sous contrôle humain obligatoire, les documents de conformité
requis pour l'importation de dispositifs médicaux au Maroc, selon le pays
d'origine du fournisseur (Chine, Inde, Union européenne, autre).

Voir **CLAUDE.md** pour le cahier des charges complet et le contexte du
projet — à lire avant toute modification.

## Démarrage rapide (pilote local)

### 1. Installer les dépendances Python
```bash
pip install --break-system-packages -r requirements.txt
```

### 2. Démarrer PostgreSQL et Qdrant
```bash
docker compose up -d
```

### 3. Installer et démarrer Mistral via Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
ollama serve &
```

### 4. Vérifier le moteur de règles (ne nécessite aucune infra)
```bash
python3 src/rule_engine.py
```
Affiche, pour chaque pays d'origine (Chine/Inde/UE/autre), la liste des
documents requis pour un dossier marocain — logique 100% déterministe,
sans appel au LLM.

### 5. Indexer les textes réglementaires (nécessite Qdrant démarré)
```bash
./scripts/indexer_tout.sh
```

**Note OCR importante (vérifié sur ce projet) :** la Loi 84-12 et les
Arrêtés 2853-2856 (`data/raw_pdfs/maroc_loi_84-12.pdf` et
`maroc_arretes_2853-2856.pdf`) sont des **scans sans couche de texte** —
l'extraction directe retourne 0 caractère. `src/ingest.py` bascule
automatiquement en OCR (Tesseract, français) page par page quand c'est le
cas. Prérequis système :
```bash
apt-get install -y tesseract-ocr tesseract-ocr-fra
pip install --break-system-packages pytesseract pillow
```
Comptez environ 20 secondes par page scannée. Les autres textes (Décret
2-14-607, Order 739 chinois, les 3 textes indiens) sont en texte natif et
s'extraient instantanément.

### 6. Générer un dossier complet (nécessite Qdrant + Ollama démarrés)
```bash
python3 src/generate.py --pays-origine chine --produit "Prothèse orthopédique de hanche" --classe IIB
```
Les fichiers `.docx` générés apparaissent dans `output/`.

## Structure du projet

```
agent-conformite-dm/
├── CLAUDE.md              # Cahier des charges résumé — à lire en premier
├── data/raw_pdfs/         # Textes réglementaires sources (Maroc, Chine, Inde, UE)
├── rules/                 # Règles par pays, versionnées (YAML)
│   ├── maroc.yaml
│   ├── chine.yaml
│   ├── inde.yaml
│   └── union_europeenne.yaml
├── src/
│   ├── rule_engine.py     # Décide les documents requis (déterministe)
│   ├── ingest.py          # Extraction + indexation dans Qdrant (RAG)
│   └── generate.py        # RAG + Mistral + génération DOCX
├── scripts/
│   └── indexer_tout.sh    # Indexe tous les textes en une commande
├── output/                # Documents générés (dossiers de sortie)
└── docker-compose.yml     # PostgreSQL + Qdrant
```

## Principe de fonctionnement

1. **Rule Engine** (`src/rule_engine.py`) détermine, sans IA, quels
   documents sont requis selon le pays d'origine du fournisseur — logique
   codée en YAML, jamais laissée au LLM.
2. **RAG** (`src/ingest.py` + Qdrant) retrouve des extraits réels des
   textes réglementaires et des dossiers déjà réalisés, pertinents pour le
   document à produire.
3. **Mistral** (`src/generate.py`, via Ollama) rédige le contenu de chaque
   document en s'appuyant sur ces extraits — jamais "de mémoire".
4. **Validation humaine obligatoire** avant tout dépôt — ce repo ne
   contient volontairement aucune fonction de dépôt automatique.

## Ce qui a été vérifié dans ce sandbox, et ce qui reste à toi

Cet environnement de développement bloque l'accès à Docker Hub (politique
réseau de ce container) — impossible d'y tirer les images `qdrant/qdrant`
et `postgres`. Sur ta propre machine ou ton serveur, ce blocage n'existe
pas.

**Déjà vérifié ici, avec les vrais textes que tu as fournis :**
- Extraction de texte natif (Décret marocain, Order 739 chinois, textes
  indiens) — fonctionne directement
- Détection automatique des PDF scannés + bascule OCR (Loi 84-12, Arrêtés
  2853-2856) — fonctionne, ~20s/page
- Découpage en chunks — fonctionne
- Génération de fichiers DOCX — fonctionne
- Moteur de règles (`rule_engine.py`) — testé sur les 4 pays, produit la
  bonne liste de documents avec les bons flags traduction/légalisation
- Calcul du prochain créneau de dépôt (mercredi/jeudi) — fonctionne

**À faire sur ta machine (nécessite Docker Hub + GPU/CPU pour Mistral) :**
```bash
docker compose up -d        # démarre Qdrant + PostgreSQL
ollama serve && ollama pull mistral
./scripts/indexer_tout.sh   # indexe tous les textes (OCR inclus, prévoir ~10-15 min)
python3 src/generate.py --pays-origine chine --produit "Prothèse orthopédique de hanche" --classe IIB
```

## Prochaines étapes (voir CLAUDE.md section 7)

- Tester le pipeline complet sur un dossier réel connu
- Construire l'interface de validation humaine (React + FastAPI)
- Ajouter Keycloak (authentification) avant toute mise en production
