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
| Maroc (destination) | Loi 84-12, Décret 2-14-607, Arrêtés 2853-2856 (enregistrement : 2855-15 art. 2) | AMMPS (ex-DMP) — demande adressée à son Directeur général | `rules/maroc.yaml` (v2 ; v1 dans `rules/historique/`) |
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
- [x] Règles YAML par pays (`rules/`)
- [x] Moteur de règles (`src/rule_engine.py`) + tests (`tests/`)
- [x] Pipeline d'extraction/indexation (`src/ingest.py`) — OCR parallélisé,
      détection des pages scannées ou vectorisées
- [x] Pipeline RAG + génération (`src/generate.py`)
- [x] docker-compose (PostgreSQL + Qdrant) — démarré et vérifié
- [x] Backend FastAPI (`src/api.py`) — endpoints testés
- [x] Indexation de tous les textes de `data/raw_pdfs/` dans Qdrant
- [ ] Test end-to-end sur un dossier réel connu (le pipeline tourne de bout
      en bout ; reste à le valider sur un dossier réel déjà déposé)
- [ ] Données réelles : dossiers déjà réalisés + base fournisseurs (PostgreSQL)
- [x] Distinction pièces `a_rediger` / `a_fournir` dans les règles YAML
      (les certificats et pièces de tiers ne sont jamais générés)
- [x] Suivi des dossiers (PostgreSQL), rédaction en tâche de fond,
      validation / rejet nominatifs, journal d'audit — testés
