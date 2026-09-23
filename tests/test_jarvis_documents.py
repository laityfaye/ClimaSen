"""Lecture et modification des .docx, et outils admin de redaction.

Chaque test travaille sur un .docx fabrique sur mesure dans un dossier
temporaire: aucun acces au memoire ni a l'article reels, donc aucun risque de
les modifier en lancant la suite.
"""
import json
import zipfile
from pathlib import Path

import pytest

from jarvis import actions, documents, tools

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def fabriquer_docx(chemin: Path, paragraphes):
    """Cree un .docx minimal mais valide: [(style, texte), ...]."""
    corps = []
    for style, texte in paragraphes:
        prop = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
        corps.append('<w:p>%s<w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>'
                     % (prop, texte))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="%s"><w:body>%s</w:body></w:document>'
                % (W, "".join(corps)))
    relations = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/'
                 'package/2006/relationships"/>')
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", relations)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", "<styles/>")


@pytest.fixture
def settings_docs(tmp_path):
    from jarvis.config import Settings

    dossier = tmp_path / "docs"
    dossier.mkdir()
    fabriquer_docx(dossier / "memoire.docx", [
        ("Titre1", "Chapitre 2 : Donnees"),
        ("", "La grille compte 18 x 25 pixels, soit 450 points au total."),
        ("Titre2", "2.1 Precipitations"),
        ("", "Les donnees CHIRPS couvrent 1981-2023 a 0,25 degre."),
        ("", "La grille compte 18 x 25 pixels ailleurs aussi."),
    ])
    fabriquer_docx(dossier / "article.docx", [
        ("Titre1", "1. Introduction"),
        ("", "Un texte court pour l article."),
    ])
    s = Settings(secret_key="k" * 48, env="dev", anthropic_api_key="x",
                 log_dir=str(tmp_path / "logs"),
                 documents_dir=str(dossier),
                 documents_memoire="memoire.docx",
                 documents_article="article.docx")
    return s


@pytest.fixture
def contexte(settings_docs):
    return {"settings": settings_docs, "session_id": "sess1",
            "registre": actions.RegistreActions(ttl_seconds=600)}


# --- lecture ------------------------------------------------------------------
def test_catalogue(settings_docs):
    entrees = {d["cle"]: d for d in documents.catalogue(settings_docs)}
    assert entrees["memoire"]["present"] is True
    assert entrees["memoire"]["taille_ko"] >= 0
    assert "modifie_le" in entrees["article"]


def test_document_inconnu(settings_docs):
    with pytest.raises(documents.DocumentIntrouvable):
        documents.chemin_document(settings_docs, "these_de_quelqu_un_d_autre")


def test_fichier_absent(settings_docs):
    Path(settings_docs.documents_dir, "article.docx").unlink()
    with pytest.raises(documents.DocumentIntrouvable):
        documents.chemin_document(settings_docs, "article")


def test_sections_lues_avec_leur_chemin(settings_docs):
    sections = documents.sections(settings_docs, "memoire")
    chemins = [s["section"] for s in sections]
    assert any("Chapitre 2" in c for c in chemins)
    assert any("2.1 Precipitations" in c for c in chemins)


def test_occurrences_avec_contexte(settings_docs):
    trouvees = documents.occurrences(settings_docs, "memoire", "450 points")
    assert len(trouvees) == 1
    assert "18 x 25" in trouvees[0]["avant"]
    assert trouvees[0]["section"].startswith("Chapitre 2")


def test_occurrences_multiples(settings_docs):
    assert len(documents.occurrences(settings_docs, "memoire", "18 x 25 pixels")) == 2


# --- previsualisation ---------------------------------------------------------
def test_previsualisation_n_ecrit_rien(settings_docs):
    avant = Path(settings_docs.documents_dir, "memoire.docx").read_bytes()
    apercu = documents.previsualiser_remplacement(
        settings_docs, "memoire", "450 points", "460 points")
    assert apercu["n_occurrences"] == 1
    apres = Path(settings_docs.documents_dir, "memoire.docx").read_bytes()
    assert avant == apres


def test_texte_absent(settings_docs):
    with pytest.raises(documents.RemplacementImpossible) as exc:
        documents.previsualiser_remplacement(
            settings_docs, "memoire", "texte qui n existe pas", "x")
    assert "introuvable" in str(exc.value)


def test_remplacement_identique_refuse(settings_docs):
    with pytest.raises(documents.RemplacementImpossible):
        documents.previsualiser_remplacement(
            settings_docs, "memoire", "450 points", "450 points")


def test_texte_vide_refuse(settings_docs):
    with pytest.raises(documents.RemplacementImpossible):
        documents.previsualiser_remplacement(settings_docs, "memoire", "", "x")


# --- application --------------------------------------------------------------
def test_application(settings_docs):
    resultat = documents.appliquer_remplacement(
        settings_docs, "memoire", "450 points", "460 points")
    assert resultat["n_occurrences"] == 1
    texte = " ".join(s["texte"] for s in documents.sections(settings_docs, "memoire"))
    assert "460 points" in texte and "450 points" not in texte


def test_sauvegarde_ecrite_avant_modification(settings_docs):
    original = Path(settings_docs.documents_dir, "memoire.docx").read_bytes()
    resultat = documents.appliquer_remplacement(
        settings_docs, "memoire", "450 points", "460 points")
    sauvegarde = Path(settings_docs.documents_dir, resultat["sauvegarde"])
    assert sauvegarde.exists()
    assert sauvegarde.read_bytes() == original


