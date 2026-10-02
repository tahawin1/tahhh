# Jenkins du serveur de l'entreprise : intégration continue de l'outil
# (tests, évaluation de Mistral, construction des images, déploiement validé
# par une personne). Il pilote le Docker de l'hôte (socket monté) : les
# étapes du Jenkinsfile lancent des conteneurs jetables.
FROM jenkins/jenkins:lts-jdk17

USER root
# Client Docker + compose (le moteur reste celui de l'hôte), git, curl
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
 && rm -rf /var/lib/apt/lists/*

# Extensions strictement nécessaires (liste versionnée)
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# Premier démarrage : compte administrateur et tâche « conformite-dm » créés
# par script (pas d'assistant d'installation)
COPY init.groovy.d/ /usr/share/jenkins/ref/init.groovy.d/
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