- [x] Installation serveur en une commande (`scripts/installer_serveur.sh`,
      fiche `INSTALLATION_SERVEUR.md`) : tableau de bord servi par nginx
      (`deploiement/interface/`, API relayée sous `/api`) — image construite et
      parcours E2E réussi à travers nginx ; sauvegarde `scripts/sauvegarder.sh`
      testée (restauration comprise) ; mise à jour en une commande
      `scripts/mettre_a_jour.sh` (sauvegarde, pull GitHub ou fichier .bundle,
      rebuild, rapport sans secret) ; contrôle complet en une commande
      `scripts/verifier_installation.sh` (services, clé, Mistral, index, OCR, ports). Pile complète testée comme sur le serveur
      (API en conteneur + nginx + clé obligatoire + Ollama sur l'hôte) : E2E,
      indexation depuis le conteneur, rédaction Mistral. Non testable ici :
      la couche apt (Tesseract) de l'image API, deb.debian.org étant bloqué
      dans l'environnement de développement. Pas encore exécutée sur le vrai serveur.
- [x] **Serveur de l'entreprise = Windows** (2026-10-01) : installation via
      WSL2 + Ubuntu 24.04 (`deploiement/windows/installer_windows.ps1`, puis le
      même `installer_serveur.sh` dans Ubuntu) ; relais du port (netsh
      portproxy) et tâche planifiée au démarrage (`demarrer_conformite.ps1`) ;
      Windows Server 2019 et antérieurs : VM Ubuntu Hyper-V. Scripts PowerShell
      vérifiés (syntaxe, encodage UTF-8 BOM pour PowerShell 5.1, logique avec
      un faux wsl.exe) mais **jamais exécutés sur un vrai Windows**.
- [x] Interface de validation (React, `frontend/`) — testée dans Chromium
      contre le backend local ; déploiement Vercel prêt (`DEPLOIEMENT.md`)
      mais pas encore effectué
- [x] Agent — étape 1 : lecture des documents reçus du fournisseur (OCR +
      extraction des champs déclarés dans les YAML, chaque valeur confrontée
      au texte réel) — testée sur des spécimens fictifs, texte et scan
- [x] Édition claude.ai (`claude_ai/`) : même tableau de bord, sans serveur,
      l'agent y est Claude (et non Mistral) — voir claude_ai/README.md ;
      confidentialité des documents fournisseurs à valider par la direction
- [x] Règles Maroc v2 (2026-10-01) alignées sur l'arrêté 2855-15 art. 2 (1)
      « DM importé » et sur le dossier réel accepté : AMMPS, pièces numérotées
      (`numero`), fondement de chaque pièce (`source`), certificat CE/équivalent
      pour IS/IM/IIA/IIB/III, remarque 2023/607 ; retirés : bulletin d'analyse,
      dossier technique, mandataire ; ajoutés : attestation fabricant,
      déclaration de conformité, étiquetage, notice, catalogue, annexe II,
      quittance (hors numérotation, à confirmer). v1 archivée.
- [x] Modèles de rédaction (`src/modeles.py`, `scripts/indexer_modeles.sh`) :
      les pièces à rédiger des dossiers acceptés (`data/dossiers_valides/`,
      jamais versionné) sont indexées (collection `modeles_dossiers`) ; le
      fichier est rattaché à la pièce par son numéro et le `numero` des règles
      (code, pas IA). Mistral rédige sur le modèle le plus proche ; sans
      extraits de textes quand un modèle existe ; profil de l'entreprise
      (`config/entreprise.yaml`, jamais versionné) ; garde-fou déterministe
      `recadrer_sur_modele` (préambule et ajouts après la fin du modèle retirés).
      Essai réel : la lettre (pièce 1) d'un nouveau dossier UE est conforme au
      modèle accepté, via la pile serveur complète.
- [ ] Agent — étape 2 : contrôles automatiques de conformité des documents
      reçus (expiration, produit, classe, émetteur) — règles en YAML
- [ ] Agent — étape 3 : projets remplis avec les données extraites
- [ ] Agent — étape 4 : enchaînement automatique et relances fournisseur
      préparées (jamais envoyées sans validation)
- [ ] Tests sur de vrais documents fournisseurs (en attente de dossiers réels)
- [ ] Authentification réelle (Keycloak) — aujourd'hui : clé d'API partagée
      + nom saisi par l'utilisateur (non vérifié)

### Points d'attention découverts en exécutant le pipeline
- Les embeddings (bge-m3) passent par Ollama par défaut (`src/embeddings.py`) ;
  l'indexation et la recherche doivent utiliser le même backend.
- La condition de classe d'un document du socle se déclare en liste YAML
  (`classes_concernees`), jamais en texte libre (bug corrigé : l'ISO 13485
  était exigé pour la classe I).
- `data/raw_pdfs/ue_mdr_annexe.txt` contient en réalité les Medical Devices
  Rules 2017 indiennes consolidées — indexé sous `pays=inde`.
- Même avec la liste des pièces imposée et les données du dossier fournies,
  Mistral peut inventer un détail (ex. une adresse) : la relecture humaine
  de chaque projet n'est pas une formalité.
- **Enseignements du premier dossier réel accepté** (UE, classe IIb, ciment
  osseux — pièces dans `data/dossiers_valides/`, jamais versionné) :
  - la demande est adressée au **Directeur général de l'AMMPS** (Agence
    marocaine des médicaments et des produits de santé), plus au ministre
    ni à la DMP : autorité à mettre à jour dans les règles ;
  - les pièces sont déposées **numérotées** (1 lettre, 2 fiche signalétique,
    3 autorisation du fabricant, 4 certificat CE + lettre de confirmation,
    5 ISO 13485, 6 déclaration de conformité, 7 étiquettes, 8 notice (partie
    française), 9 photos, 14 catalogue, 16 certificat d'enregistrement au
    modèle de l'annexe II pré-rempli par le demandeur) ;
    les numéros 10 à 13 et 15 sont sans objet pour ce type de produit
    (confirmé par l'utilisateur) — ne pas les exiger ;
  - **certificat CE (directive 93/42) expiré sur le papier mais valide** grâce
    à la lettre de confirmation de l'organisme notifié au titre du Règlement
    (UE) 2023/607 : un contrôle d'expiration naïf rejetterait à tort ;
  - absents de ce dossier : « bulletin d'analyse », « dossier technique »,
    « mandataire au Maroc » — pièces actuelles des règles à revoir ;
  - lecture par l'agent sur les vrais certificats : ISO 7/7 vérifiés,
    certificat CE scanné 6 vérifiés + 1 prudent + classe absente (exact).
- Test de la pile serveur : une rédaction a reçu une erreur 500 d'Ollama après
  3 min de génération (cause non identifiée, non reproduite à la relance) ;
  rédaction et lecture relancent désormais une fois automatiquement sur 5xx
  (`tests/test_relance_ollama.py`).
- Modèles : pour la **lettre**, Mistral + modèle + recadrage donnent un résultat
  conforme. Pour les **formulaires** (fiche signalétique, annexe II), la
  rédaction libre par Mistral ne suit pas la mise en page (essai du
  2026-10-01) : ils doivent être remplis par le code, champ par champ, à
  partir des modèles et des données extraites (agent — étape 3).
- Mistral 7B ajoute souvent une introduction (« Voici… ») et des listes
  inventées après la signature : le prompt ne suffit pas, d'où le recadrage.
- Au premier démarrage à froid, charger Mistral peut dépasser 5 min sur un
  disque lent : `OLLAMA_LOAD_TIMEOUT=20m` (réglé par installer_serveur.sh).
- Sur CPU seul, Mistral 7B rédige ~5 tokens/s : `/dossiers/generer` prend
  plusieurs minutes par document. Un GPU (ou vLLM) est nécessaire en production.

## 8. Ce qui n'est volontairement PAS fait à ce stade

- Pas de fine-tuning de Mistral — le RAG suffit et reste plus maintenable
- Pas d'intégration API temps réel avec le ministère marocain (elle
  n'existe pas de façon publique/documentée) — le dépôt reste préparé puis
  déposé manuellement
- Pas de frontend avant que le cœur du pipeline soit validé en ligne de
  commande
