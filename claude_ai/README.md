# Édition claude.ai du tableau de bord

Le même tableau de bord que `frontend/`, publié comme page claude.ai et
fonctionnant **sans serveur** :

| Besoin | Version serveur | Édition claude.ai |
|---|---|---|
| Dossiers, pièces, journal | PostgreSQL | base de données de la page (partagée) |
| Documents reçus | disque du serveur | stockage de la page |
| Rédaction / lecture des documents | **Mistral** (Ollama, sur vos machines) | **Claude** (compte de la personne qui lance la tâche) |
| Extraits réglementaires (RAG) | Qdrant, à la volée | pré-calculés depuis Qdrant (`regles.json`) |
| Pièces requises | moteur de règles (YAML) | le même, exporté (`regles.json`) |
| Identité | nom saisi + clé d'API | compte claude.ai de la personne |

Inchangé : l'IA ne décide jamais des pièces requises ; les pièces à fournir
ne sont jamais rédigées ; chaque valeur lue est confrontée au texte du
document (`controle.js`, portage de `src/extraction.py`, mêmes tests) ;
seule une personne identifiée valide ; aucun dépôt automatique.

## Limites à connaître
- **L'agent travaille dans l'onglet** de la personne qui lance la tâche :
  fermer ou recharger la page pendant une rédaction ou une lecture
  l'interrompt (la pièce passe « interrompue — relancer »). Naviguer dans
  le tableau de bord ne l'interrompt pas.
- **Documents scannés** : Claude lit les images et en fait lui-même la
  transcription ; les citations sont alors contrôlées contre cette
  transcription (signalé dans la page), pas contre une couche texte.
- **Confidentialité** : les documents fournisseurs et les dossiers sont
  stockés sur claude.ai et lus par Claude, et non par un modèle hébergé
  chez vous. À valider par la direction avant d'y mettre des dossiers réels.
- L'utilisation de l'agent consomme l'usage Claude de la personne qui
  lance la tâche (une autorisation est demandée au premier appel).

## Construire et publier
```bash
.venv/bin/python claude_ai/exporter_regles.py        # après toute modification des YAML (Qdrant + Ollama requis)
.venv/bin/python claude_ai/construire.py espace.html  # page à publier
node claude_ai/test_controle.js                       # tests du contrôle des citations
```
Test local complet (sans claude.ai) : `construire.py page.html --local <libs>`
insère `simulation_locale.js`, qui simule les capacités de claude.ai et
fait jouer l'agent par le Mistral local.
