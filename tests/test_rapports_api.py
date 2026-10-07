"""Rapports d'Iris par l'API et par le chat (faux client Claude, aucun reseau).

Parcours complets: question de clarification unique, production en
arriere-plan, telechargement des fichiers, isolement des sessions, quotas,
evenement SSE 'rapport' emis par l'outil generate_report.
"""
import io
import time

import pytest

from conftest import FakeClaude, sse_events

RAPPORTS = "/jarvis/api/rapports"


@pytest.fixture
def client(settings, tmp_path):
    from fastapi.testclient import TestClient

    from jarvis.app import create_app
    settings.rapports_dir = str(tmp_path / "rapports")
    settings.rapports_pdf = False          # Chromium: un seul test dedie, plus bas
    app = create_app(settings)
    with TestClient(app) as c:
        c.app.state.ctx.claude = FakeClaude()
        c.app.state.ctx.rapports.claude = c.app.state.ctx.claude
        yield c


def _session(client):
    return {"X-Jarvis-Session": client.post("/jarvis/api/session").json()["token"]}


def _attendre(client, h, ident, delai=120):
    fin = time.time() + delai
    while time.time() < fin:
        etat = client.get("%s/%s" % (RAPPORTS, ident), headers=h).json()
        if etat["statut"] in ("termine", "echec"):
            return etat
        time.sleep(0.3)
    raise AssertionError("rapport %s toujours en cours" % ident)


def test_parcours_complet_question_puis_rapport(client):
    h = _session(client)
    r = client.post(RAPPORTS, json={"params": {"type": "vulnerabilite", "zone": "Dakar"}},
                    headers=h).json()
    assert r["statut"] == "question" and r["champ"] == "zone"
    code = r["options"][1]["valeur"]["zone_code"]
    r = client.post(RAPPORTS, json={"params": {"type": "vulnerabilite", "zone_code": code}},
                    headers=h).json()
    assert r["statut"] == "lance"
    etat = _attendre(client, h, r["rapport"]["id"])
    assert etat["statut"] == "termine", etat
    assert set(etat["formats"]) == {"html", "docx", "csv"}
    assert etat["redaction"] == "gabarit"          # FakeClaude ne sait pas rediger
    assert etat["resume"] and etat["version_donnees"].startswith("D-")
    for fmt, debut in (("html", b"<!doctype html>"), ("docx", b"PK"), ("csv", b"\xef\xbb\xbfid")):
        f = client.get("%s/%s/fichier?format=%s" % (RAPPORTS, etat["id"], fmt), headers=h)
        assert f.status_code == 200 and f.content.startswith(debut)
        assert "CLIMATSEN_vulnerabilite_dakar" in f.headers["content-disposition"]
        assert f.headers["cache-control"] == "private, no-store"


def test_une_seule_question_par_demande(client):
    h = _session(client)
    assert client.post(RAPPORTS, json={"params": {"type": "vulnerabilite", "zone": "Dakar"}},
                       headers=h).json()["statut"] == "question"
    r = client.post(RAPPORTS, json={"params": {"type": "vulnerabilite", "zone": "Dakar"}},
                    headers=h).json()
    assert r["statut"] == "lance"
    assert any("ambiguë" in x for x in r["rapport"]["hypotheses"])


def test_rapport_invisible_pour_une_autre_session(client):
    h1, h2 = _session(client), _session(client)
    r = client.post(RAPPORTS, json={"params": {"type": "historique", "zone": "Pikine"}},
                    headers=h1).json()
    ident = r["rapport"]["id"]
    _attendre(client, h1, ident)
    assert client.get("%s/%s" % (RAPPORTS, ident), headers=h2).status_code == 404
    assert client.get("%s/%s/fichier?format=html" % (RAPPORTS, ident),
                      headers=h2).status_code == 404
    assert client.get("%s/%s" % (RAPPORTS, ident)).status_code in (401, 403)


@pytest.mark.parametrize("chemin", ["/inconnu", "/R..%2F..", "/R1/fichier?format=exe"])
def test_identifiants_et_formats_invalides(client, chemin):
    h = _session(client)
    assert client.get(RAPPORTS + chemin, headers=h).status_code == 404


def test_parametres_invalides_422(client):
    h = _session(client)
    r = client.post(RAPPORTS, json={"params": {"type": "roman"}}, headers=h)
    assert r.status_code == 422 and "type de rapport inconnu" in r.json()["error"]["message"]


def test_cache_meme_demande_meme_donnees(client):
    h = _session(client)
    p = {"params": {"type": "historique", "zone_code": "SN07"}}
    r1 = client.post(RAPPORTS, json=p, headers=h).json()
    _attendre(client, h, r1["rapport"]["id"])
    h2 = _session(client)
    r2 = client.post(RAPPORTS, json=p, headers=h2).json()
    assert r2["statut"] == "pret" and r2["rapport"]["depuis_cache"]
    f = client.get("%s/%s/fichier?format=docx" % (RAPPORTS, r2["rapport"]["id"]), headers=h2)
    assert f.status_code == 200


def test_quota_un_rapport_en_cours_par_session(client):
    rapports = client.app.state.ctx.rapports
    from jarvis.rapports import gazetteer, spec as S
    from jarvis.rapports.taches import QuotaRapports, Tache
    sp = S.preparer({"type": "historique"}, gazetteer.charger(), [], None)["spec"]
    t = Tache("sess", sp, "public", "cle")
    rapports._taches[t.id] = t                     # une tache "en_cours"
    with pytest.raises(QuotaRapports):
        rapports.lancer("sess", sp)


