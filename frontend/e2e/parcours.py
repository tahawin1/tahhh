"""
Test de bout en bout du tableau de bord, dans un vrai navigateur (Chromium).

Prérequis : backend démarré (uvicorn src.api:app --port 8000) et frontend
servi (npm run build && npx vite preview --port 4173), avec
VITE_API_URL pointant vers le backend — ou le frontend déployé sur Vercel.

    .venv/bin/python frontend/e2e/parcours.py [URL_FRONTEND] [DOSSIER_CAPTURES]
    (E2E_API_KEY=... si le backend exige une clé d'API)

Attention : crée un dossier de test « Stent coronaire (test E2E) » dans la base.

Vérifie concrètement que le tableau de bord charge les données du backend :
connexion, liste des dossiers, aperçu des pièces requises (moteur de règles),
création d'un dossier, validation d'une pièce à fournir, journal.
"""
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"
CAPTURES = Path(sys.argv[2] if len(sys.argv) > 2 else "e2e-captures")
CAPTURES.mkdir(parents=True, exist_ok=True)
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def etape(message):
    print(f"✓ {message}", flush=True)


with sync_playwright() as p:
    navigateur = p.chromium.launch(executable_path=CHROMIUM if Path(CHROMIUM).exists() else None)
    page = navigateur.new_page(viewport={"width": 1280, "height": 900})
    erreurs_console = []
    # polices Google : externes, parfois bloquées par un proxy — sans effet sur le fonctionnement
    page.on("console", lambda m: m.type == "error" and "fonts.g" not in (m.location or {}).get("url", "")
            and erreurs_console.append(m.text))

    # 1. Connexion
    page.goto(URL)
    page.get_by_label("Nom et prénom").wait_for(timeout=15000)
    page.get_by_label("Nom et prénom").fill("Testeur E2E")
    if os.environ.get("E2E_API_KEY"):
        page.get_by_label("Clé d'API").fill(os.environ["E2E_API_KEY"])
    page.get_by_role("button", name="Accéder au tableau de bord").click()
    expect(page.get_by_text("Serveur en ligne")).to_be_visible(timeout=15000)
    expect(page.get_by_role("heading", name="Vos dossiers")).to_be_visible()
    etape("connexion et état du serveur (/health) affichés")

    # 2. Liste des dossiers chargée depuis PostgreSQL via l'API
    expect(page.locator(".carte-dossier").first.or_(page.get_by_text("Aucun dossier pour l'instant"))).to_be_visible()
    nb_lignes = page.locator(".carte-dossier").count()
    page.screenshot(path=CAPTURES / "1-liste-dossiers.png", full_page=True)
    etape(f"liste des dossiers chargée depuis le backend ({nb_lignes} dossier(s))")

    # 3. Aperçu des pièces requises : décidé par le moteur de règles du backend
    page.get_by_role("link", name="Nouveau dossier").first.click()
    page.get_by_role("radio", name="Inde").check(force=True)  # radio masqué sous sa tuile : le libellé reçoit le clic
    page.get_by_role("radio", name=re.compile(r"^III ")).check(force=True)  # radio masqué sous sa tuile : le libellé reçoit le clic
    expect(page.get_by_text("Le fournisseur les envoie (4)")).to_be_visible()
    expect(page.get_by_text("Autorisation de mise en vente délivrée par la CDSCO")).to_be_visible()
    expect(page.get_by_text("L'agent les rédige (4)")).to_be_visible()
    page.get_by_role("radio", name=re.compile(r"^I ")).check(force=True)  # radio masqué sous sa tuile : le libellé reçoit le clic
    expect(page.get_by_text("Le fournisseur les envoie (3)")).to_be_visible()  # pas d'ISO 13485 en classe I
    page.get_by_role("radio", name=re.compile(r"^III ")).check(force=True)  # radio masqué sous sa tuile : le libellé reçoit le clic
    etape("aperçu des documents requis chargé depuis /dossiers/documents-requis (Inde III : 4+4, classe I : sans ISO)")

    # 4. Création d'un dossier
    page.get_by_label("Dispositif médical").fill("Stent coronaire (test E2E)")
    page.get_by_label("Fournisseur / fabricant").fill("Fabricant indien (test)")
    page.screenshot(path=CAPTURES / "2-nouveau-dossier.png", full_page=True)
    page.get_by_role("button", name="Créer le dossier").click()
    expect(page.get_by_role("heading", name="Stent coronaire (test E2E)")).to_be_visible()
    expect(page.locator("article.piece")).to_have_count(8)
    etape("dossier créé et affiché (8 pièces)")

    # 5. Une pièce à fournir n'a jamais de bouton de rédaction
    cdsco = page.locator("article.piece", has_text="CDSCO")
    expect(cdsco.get_by_role("button", name="Relancer la rédaction")).to_have_count(0)
    expect(cdsco.get_by_text("Traduction assermentée requise")).to_be_visible()

    # 6. Validation humaine d'une pièce à fournir (commentaire obligatoire)
    cdsco.get_by_role("button", name="Marquer reçue et vérifiée").click()
    confirmer = cdsco.get_by_role("button", name="Confirmer la validation (Testeur E2E)")
    expect(confirmer).to_be_disabled()
    cdsco.get_by_role("textbox").fill("Certificat CDSCO reçu le 30/09 — test E2E")
    confirmer.click()
    expect(cdsco.get_by_text("Validée par")).to_be_visible()
    expect(page.locator(".journal").get_by_text("Pièce validée")).to_be_visible()
    etape("pièce à fournir validée (commentaire exigé), journal mis à jour")

    page.screenshot(path=CAPTURES / "3-detail-dossier.png", full_page=True)

    # 7. Retour à la liste : le dossier créé y figure
    page.get_by_role("link", name="Tableau de bord").first.click()
    expect(page.get_by_role("link", name="Stent coronaire (test E2E)").first).to_be_visible()
    page.screenshot(path=CAPTURES / "4-liste-apres-creation.png", full_page=True)
    etape("le dossier créé apparaît dans la liste")

    assert not erreurs_console, f"Erreurs dans la console du navigateur : {erreurs_console}"
    etape("aucune erreur dans la console du navigateur")
    navigateur.close()

print(f"\nParcours E2E réussi — captures dans {CAPTURES}/")
