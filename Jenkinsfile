// Pipeline Jenkins — Agent IA de conformité des dispositifs médicaux.
//
// Chaque étape du cahier des charges est exécutée et notée, à chaque nouvelle
// version publiée sur GitHub (vérifié toutes les 15 min) :
//
//   1. Image de test (Dockerfile du projet)
//   2. Contrôles (en parallèle)
//        - tests Python (moteur de règles, checklist, formulaires, API…)
//        - matrice des règles : 7 origines × 7 classes × 5 situations comparées
//          à la référence versionnée (aucune règle ne change en silence)
//        - interface (lint + build), syntaxe des scripts
//   3. Pile IA (Ollama + Qdrant du serveur, lecture seule)
//        - lecture : Mistral sur des documents SPÉCIMEN aux réponses connues
//        - RAG : bon texte du bon pays retrouvé ; recommandations de Mistral
//          avec citations vérifiées par le code
//        - agent de bout en bout : règles -> classement -> lecture -> checklist
//          -> formulaires -> lettre -> ZIP -> reprise des documents du fabricant
//          (API de test éphémère, base SQLite jetable)
//        - rejeu des dossiers ACCEPTÉS par l'AMMPS (Chine, UE, Inde…) : l'agent
//          refait chaque dossier sans le voir, sa production est comparée au
//          dossier accepté
//   4. Images de production
//   5. Déploiement : seulement si DEPLOYER est coché ET qu'une personne
//      connectée le confirme (même principe que les dossiers).
//
// Les résultats sont dans « Test Result » (un contrôle par ligne) et dans les
// artefacts (rapports-ci/*.md, *.json). Aucune donnée réelle ne quitte le
// serveur. La qualité de l'IA sous le seuil rend le build INSTABLE (orange) ;
// une règle, un test ou un build cassé le met en ÉCHEC (rouge).

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()          // un seul Mistral sur la machine
        buildDiscarder(logRotator(numToKeepStr: '30'))
        timeout(time: 4, unit: 'HOURS')    // le rejeu des dossiers acceptés est long sans GPU
    }

    triggers {
        pollSCM('H/15 * * * *')            // pas de webhook entrant : le serveur reste fermé à Internet
    }

    parameters {
        booleanParam(name: 'EVALUER_IA', defaultValue: true,
                     description: 'Évaluer la pile IA : lecture Mistral, RAG, agent de bout en bout (Ollama et Qdrant du serveur)')
        booleanParam(name: 'REJOUER_ACCEPTES', defaultValue: true,
                     description: 'Rejouer les dossiers acceptés (data/dossiers_valides) et noter l\'agent')
        string(name: 'SEUIL_MISTRAL', defaultValue: '0.75',
               description: 'Exactitude minimale de Mistral sur les spécimens (0 à 1)')
        booleanParam(name: 'DEPLOYER', defaultValue: false,
                     description: 'Déployer sur le serveur après les contrôles (une personne devra confirmer)')
    }

    environment {
        IMAGE_CI = "conformite-ci:${env.BUILD_NUMBER}"
        API_CI = "conformite-ci-api-${env.BUILD_NUMBER}"
        PORT_CI = '8100'
        CLE_CI = "ci-${env.BUILD_NUMBER}-${env.BUILD_ID}"
        RAPPORTS = 'rapports-ci'
        // premier build (lancé à la création de la tâche) : les paramètres n'existent pas encore
        // comme variables d'environnement -> valeur par défaut explicite
        SEUIL = "${params.SEUIL_MISTRAL ?: '0.75'}"
        DOSSIER_SERVEUR = '/opt/conformite'
        OLLAMA_HOTE = 'http://127.0.0.1:11434'
        QDRANT_HOTE = 'http://127.0.0.1:6333'
    }

    stages {
        stage('Image de test') {
            steps {
                sh '''
                    rm -rf "$RAPPORTS" output && mkdir -p "$RAPPORTS"
                    docker build -t "$IMAGE_CI" .   # image de base en cache : pas de limite Docker Hub
                '''
            }
        }

        stage('Contrôles') {
            parallel {
                stage('Tests et matrice des règles') {
                    steps {
                        // réseau isolé : jamais la base ni l'index du serveur (les tests ont leur propre SQLite)
                        sh '''
                            docker run --rm --network none -v "$WORKSPACE":/w -w /w -e PYTHONDONTWRITEBYTECODE=1 \
                                "$IMAGE_CI" sh -c 'python scripts/ci_tests.py --rapport "$0"; t=$?; \
                                                   python scripts/ci_regles.py --rapport "$0"; r=$?; exit $((t + r))' "$RAPPORTS"
                        '''
                    }
                }
                stage('Interface') {
                    steps {
                        sh '''
                            docker run --rm -v "$WORKSPACE/frontend":/f -w /f -e VITE_API_URL=/api node:22-alpine \
                                sh -c "npm ci --no-audit --no-fund && npm run lint && npm run build"
                        '''
                    }
                }
                stage('Scripts') {
                    steps {
                        sh '''
                            for f in scripts/*.sh deploiement/*/*.sh; do bash -n "$f" || exit 1; done
                            echo "Syntaxe des scripts shell : OK"
                        '''
                    }
                }
            }
        }

        stage('Pile IA') {
            when { expression { params.EVALUER_IA } }
            stages {
                stage('Services') {
                    steps {
                        script {
                            def ollama = sh(returnStatus: true, script: 'curl -sf -m 10 "$OLLAMA_HOTE/api/tags" >/dev/null')
                            def qdrant = sh(returnStatus: true, script: 'curl -sf -m 10 "$QDRANT_HOTE/collections" >/dev/null')
                            env.PILE_IA = (ollama == 0 && qdrant == 0) ? 'oui' : 'non'
                            if (env.PILE_IA != 'oui') {
                                // jamais un succès silencieux : l'IA n'a pas été évaluée
                                unstable("Ollama (${ollama == 0 ? 'ok' : 'injoignable'}) ou Qdrant (${qdrant == 0 ? 'ok' : 'injoignable'}) : pile IA non évaluée")
                            } else {
                                sh 'curl -s "$OLLAMA_HOTE/api/tags" | grep -o \'"name":"[^"]*"\' | sed \'s/^/  modèle /\''
                            }
                        }
                    }
                }
                stage('Lecture par Mistral (spécimens)') {
                    when { environment name: 'PILE_IA', value: 'oui' }
                    steps {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh '''
                                docker run --rm --network host -v "$WORKSPACE":/w -w /w \
                                    -e OLLAMA_BASE_URL="$OLLAMA_HOTE" -e OLLAMA_TIMEOUT=1800 \
                                    "$IMAGE_CI" python scripts/evaluer_mistral.py --rapport "$RAPPORTS" --seuil "$SEUIL"
                            '''
                        }
                    }
                }
                stage('RAG et recommandations') {
                    when { environment name: 'PILE_IA', value: 'oui' }
                    steps {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh '''
                                docker run --rm --network host -v "$WORKSPACE":/w -w /w \
                                    -e OLLAMA_BASE_URL="$OLLAMA_HOTE" -e QDRANT_HOST=127.0.0.1 -e OLLAMA_TIMEOUT=1800 \
                                    "$IMAGE_CI" python scripts/ci_rag.py --rapport "$RAPPORTS"
                            '''
                        }
                    }
                }
                stage('Agent de bout en bout') {
                    when { environment name: 'PILE_IA', value: 'oui' }
                    steps {
                        // API de test : base SQLite jetable, mémoire vide, profil fictif ; Qdrant et Ollama du serveur
                        sh '''
                            mkdir -p config "$RAPPORTS/memoire-vide"
                            [ -f config/entreprise.yaml ] || printf '%s\\n' 'raison_sociale: "SOCIETE ESSAI CI"' \
                                'ville: "Rabat"' 'adresse: "1 rue de l Essai, Rabat"' 'representant_legal: "M. Essai"' \
                                > config/entreprise.yaml
                            docker rm -f "$API_CI" >/dev/null 2>&1 || true
                            docker run -d --name "$API_CI" --network host -v "$WORKSPACE":/w -w /w \
                                -e DATABASE_URL="sqlite+pysqlite:////w/$RAPPORTS/agent.db" -e API_KEY="$CLE_CI" \
                                -e QDRANT_HOST=127.0.0.1 -e OLLAMA_BASE_URL="$OLLAMA_HOTE" -e OLLAMA_TIMEOUT=1800 \
                                -e MEMOIRE_DIR="/w/$RAPPORTS/memoire-vide" \
                                "$IMAGE_CI" uvicorn src.api:app --host 127.0.0.1 --port "$PORT_CI"
                            for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT_CI/health" >/dev/null && break; sleep 2; done
                            curl -sf "http://127.0.0.1:$PORT_CI/health"
                        '''
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh '''
                                docker run --rm --network host -v "$WORKSPACE":/w -w /w "$IMAGE_CI" \
                                    python scripts/ci_agent.py --api "http://127.0.0.1:$PORT_CI" --cle "$CLE_CI" --rapport "$RAPPORTS"
                            '''
                        }
                    }
                }
                stage('Rejeu des dossiers acceptés') {
                    when {
                        allOf {
                            environment name: 'PILE_IA', value: 'oui'
                            expression { params.REJOUER_ACCEPTES }
                        }
                    }
                    steps {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh '''
                                ACCEPTES="$DOSSIER_SERVEUR/data/dossiers_valides"; MEMOIRE="$DOSSIER_SERVEUR/output/memoire"
                                mkdir -p "$RAPPORTS/vide"
                                [ -d "$ACCEPTES" ] || ACCEPTES="$WORKSPACE/$RAPPORTS/vide"
                                [ -d "$MEMOIRE" ] || MEMOIRE="$WORKSPACE/$RAPPORTS/vide"
                                docker run --rm --network host -v "$WORKSPACE":/w -w /w \
                                    -v "$ACCEPTES":/acceptes:ro -v "$MEMOIRE":/memoire:ro "$IMAGE_CI" \
                                    python scripts/ci_rejouer_acceptes.py --api "http://127.0.0.1:$PORT_CI" --cle "$CLE_CI" \
                                        --acceptes /acceptes --memoire /memoire --rapport "$RAPPORTS"
                            '''
                        }
                    }
                }
            }
            post {
                always {
                    sh 'docker logs "$API_CI" > "$RAPPORTS/api-ci.log" 2>&1 || true; docker rm -f "$API_CI" >/dev/null 2>&1 || true'
                }
            }
        }

        stage('Images de production') {
            steps {
                sh 'docker compose --profile api --profile interface build'
            }
        }

        stage('Déploiement') {
            when {
                expression { params.DEPLOYER && currentBuild.resultIsBetterOrEqualTo('UNSTABLE') }
            }
            steps {
                input message: "Déployer cette version sur le serveur ? État des contrôles : ${currentBuild.currentResult} " +
                               '(sauvegarde automatique avant la mise à jour)',
                      ok: 'Déployer'
                sh '''
                    cd "$DOSSIER_SERVEUR"
                    bash scripts/mettre_a_jour.sh
                    DEPLOYE=$(git rev-parse HEAD)
                    echo "Version déployée : $DEPLOYE — version contrôlée : $GIT_COMMIT"
                    if [ "$DEPLOYE" != "$GIT_COMMIT" ]; then
                        echo "ATTENTION : une version plus récente a été publiée pendant les contrôles ; relancer le pipeline."
                        exit 3
                    fi
                '''
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: "${env.RAPPORTS}/*.xml"
            archiveArtifacts allowEmptyArchive: true, artifacts: "${env.RAPPORTS}/*.md, ${env.RAPPORTS}/*.json, ${env.RAPPORTS}/*.xml, ${env.RAPPORTS}/*.log"
            sh 'docker image rm "$IMAGE_CI" >/dev/null 2>&1 || true'
        }
        success {
            echo 'Tous les contrôles sont passés.'
        }
        unstable {
            echo 'Contrôles du code passés ; qualité de l\'IA à améliorer ou pile IA non évaluée : voir « Test Result ».'
        }
        failure {
            echo 'Échec : voir l\'étape en rouge et les rapports.'
        }
    }
}