def test_quota_horaire(client):
    rapports = client.app.state.ctx.rapports
    from jarvis.rapports import gazetteer, spec as S
    from jarvis.rapports.taches import QuotaRapports, Tache
    sp = S.preparer({"type": "historique"}, gazetteer.charger(), [], None)["spec"]
    for i in range(rapports.par_heure):
        t = Tache("sess", sp, "public", "cle%d" % i)
        t.statut = "termine"
        rapports._taches[t.id] = t
    with pytest.raises(QuotaRapports):
        rapports.lancer("sess", sp)


def test_purge_supprime_les_fichiers(client):
    h = _session(client)
    r = client.post(RAPPORTS, json={"params": {"type": "veille", "season": 2023}},
                    headers=h).json()
    etat = _attendre(client, h, r["rapport"]["id"])
    rapports = client.app.state.ctx.rapports
    tache = rapports._taches[etat["id"]]
    dossier = tache.dossier
    assert dossier.is_dir()
    tache.cree_le -= rapports.ttl + 1
    rapports.purger()
    assert not dossier.exists()
    assert client.get("%s/%s" % (RAPPORTS, etat["id"]), headers=h).status_code == 404


def test_echec_lisible(client, monkeypatch):
    from jarvis.rapports.collecteurs import CollecteImpossible
    from jarvis.rapports import service

    def casse(*a, **k):
        raise CollecteImpossible("Données insuffisantes pour ce test.")
    monkeypatch.setattr(service, "collecter", casse)
    h = _session(client)
    r = client.post(RAPPORTS, json={"params": {"type": "historique"}}, headers=h).json()
    etat = _attendre(client, h, r["rapport"]["id"])
    assert etat["statut"] == "echec" and etat["erreur"] == "Données insuffisantes pour ce test."


# =============================================================================
# Par le chat: l'outil generate_report et l'evenement SSE
# =============================================================================
def _chat(client, h, tool_calls, message="Rapport sur le risque à Pikine"):
    client.app.state.ctx.claude = FakeClaude(reply="Le rapport se prépare.",
                                             tool_calls=tool_calls)
    reponse = client.post("/jarvis/api/chat", json={"message": message}, headers=h)
    assert reponse.status_code == 200
    return sse_events(reponse.text)


def test_chat_lance_un_rapport_et_annonce_l_evenement(client):
    h = _session(client)
    evts = _chat(client, h, [("generate_report", {"type": "veille", "horizon": "prochaine",
                                                  "zone": "Pikine"})])
    rapports = [d for n, d in evts if n == "rapport"]
    assert len(rapports) == 1 and rapports[0]["statut"] == "lance"
    etat = _attendre(client, h, rapports[0]["id"])
    assert etat["statut"] == "termine"
    assert "2027" in etat["sous_titre"] or "2027" in etat["titre"] or \
        any("2027" in t for t in etat["resume"])


def test_chat_question_sans_evenement_rapport(client):
    h = _session(client)
    evts = _chat(client, h, [("generate_report", {"type": "vulnerabilite", "zone": "Kolda"})])
    assert not [d for n, d in evts if n == "rapport"]
    resultat = client.app.state.ctx.claude.tool_results[0]
    assert '"statut": "question"' in resultat["content"]


def test_chat_figure_a_la_demande(client):
    h = _session(client)
    evts = _chat(client, h, [("make_custom_figure", {
        "dataset": "departements", "mark": "barres_horizontales", "x": "departement",
        "y": "population_2023", "sort": "desc", "top": 5})], message="Population par dép.")
    figs = [d for n, d in evts if n == "figure"]
    assert len(figs) == 1
    png = client.get("/jarvis/api/figures/%s" % figs[0]["id"], headers=h)
    assert png.content[:4] == b"\x89PNG"


def test_chat_figure_absurde_refusee(client):
    h = _session(client)
    evts = _chat(client, h, [("make_custom_figure", {
        "dataset": "departements", "mark": "barres", "group_by": "region",
        "measure": "indice_risque", "aggregation": "moyenne"})])
    assert not [d for n, d in evts if n == "figure"]
    resultat = client.app.state.ctx.claude.tool_results[0]
    assert resultat["is_error"] and "rangs" in resultat["content"]


def test_les_outils_sont_exposes_aux_deux_profils(client):
    from jarvis import tools
    for profil in ("public", "admin"):
        noms = {s["name"] for s in tools.specs_for(profil)}
        assert {"generate_report", "make_custom_figure"} <= noms


def test_sync_renvoie_les_rapports(client):
    h = _session(client)
    client.app.state.ctx.claude = FakeClaude(reply="ok", tool_calls=[
        ("generate_report", {"type": "historique", "zone": "Kolda", "zone_code": "SN07"})])
    r = client.post("/jarvis/api/chat/sync", json={"message": "rapport"}, headers=h).json()
    assert len(r["rapports"]) == 1


# =============================================================================
# PDF par l'API (Chromium)
# =============================================================================
def test_pdf_par_l_api(settings, tmp_path):
    pytest.importorskip("playwright")
    from fastapi.testclient import TestClient
    from pypdf import PdfReader

    from jarvis.app import create_app
    settings.rapports_dir = str(tmp_path / "r")
    settings.rapports_pdf = True
    with TestClient(create_app(settings)) as c:
        c.app.state.ctx.rapports.claude = None
        h = _session(c)
        r = c.post(RAPPORTS, json={"params": {"type": "vulnerabilite", "zone": "Thiaroye"}},
                   headers=h).json()
        etat = _attendre(c, h, r["rapport"]["id"])
        if "pdf" not in etat["formats"]:
            pytest.skip("Chromium indisponible sur cette machine")
        pdf = c.get("%s/%s/fichier?format=pdf" % (RAPPORTS, etat["id"]), headers=h)
        assert pdf.headers["content-type"] == "application/pdf"
        texte = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
        assert "Thiaroye" in texte and etat["version_donnees"] in texte
