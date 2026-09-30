# Briefing total — Agent IA de conformité documentaire (dispositifs médicaux)

Ce document est fait pour être donné tel quel à une session Claude Code
sur ta machine, en complément de `CLAUDE.md` (contexte technique détaillé
déjà présent dans le repo). Il résume tout ce qui a été décidé et déjà
construit, pour que le travail reprenne sans repartir de zéro.

---

## 1. Le projet en une phrase

Un agent IA qui automatise, **sous contrôle humain obligatoire**, la
constitution des dossiers de conformité pour l'importation de dispositifs
médicaux au Maroc, en s'adaptant au pays d'origine du fournisseur (Chine,
Inde, Union européenne, autre), en s'appuyant sur Mistral (IA open source,
self-hosted) et une base documentaire RAG plutôt que sur un modèle
"entraîné" sur la réglementation.

## 2. Ce qui est déjà construit et testé (repo : `agent-conformite-dm/`)

| Composant | Fichier | Statut |
|---|---|---|
| Cahier des charges / contexte projet | `CLAUDE.md` | Fait |
| Règles réglementaires (Maroc, Chine, Inde, UE) | `rules/*.yaml` | Fait, basé sur les vrais textes (Loi 84-12, Décret 2-14-607, Order 739, Medical Devices Rules 2017, MDR 2017/745) |
| Moteur de règles déterministe | `src/rule_engine.py` | Fait et testé — décide seul des documents requis, jamais le LLM |
| Extraction PDF + OCR automatique | `src/ingest.py` | Fait et testé — bascule OCR (Tesseract) quand le PDF est un scan sans texte |
| Indexation Qdrant (RAG) | `src/ingest.py` | Codé, non testé de bout en bout (Qdrant nécessite Docker, bloqué dans le sandbox de développement utilisé jusqu'ici) |
| Génération RAG + Mistral + DOCX | `src/generate.py` | Codé, non testé de bout en bout (nécessite Qdrant + Ollama) |
| **Backend API (FastAPI)** | `src/api.py` | **Fait et testé** — expose le moteur de règles (`/dossiers/documents-requis`) en HTTP, avec un endpoint de génération (`/dossiers/generer`) qui échoue proprement tant que Qdrant/Ollama ne sont pas démarrés |
| Infrastructure (PostgreSQL + Qdrant) | `docker-compose.yml` | Codé, non démarré (Docker Hub bloqué dans le sandbox de dev) |
| Script d'indexation de tous les textes | `scripts/indexer_tout.sh` | Fait |

### Découverte importante déjà faite
En testant l'extraction sur les vrais textes marocains : **la Loi 84-12 et
les Arrêtés 2853-2856 sont des PDF scannés sans couche de texte** (0
caractère en extraction directe). `src/ingest.py` gère déjà ce cas avec un
fallback OCR automatique (Tesseract, français, ~20s/page) — vérifié
fonctionnel sur la Loi 84-12 (a bien retrouvé le texte du Dahir n°1-13-90).
Le Décret 2-14-607, l'Order 739 chinois et les 3 textes indiens sont en
texte natif, extraction instantanée.

## 3. Logique métier — ce que le système doit savoir faire

Pour un dossier destiné au **Maroc**, avec un produit venant de **Chine**,
**Inde** ou l'**Union européenne** :

- Un socle documentaire commun (demande signée, fiche signalétique,
  dossier technique, bulletin d'analyse, échantillon/étiquetage,
  mandataire au Maroc, ISO 13485 pour les classes IIA/IIB/III)
- Une pièce spécifique selon l'origine :
  - Chine → certificat NMPA (traduction + légalisation requises)
  - Inde → certificat CDSCO (traduction + légalisation requises)
  - Union européenne → certificat de marquage CE (aucune traduction/légalisation)
  - Autre → certificat de libre vente + ISO 13485 (traduction + légalisation requises)
- Dépôt physique possible uniquement le **mercredi et le jeudi** (règle DMP)

Différence structurelle entre les 4 systèmes réglementaires (encodée dans
les 4 fichiers YAML) :
- Le Maroc et l'Inde acceptent des équivalences étrangères (sous condition)
- La Chine accepte une équivalence étrangère pour les classes II/III sauf
  dispositif jamais commercialisé ailleurs
- **L'Union européenne n'accepte aucune équivalence étrangère** — c'est le
  système le plus strict des quatre

## 4. Architecture technique cible

```
Textes réglementaires + dossiers déjà réalisés
        │  (extraction + OCR + découpage + embeddings)
        ▼
     Qdrant (base vectorielle, RAG)
        ▲
        │  (recherche des passages pertinents)
        │
Nouveau dossier (pays d'origine, produit)
        │
        ▼
Rule Engine (YAML, déterministe) ──► liste des documents requis
        │
        ▼
RAG + Mistral (Ollama, self-hosted) ──► contenu rédigé de chaque document
        │
        ▼
Génération DOCX/PDF
        │
        ▼
Backend FastAPI (src/api.py) ──► expose tout ça en HTTP
        │
        ▼
Frontend (React — pas encore construit) ──► validation humaine obligatoire
        │
        ▼
Dépôt (physique + électronique) — TOUJOURS manuel, jamais automatisé
```

## 5. Ce qu'il reste à faire, dans l'ordre

1. **Démarrer l'infrastructure sur ta machine** (Docker Hub n'est pas
   bloqué chez toi comme il l'était dans le sandbox de développement) :
   ```bash
   docker compose up -d
   ollama serve && ollama pull mistral
   ```
2. **Indexer les textes réglementaires** :
   ```bash
   ./scripts/indexer_tout.sh
   ```
3. **Toi (l'utilisateur) : fournir les données réelles** pour enrichir le
   RAG — c'est le point que tu as mentionné vouloir apporter toi-même :
   - Des dossiers déjà réalisés/validés (anonymisés si besoin), à indexer
     avec le même script `src/ingest.py` (ajouter un `type_document:
     dossier_exemple` et les métadonnées pays/produit)
   - La base de données fournisseurs (structure PostgreSQL à définir selon
     tes champs réels : nom, pays, produit, classe, contacts)
4. **Tester le pipeline complet** :
   ```bash
   uvicorn src.api:app --reload --port 8000
   curl -X POST http://localhost:8000/dossiers/generer -H "Content-Type: application/json" \
     -d '{"pays_origine":"chine","produit":"Prothèse orthopédique de hanche","classe":"IIB"}'
   ```
5. **Construire le frontend de validation** (React) qui consomme cette
   API — c'est la seule pièce de l'architecture qui n'a pas encore de code,
   volontairement, pour ne pas construire une interface avant que le
   moteur derrière fonctionne.
6. **Sécuriser avant toute mise en production** : Keycloak (authentification),
   logs d'audit, chiffrement — voir `CLAUDE.md` section sécurité.

## 6. Principe à ne jamais casser en continuant le développement

- Le LLM ne décide **jamais** des documents requis — seul `rule_engine.py`
  le fait, à partir des YAML versionnés dans `rules/`
- Aucun endpoint, aucune fonction ne doit permettre un dépôt automatique
  sans validation humaine explicite
- Toute nouvelle règle réglementaire va dans un fichier YAML, jamais codée
  en dur dans un script Python
