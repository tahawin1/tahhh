// Tâche « conformite-dm » : le Jenkinsfile du dépôt GitHub (branche suivie
// par le serveur), relu à chaque build. Créée une seule fois.
import jenkins.model.Jenkins
import org.jenkinsci.plugins.workflow.job.WorkflowJob
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import hudson.plugins.git.GitSCM
import hudson.plugins.git.BranchSpec

def jenkins = Jenkins.get()
def nom = "conformite-dm"
if (jenkins.getItem(nom) == null) {
    def depot = System.getenv("JENKINS_DEPOT") ?: "https://github.com/tahawin1/tahhh.git"
    def branche = System.getenv("JENKINS_BRANCHE") ?: "claude/complete-pipeline-setup-ikdsp0"
    def scm = new GitSCM(GitSCM.createRepoList(depot, null), [new BranchSpec("*/" + branche)], null, null, [])
    def tache = jenkins.createProject(WorkflowJob, nom)
    tache.definition = new CpsScmFlowDefinition(scm, "Jenkinsfile")
    tache.description = "Conformité DM : tests, évaluation de Mistral, images, déploiement validé par une personne."
    tache.save()
    // premier build (le déclencheur « vérifier GitHub toutes les 15 min » du
    // Jenkinsfile n'est connu de Jenkins qu'après un premier passage)
    tache.scheduleBuild2(60)
    println("Tâche Jenkins créée : " + nom + " (" + depot + ", " + branche + ")")
}
