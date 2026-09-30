// Points d'extension optionnels, fournis par un hébergement qui remplace le
// backend HTTP (édition claude.ai, voir claude_ai/moteur.js). Absents avec
// le backend FastAPI : le frontend fonctionne alors exactement comme avant.
interface Window {
  /** Session ouverte automatiquement (identité fournie par l'hébergement). */
  conformiteSession?: Promise<{ nom: string; cleApi: string } | null>
  /** Enregistrement d'un fichier quand un lien de téléchargement est impossible. */
  conformiteEnregistrer?: (nom: string, contenu: Blob) => Promise<void>
}