def test_archive_intacte_sauf_le_texte(settings_docs):
    """Un .docx est un zip: le reconstruire de travers le corromprait."""
    chemin = Path(settings_docs.documents_dir, "memoire.docx")
    with zipfile.ZipFile(chemin) as z:
        avant = {n: z.read(n) for n in z.namelist()}
    documents.appliquer_remplacement(settings_docs, "memoire", "450 points", "460 points")
    with zipfile.ZipFile(chemin) as z:
        assert z.testzip() is None
        apres = {n: z.read(n) for n in z.namelist()}
    assert set(avant) == set(apres)
    modifiees = [n for n in avant if avant[n] != apres[n]]
    assert modifiees == ["word/document.xml"]


def test_toutes_les_occurrences_sont_remplacees(settings_docs):
    resultat = documents.appliquer_remplacement(
        settings_docs, "memoire", "18 x 25 pixels", "18 x 25 cellules")
    assert resultat["n_occurrences"] == 2
    texte = " ".join(s["texte"] for s in documents.sections(settings_docs, "memoire"))
    assert "18 x 25 pixels" not in texte


# --- outils -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outil_list_documents(contexte):
    r = await tools.execute("list_documents", {}, "admin", contexte=contexte)
    assert not r["is_error"]
    assert {d["cle"] for d in json.loads(r["content"])["documents"]} == {"memoire", "article"}


@pytest.mark.asyncio
async def test_outil_find_in_document(contexte):
    r = await tools.execute("find_in_document",
                            {"document": "memoire", "text": "450 points"},
                            "admin", contexte=contexte)
    assert json.loads(r["content"])["n_occurrences"] == 1


@pytest.mark.asyncio
async def test_outil_find_sans_resultat(contexte):
    r = await tools.execute("find_in_document",
                            {"document": "memoire", "text": "zzz"},
                            "admin", contexte=contexte)
    donnees = json.loads(r["content"])
    assert donnees["n_occurrences"] == 0
    assert "scinde" in donnees["message"]


@pytest.mark.asyncio
async def test_outil_propose_n_ecrit_rien(contexte, settings_docs):
    """Le coeur de la Phase 5: proposer ne modifie pas le fichier."""
    avant = Path(settings_docs.documents_dir, "memoire.docx").read_bytes()
    r = await tools.execute("propose_document_edit", {
        "document": "memoire", "old_text": "450 points",
        "new_text": "460 points", "reason": "essai"}, "admin", contexte=contexte)
    donnees = json.loads(r["content"])
    assert donnees["statut"] == "proposition_deposee"
    assert donnees["action_id"]
    assert Path(settings_docs.documents_dir, "memoire.docx").read_bytes() == avant


@pytest.mark.asyncio
async def test_la_proposition_est_listee(contexte):
    await tools.execute("propose_document_edit", {
        "document": "memoire", "old_text": "450 points",
        "new_text": "460 points", "reason": "essai"}, "admin", contexte=contexte)
    assert len(contexte["registre"].lister("sess1")) == 1


@pytest.mark.asyncio
async def test_raison_obligatoire(contexte):
    """L'utilisateur doit savoir POURQUOI on lui propose une modification."""
    r = await tools.execute("propose_document_edit", {
        "document": "memoire", "old_text": "450 points",
        "new_text": "460 points"}, "admin", contexte=contexte)
    assert r["is_error"]
    assert "reason" in json.loads(r["content"])["erreur"]


@pytest.mark.asyncio
async def test_proposition_sur_texte_absent(contexte):
    r = await tools.execute("propose_document_edit", {
        "document": "memoire", "old_text": "absent", "new_text": "x",
        "reason": "essai"}, "admin", contexte=contexte)
    assert r["is_error"]


@pytest.mark.asyncio
async def test_les_outils_de_redaction_sont_admin_seulement(contexte):
    publics = {s["name"] for s in tools.specs_for("public")}
    admins = {s["name"] for s in tools.specs_for("admin")}
    reserves = {"list_documents", "find_in_document", "propose_document_edit"}
    assert reserves & publics == set()
    assert reserves <= admins


@pytest.mark.asyncio
async def test_outil_admin_inexecutable_en_public(contexte, settings_docs):
    avant = Path(settings_docs.documents_dir, "memoire.docx").read_bytes()
    r = await tools.execute("propose_document_edit", {
        "document": "memoire", "old_text": "450 points",
        "new_text": "460 points", "reason": "essai"}, "public", contexte=contexte)
    assert r["is_error"]
    assert Path(settings_docs.documents_dir, "memoire.docx").read_bytes() == avant


# --- execution d'une action approuvee -----------------------------------------
def test_execution_apres_approbation(settings_docs):
    registre = actions.RegistreActions(ttl_seconds=600)
    action = registre.deposer("sess1", "document_remplacer", "resume", {},
                              {"document": "memoire", "avant": "450 points",
                               "apres": "460 points"})
    resultat = actions.executer(settings_docs, registre.recuperer("sess1", action.id))
    assert resultat["n_occurrences"] == 1
    texte = " ".join(s["texte"] for s in documents.sections(settings_docs, "memoire"))
    assert "460 points" in texte
