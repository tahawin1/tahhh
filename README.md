# Agent IA — Conformité documentaire dispositifs médicaux

Génère, sous contrôle humain obligatoire, les documents de conformité
requis pour l'importation de dispositifs médicaux au Maroc, selon le pays
d'origine du fournisseur (Chine, Inde, Union européenne, autre).

Voir **CLAUDE.md** pour le cahier des charges complet et le contexte du
projet — à lire avant toute modification.

## Démarrage rapide (pilote local)

### 1. Installer les dépendances Python (environnement virtuel)
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
`scripts/indexer_tout.sh` utilise automatiquement `.venv` s'il existe.

### 2. Démarrer PostgreSQL et Qdrant
```bash
docker compose up -d
```

### 3. Installer et démarrer Mistral (+ bge-m3 pour les embeddings) via Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull mistral   # rédaction des documents
ollama pull bge-m3    # embeddings du RAG (1024 dimensions, multilingue)
```
Les embeddings passent par Ollama par défaut (`EMBEDDING_BACKEND=ollama`) :
pas besoin de torch ni d'accès à Hugging Face. Pour utiliser
sentence-transformers à la place : `EMBEDDING_BACKEND=sentence-transformers`
— mais **la même valeur doit servir à l'indexation et à la génération**
(sinon ré-indexer). Le backend est tracé dans chaque chunk (champ `embedding`).

Variables utiles pour la génération (voir `src/generate.py`) :
`OLLAMA_TIMEOUT` (défaut 900 s — Mistral 7B sur CPU seul rédige ~5 tokens/s),
`OLLAMA_NUM_PREDICT` (longueur max par document, défaut 700 tokens).

### 4. Vérifier le moteur de règles (ne nécessite aucune infra)
```bash
.venv/bin/python src/rule_engine.py
.venv/bin/python -m unittest discover -s tests   # tests du moteur de règles
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
automatiquement en OCR (Tesseract, français) quand c'est le cas — y compris
pour les pages qui n'ont qu'un en-tête en texte et un corps scanné ou
vectorisé (page 2 du Décret 2-14-607 : sans cela, les articles 15 à 19
n'étaient pas indexés). Les pages scannées sont OCRisées en parallèle (un
processus par cœur). Prérequis système :
```bash
apt-get install -y tesseract-ocr tesseract-ocr-fra
```

**Deux corrections de métadonnées faites dans `scripts/indexer_tout.sh` :**
- `data/raw_pdfs/ue_mdr_annexe.txt` n'est **pas** une annexe du MDR
  européen : c'est la version consolidée des *Medical Devices Rules 2017
  indiennes* (amendées jusqu'au G.S.R. 777(E) du 14-10-2022). Il est
  indexé sous `pays=inde`, `date_version=2022-10-14`.
- `ue_mdr_2017-745.txt` est une version **consolidée** du MDR (amendements
  M1 à M8, JO du 29.6.2026) : `date_version=2026-06-29`, et non la date du
  texte d'origine (2017-05-05).

### 6. Générer un dossier complet (nécessite Qdrant + Ollama démarrés)
```bash
.venv/bin/python src/generate.py --pays-origine chine --produit "Prothèse orthopédique de hanche" --classe IIB
```
Les fichiers `.docx` générés apparaissent dans un sous-dossier horodaté de
`output/` (un par dossier). Chaque document porte la mention « en attente
de validation humaine », les flags traduction/légalisation, et la liste
des extraits réglementaires (texte, version, n° d'extrait) utilisés pour
le rédiger — à vérifier lors de la validation.

### 7. Lancer l'API
```bash
.venv/bin/uvicorn src.api:app --reload --port 8000
```
- `GET /health` — état de l'API, de Qdrant et d'Ollama
- `GET /pays` — autorité et classification par pays
- `POST /dossiers/documents-requis` — liste des pièces (moteur de règles seul, instantané)
- `POST /dossiers/generer` — génération complète RAG + Mistral + DOCX
  (long sur CPU : plusieurs minutes par document)

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
│   ├── embeddings.py      # Embeddings bge-m3 (Ollama ou sentence-transformers)
│   ├── ingest.py          # Extraction + OCR + indexation dans Qdrant (RAG)
│   ├── generate.py        # RAG + Mistral + génération DOCX
│   └── api.py             # Backend FastAPI
├── tests/                 # Tests du moteur de règles (unittest)
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
