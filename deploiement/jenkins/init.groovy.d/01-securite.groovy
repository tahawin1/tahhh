// Compte administrateur créé au premier démarrage, mot de passe lu dans la
// variable JENKINS_ADMIN_PASSWORD (fichier .env du serveur, jamais versionné).
// Personne d'autre ne peut rien faire sans être connecté.
import jenkins.model.Jenkins
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.FullControlOnceLoggedInAuthorizationStrategy

def jenkins = Jenkins.get()
def motDePasse = System.getenv("JENKINS_ADMIN_PASSWORD")
if (!(jenkins.securityRealm instanceof HudsonPrivateSecurityRealm)) {
    if (!motDePasse) {
        println("JENKINS_ADMIN_PASSWORD absent : compte administrateur non créé")
        return
    }
    def royaume = new HudsonPrivateSecurityRealm(false)
    royaume.createAccount("admin", motDePasse)
    jenkins.securityRealm = royaume
    def strategie = new FullControlOnceLoggedInAuthorizationStrategy()
    strategie.allowAnonymousRead = false
    jenkins.authorizationStrategy = strategie
    jenkins.numExecutors = 1  // un seul Mistral sur la machine : un build à la fois
    jenkins.save()
    println("Compte administrateur Jenkins créé (admin)")
}
