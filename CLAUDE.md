# Agent IA — Conformité documentaire dispositifs médicaux

Ce fichier résume le cahier des charges du projet pour toute session future
travaillant sur ce repo (humaine ou Claude Code). Lis-le avant toute
modification.

## 1. Objectif du projet

Automatiser, sous contrôle humain obligatoire, la constitution des dossiers
de conformité pour l'importation et l'enregistrement de dispositifs
médicaux (prothèses et autres produits médicaux) au Maroc, en tenant compte
du pays d'origine du fournisseur (Chine, Inde, Union européenne, autre).

L'entreprise importe des produits médicaux depuis plusieurs pays. Chaque
dossier déposé auprès du ministère de la Santé marocain doit contenir des
pièces différentes selon l'origine du fournisseur. Le système doit :

1. Déterminer les documents requis selon le fournisseur (règles explicites,
   pas de décision du LLM sur ce point)
2. Générer le contenu de ces documents à partir d'une base de données
   fournisseur et de dossiers déjà réalisés (RAG)
3. Vérifier leur conformité aux textes réglementaires réels
4. Préparer le dépôt (physique et électronique), sous validation humaine
   systématique avant tout envoi

## 2. Principe non négociable

**Aucun document n'est déposé sans validation humaine explicite.**
Le LLM ne décide jamais seul des règles applicables — celles-ci sont
codées en YAML, versionnées, et lues par un moteur de règles déterministe
(`src/rule_engine.py`). Le LLM (Mistral) n'intervient que pour rédiger le
contenu d'un document une fois la liste des pièces requises déjà décidée
par le code.

## 3. Architecture cible

```
Dossiers déjà réalisés ─┐
Textes réglementaires ──┼─► extraction → chunks → embeddings → Qdrant (RAG)
                         │
Nouveau dossier ────────►│
(fournisseur, produit,   ├─► Rule Engine (YAML par pays) → liste des documents requis
 pays d'origine)          │
                         └─► RAG (retrouve exemples similaires) + Mistral → contenu généré
                                    │
                              Template → DOCX/PDF
                                    │
                          Validation humaine (obligatoire)
                                    │
                              Dépôt final (physique + électronique)
```

### Stack technique
| Couche | Outil |
|---|---|
| Données structurées | PostgreSQL |
| Base vectorielle (RAG) | Qdrant |
| Modèle IA | Mistral (open source, self-hosted) |
| Serveur d'inférence | Ollama (dev/pilote) → vLLM (production) |
| Orchestration | Python (LangChain optionnel) |
| Génération documentaire | Jinja2, python-docx |
| Interface de validation | React + FastAPI (à construire après le pilote CLI) |
| Sécurité | Keycloak (SSO/RBAC), HashiCorp Vault (secrets) |
| Déploiement | Docker / docker-compose |

## 4. Référentiels réglementaires — quatre pays, quatre bases de règles distinctes

Le LLM n'a pas "une" connaissance générale de la conformité : il consulte
toujours la base de règles du pays concerné. Fichiers sources dans
`data/raw_pdfs/`, règles structurées dans `rules/*.yaml`.

| Pays | Texte de référence | Autorité | Fichier YAML |
|---|---|---|---|
| Maroc (destination) | Loi 84-12, Décret 2-14-607, Arrêtés 2853-2856 | DMP (Direction du Médicament et de la Pharmacie) | `rules/maroc.yaml` |
| Chine (origine possible) | Règlement du Conseil d'État n°739 (2021) | NMPA | `rules/chine.yaml` |
| Inde (origine possible) | Medical Devices Rules 2017 + amendements | CDSCO | `rules/inde.yaml` |
| Union européenne (origine possible) | Règlement (UE) 2017/745 (MDR) | Organismes notifiés | `rules/union_europeenne.yaml` |

### Différence clé entre les 4 systèmes (à respecter dans le rule engine)
- **Maroc** accepte les certificats étrangers (CE, NMPA, CDSCO) comme pièce
  justificative — le système le plus souple des quatre.
- **Chine** accepte une équivalence étrangère pour les classes II/III, sauf
  dispositif innovant non commercialisé ailleurs.
- **Inde** dispense d'essai clinique local si Free Sale Certificate d'un
  pays reconnu (Australie, Canada, Japon, UE, UK, USA — pas la Chine).
- **Union européenne** n'accepte AUCUNE équivalence étrangère : évaluation
  de conformité UE complète obligatoire dans tous les cas.

Cas d'usage principal du projet : **Cas A — dossier pour le Maroc, produit
d'origine étrangère** (Chine/Inde/UE). Le Cas B (vendre directement en
Chine/Inde/UE) n'est pas la priorité actuelle mais l'architecture le
supporte déjà.

## 5. Contraintes opérationnelles à respecter dans le code

- Dépôt physique du dossier au Maroc possible uniquement le **mercredi et
  le jeudi** (voir `src/rule_engine.py::prochain_creneau_depot`)
- Documents étrangers (chinois, indiens) : traduction assermentée et
  légalisation/apostille généralement nécessaires — signalées par le flag
  `traduction_requise` dans les règles YAML, jamais assumées silencieusement
- Chaque texte réglementaire indexé porte une date de version en métadonnée
  (`date_version`) — ne jamais écraser une règle sans la versionner

## 6. Ordre de construction (approche pilote, pas tout d'un coup)

1. Indexer les textes marocains en premier (pays de destination principal)
2. Puis les articles d'exportation/vente libre des pays d'origine réellement
   utilisés (Chine, Inde) — pas les textes entiers
3. Valider le rule engine sur les combinaisons réelles de l'activité
   (Maroc+Chine, Maroc+Inde, Maroc+UE) avant d'élargir
4. Pas de frontend avant que le pipeline CLI (script Python) fonctionne
   bout en bout et soit validé sur un dossier réel connu

## 7. État d'avancement de ce repo

- [x] Structure du projet et textes réglementaires collectés
- [x] CLAUDE.md (ce fichier)
- [ ] Règles YAML par pays (`rules/`)
- [ ] Moteur de règles (`src/rule_engine.py`)
- [ ] Pipeline d'extraction/indexation (`src/ingest.py`)
- [ ] Pipeline RAG + génération (`src/generate.py`)
- [ ] docker-compose (PostgreSQL + Qdrant)
- [ ] Test end-to-end sur un cas réel
- [ ] Interface de validation humaine (React/FastAPI) — phase suivante,
      après validation du pipeline CLI

## 8. Ce qui n'est volontairement PAS fait à ce stade

- Pas de fine-tuning de Mistral — le RAG suffit et reste plus maintenable
- Pas d'intégration API temps réel avec le ministère marocain (elle
  n'existe pas de façon publique/documentée) — le dépôt reste préparé puis
  déposé manuellement
- Pas de frontend avant que le cœur du pipeline soit validé en ligne de
  commande
