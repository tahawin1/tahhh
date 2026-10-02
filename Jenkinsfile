// Pipeline Jenkins — Agent IA de conformité des dispositifs médicaux.
//
// À chaque nouvelle version publiée sur GitHub (vérifié toutes les 15 min) :
//   1. image de test construite depuis le Dockerfile du projet ;
//   2. en parallèle : tests Python (règles, moteur, API, formulaires…),
//      interface (lint + build), syntaxe des scripts ;
//   3. évaluation de Mistral (Ollama de l'hôte) sur des documents SPÉCIMEN
//      fictifs aux réponses connues : exactitude minimale et zéro erreur
//      « dangereuse » (valeur fausse acceptée par le contrôle des citations) ;
//   4. images de production construites ;
//   5. déploiement sur le serveur UNIQUEMENT si la case DEPLOYER est cochée ET
//      après accord explicite d'une personne connectée (même principe que
//      les dossiers : rien ne part sans validation humaine).
// Aucune donnée réelle n'est utilisée : les spécimens sont inventés.
//
// Jenkins tourne dans Docker sur le serveur (deploiement/jenkins/,
// scripts/installer_jenkins.sh) et pilote le Docker de l'hôte : les chemins
// du workspace sont identiques dans Jenkins et sur l'hôte (/var/jenkins_home).

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()          // un seul Mistral sur la machine
        buildDiscarder(logRotator(numToKeepStr: '30'))
        timeout(time: 90, unit: 'MINUTES')
    }

    triggers {
        pollSCM('H/15 * * * *')            // pas de webhook entrant : le serveur reste fermé à Internet
    }

    parameters {
        booleanParam(name: 'EVALUER_MISTRAL', defaultValue: true,
                     description: 'Évaluer la lecture des documents par Mistral (Ollama doit tourner sur le serveur)')
        string(name: 'SEUIL_MISTRAL', defaultValue: '0.75',
               description: 'Exactitude minimale de Mistral sur les spécimens (0 à 1)')
        booleanParam(name: 'DEPLOYER', defaultValue: false,
                     description: 'Déployer sur le serveur après les contrôles (une personne devra confirmer)')
    }

    environment {
        IMAGE_CI = "conformite-ci:${env.BUILD_NUMBER}"
        RAPPORTS = 'rapports-ci'
        DOSSIER_SERVEUR = '/opt/conformite'
        OLLAMA_HOTE = 'http://127.0.0.1:11434'
    }

    stages {
        stage('Image de test') {
            steps {
                sh '''
                    rm -rf "$RAPPORTS" && mkdir -p "$RAPPORTS"
                    docker build -t "$IMAGE_CI" .   # image de base en cache : pas de limite Docker Hub
                '''
            }
        }

        stage('Contrôles') {
            parallel {
                stage('Tests Python') {
                    steps {
                        // réseau isolé : jamais la base ni l'index du serveur (les tests ont leur propre SQLite)
                        sh '''
                            docker run --rm --network none -v "$WORKSPACE":/w -w /w -e PYTHONDONTWRITEBYTECODE=1 \
                                "$IMAGE_CI" python scripts/ci_tests.py --rapport "$RAPPORTS"
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

        stage('Évaluation de Mistral') {
            when { expression { params.EVALUER_MISTRAL } }
            steps {
                script {
                    def ollama = sh(returnStatus: true,
                                    script: 'curl -sf -m 10 "$OLLAMA_HOTE/api/tags" >/dev/null')
                    if (ollama != 0) {
                        // jamais un succès silencieux : la lecture n'a pas été vérifiée
                        unstable("Ollama injoignable sur ${env.OLLAMA_HOTE} : Mistral n'a pas été évalué")
                        return
                    }
                    sh '''
                        docker run --rm --network host -v "$WORKSPACE":/w -w /w \
                            -e OLLAMA_BASE_URL="$OLLAMA_HOTE" -e OLLAMA_TIMEOUT=900 \
                            "$IMAGE_CI" python scripts/evaluer_mistral.py --rapport "$RAPPORTS" --seuil "$SEUIL_MISTRAL"
                    '''
                }
            }
        }

        stage('Images de production') {
            steps {
                sh 'docker compose --profile api --profile interface build'
            }
        }

        stage('Déploiement') {
            when { expression { params.DEPLOYER } }
            steps {
                input message: 'Déployer cette version sur le serveur ? (sauvegarde automatique avant la mise à jour)',
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
            archiveArtifacts allowEmptyArchive: true, artifacts: "${env.RAPPORTS}/**"
            sh 'docker image rm "$IMAGE_CI" >/dev/null 2>&1 || true'
        }
        success {
            echo 'Tous les contrôles sont passés.'
        }
        failure {
            echo 'Échec : voir l\'étape en rouge et les rapports (Tests / Évaluation Mistral).'
        }
    }
}
