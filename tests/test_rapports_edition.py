"""Apercu et modification des rapports (versions), sans reseau.

Le gestionnaire tourne ici sans boucle de service: lancer() et modifier()
s'executent jusqu'au bout avant de rendre la main, ce qui rend chaque etape
directement verifiable.
"""
import json
import time

import pytest

from conftest import FakeClaude, sse_events
from jarvis.rapports import taches
from jarvis.rapports.taches import GestionnaireRapports, ModificationImpossible


class RedacteurModif:
    """Faux modele: applique (ou non) une modification au resume."""

    def __init__(self, mode="ok"):
        self.mode = mode
        self.appels = 0

    async def generer_json(self, system, messages, schema, profile="public", **kw):
        self.appels += 1
        charge = json.loads(messages[0]["content"])
        if "demande_de_modification" not in charge:      # premier jet: le gabarit
            red = dict(charge["gabarit"])
            red["recommandations"] = charge["recommandations_gabarit"]
            return {"text": json.dumps(red), "model": "faux", "usage": {}}
        red = json.loads(json.dumps(charge["redaction_actuelle"]))
        if self.mode == "ok":
            red["resume"] = [{"texte": "Résumé raccourci : rang {{fait:zone_rang}}.",
                              "statut": "observe"}]
            red["note"] = "J'ai raccourci le résumé."
        elif self.mode == "menteur":
            red["resume"] = [{"texte": "On attend 4 000 sinistrés.", "statut": "projete"}]
            red["note"] = "Ajouté."
        else:   # refus explicite: texte garde, explication
            red["note"] = "Aucune donnée de victimes dans la plateforme : rien n'est ajouté."
        return {"text": json.dumps(red), "model": "faux", "usage": {}}


@pytest.fixture
def g(tmp_path):
    return GestionnaireRapports(tmp_path / "r", claude=None, avec_pdf=False)


def _rapport(g, params=None, session="s"):
    params = params or {"type": "vulnerabilite", "zone": "Pikine"}
    r = g.preparer(params, session)
    assert r["statut"] == "pret", r
    t = g.lancer(session, r["spec"], params=params)
    assert t.statut == "termine", t.erreur
    return t


# =============================================================================
# Versions
# =============================================================================
def test_changement_de_zone_nouvelle_version(g):
    t = _rapport(g)
    r = g.modifier("s", t.id, {"changes": {"zone": "Rufisque"}})
    assert r["statut"] == "lance" and r["version"] == 2
    assert t.statut == "termine" and t.erreur is None
    v2 = t.courante
    assert v2.numero == 2 and v2.spec.lieu.nom == "Rufisque"
    assert v2.collecte.registre["zone_nom"].valeur == "Rufisque"
    assert (v2.dossier / "rapport.docx").is_file() and v2.dossier.name == "v2"
    assert (t.versions[0].dossier / "rapport.docx").is_file()       # v1 conservee
    assert any("Pikine → Rufisque" in n for n in v2.notes)
    assert v2.modifies and t.vue()["version"] == 2
    nom = g.fichier("s", t.id, "docx")[1]
    assert nom.endswith("_v2.docx") and "rufisque" in nom


def test_retrait_d_un_visuel_et_robustesse_au_changement_de_zone(g):
    t = _rapport(g)
    etiquettes = t.courante.etiquettes()
    assert etiquettes["Figure 1"].titre.startswith("Décomposition")
    g.modifier("s", t.id, {"remove_visuals": ["figure 1"]})
    titres = [f.titre for f in t.courante.rapport.figures()]
    assert not any(x.startswith("Décomposition") for x in titres)
    g.modifier("s", t.id, {"changes": {"zone": "Rufisque"}})
    titres = [f.titre for f in t.courante.rapport.figures()]
    assert not any(x.startswith("Décomposition") for x in titres)    # reste retiree


def test_tracabilite_non_retirable(g):
    t = _rapport(g)
    etiquettes = t.courante.etiquettes()
    dernier = "Tableau %d" % len(t.courante.rapport.tableaux())
    assert etiquettes[dernier].titre == "Fichiers sources et empreintes"
    with pytest.raises(ModificationImpossible, match="traçabilité"):
        g.modifier("s", t.id, {"remove_visuals": [dernier]})


@pytest.mark.parametrize("demande, message", [
    ({}, "Aucune modification"),
    ({"remove_visuals": ["la jolie carte"]}, "non reconnu"),
    ({"remove_visuals": ["Figure 99"]}, "n'existe pas"),
    ({"instruction": "Simplifie le résumé"}, "rédaction assistée"),
    ({"revert": True}, "pas de version précédente"),
    ({"reference_figures": ["inconnue"]}, "inconnue"),
    ({"extra_figures": [{"dataset": "departements", "mark": "barres", "group_by": "region",
                         "measure": "indice_risque", "aggregation": "moyenne"}]}, "rangs"),
])
def test_demandes_refusees(g, demande, message):
    t = _rapport(g)
    with pytest.raises(ModificationImpossible, match=message):
        g.modifier("s", t.id, demande)
    assert t.courante.numero == 1


def test_zone_ambigue_question(g):
    t = _rapport(g)
    r = g.modifier("s", t.id, {"changes": {"zone": "Dakar"}})
    assert r["statut"] == "question" and len(r["options"]) == 2
    assert t.courante.numero == 1


def test_retour_a_la_version_precedente(g):
    t = _rapport(g)
    n1 = len(t.courante.rapport.figures())
    g.modifier("s", t.id, {"remove_visuals": ["Figure 1"]})
    assert len(t.courante.rapport.figures()) == n1 - 1
    g.modifier("s", t.id, {"revert": True})
    assert t.courante.numero == 3 and len(t.courante.rapport.figures()) == n1
    assert t.courante.notes == ["Retour à la version 2"] or "Retour" in t.courante.notes[0]


def test_ajout_de_figures(g):
    t = _rapport(g)
    g.modifier("s", t.id, {"reference_figures": ["validation_inondations"],
                           "extra_figures": [{"dataset": "communes", "mark": "barres_horizontales",
                                              "x": "COMMUNE", "y": "population_2023",
                                              "filters": [{"column": "Departement", "op": "=",
                                                           "value": "Pikine"}]}]})
    titres = [f.titre for f in t.courante.rapport.figures()]
    assert "Validation de l'indice face aux inondations documentées" in titres
    assert any(f.origine == "a_la_demande" for f in t.courante.rapport.figures())


def test_plafond_de_versions(g, monkeypatch):
    monkeypatch.setattr(taches, "MAX_VERSIONS", 2)
    t = _rapport(g)
    g.modifier("s", t.id, {"remove_visuals": ["Figure 1"]})
    with pytest.raises(ModificationImpossible, match="versions"):
        g.modifier("s", t.id, {"revert": True})


def test_autre_session_et_rapport_par_defaut(g):
    t = _rapport(g)
    with pytest.raises(ModificationImpossible):
        g.modifier("autre", None, {"remove_visuals": ["Figure 1"]})
    r = g.modifier("s", None, {"remove_visuals": ["Figure 1"]})   # le plus recent
    assert r["rapport_id"] == t.id


def test_rapport_repris_du_cache_modifiable(g):
    t1 = _rapport(g, session="a")
    t2 = _rapport(g, session="b")
    assert t2.depuis_cache and t2.courante.dossier == t1.courante.dossier
    g.modifier("b", t2.id, {"remove_visuals": ["Figure 1"]})
    assert t2.id in str(t2.courante.dossier) and t1.courante.numero == 1


def test_purge_conserve_les_fichiers_partages(g):
    t1 = _rapport(g, session="a")
    t2 = _rapport(g, session="b")
    t1.cree_le -= g.ttl + 1
    g.purger()
    assert (t2.courante.dossier / "rapport.html").is_file()
    t2.cree_le -= g.ttl + 1
    g.purger()
    assert not t2.courante.dossier.exists()


# =============================================================================
# Texte modifie par le modele
# =============================================================================
def _avec_modele(tmp_path, mode):
    return GestionnaireRapports(tmp_path / "m", claude=RedacteurModif(mode), avec_pdf=False)


def test_modification_de_texte_appliquee_et_verifiee(tmp_path):
    g = _avec_modele(tmp_path, "ok")
    t = _rapport(g)
    g.modifier("s", t.id, {"instruction": "Raccourcis le résumé"})
    v = t.courante
    assert v.numero == 2 and v.note_ia == "J'ai raccourci le résumé."
    resume = [b.texte for b in v.rapport.sections["resume"].blocs if hasattr(b, "statut")]
    assert resume[0] == "Résumé raccourci : rang 36."
    assert "Résumé raccourci : rang 36." in v.modifies
    # Les textes fixes sont toujours la, reinseres par le code.
    assert any("rang centile" in x for x in v.rapport.textes())


def test_chiffre_invente_jamais_dans_le_rapport(tmp_path):
    g = _avec_modele(tmp_path, "menteur")
    t = _rapport(g)
    g.modifier("s", t.id, {"instruction": "Ajoute le nombre de sinistrés attendus"})
    assert t.courante.numero == 1                      # aucune version creee
    assert "règles" in t.erreur
    assert not any("4 000" in x for x in t.courante.rapport.textes())


def test_refus_explique_sans_version_vide(tmp_path):
    g = _avec_modele(tmp_path, "refus")
    t = _rapport(g)
    g.modifier("s", t.id, {"instruction": "Ajoute le nombre de victimes"})
    assert t.courante.numero == 1
    assert t.erreur.startswith("Aucune donnée de victimes")


def test_texte_refuse_mais_autres_changements_appliques(tmp_path):
    g = _avec_modele(tmp_path, "menteur")
    t = _rapport(g)
    g.modifier("s", t.id, {"instruction": "Invente un chiffre", "remove_visuals": ["Figure 1"]})
    v = t.courante
    assert v.numero == 2 and "Texte inchangé" in v.notes
    assert any("retiré" in n for n in v.notes)


# =============================================================================
# Lecture et apercu
# =============================================================================
def test_plan_du_rapport_pour_le_modele(g):
    t = _rapport(g)
    plan = g.lire("s")
    assert plan["rapport_id"] == t.id and plan["version"] == 1
    assert [s["section"] for s in plan["sections"]][0] == "Titre et contexte"
    visuels = {v["etiquette"]: v for v in plan["visuels"]}
    assert visuels["Figure 1"]["retirable"]
    assert not visuels["Tableau %d" % len(t.courante.rapport.tableaux())]["retirable"]
    assert "recommandations" in plan["sections"][4]


def test_apercu_surligne_seulement_les_changements(g):
    t = _rapport(g)
    v1 = g.apercu("s", t.id)
    assert 'class="modifie"' not in v1
    g.modifier("s", t.id, {"changes": {"zone": "Rufisque"}})
    v2 = g.apercu("s", t.id)
    assert 'class="modifie"' in v2 and "Rufisque" in v2
    exporte = (t.courante.dossier / "rapport.html").read_text(encoding="utf-8")
    assert 'class="modifie"' not in exporte          # jamais dans les fichiers
    assert g.apercu("autre", t.id) is None


# =============================================================================
# API, outils et chat
# =============================================================================
@pytest.fixture
def client(settings, tmp_path):
    from fastapi.testclient import TestClient

    from jarvis.app import create_app
    settings.rapports_dir = str(tmp_path / "api")
    settings.rapports_pdf = False
    with TestClient(create_app(settings)) as c:
        c.app.state.ctx.rapports.claude = None
        yield c


def _attendre(c, h, ident, version=1):
    fin = time.time() + 120
    while time.time() < fin:
        e = c.get("/jarvis/api/rapports/%s" % ident, headers=h).json()
        if e["statut"] == "termine" and e["version"] >= version:
            return e
        if e["statut"] == "echec":
            return e
        time.sleep(0.3)
    raise AssertionError("trop long")


def test_routes_apercu_et_modifier(client):
    h = {"X-Jarvis-Session": client.post("/jarvis/api/session").json()["token"]}
    r = client.post("/jarvis/api/rapports", json={"params": {"type": "vulnerabilite",
                                                            "zone": "Pikine"}}, headers=h).json()
    ident = r["rapport"]["id"]
    _attendre(client, h, ident)
    a = client.get("/jarvis/api/rapports/%s/apercu" % ident, headers=h)
    assert a.status_code == 200 and a.headers["content-type"].startswith("text/html")
    assert "<script" not in a.text
    m = client.post("/jarvis/api/rapports/%s/modifier" % ident,
                    json={"params": {"remove_visuals": ["Figure 1"]}}, headers=h).json()
    assert m["version"] == 2
    e = _attendre(client, h, ident, 2)
    assert e["version"] == 2 and len(e["versions"]) == 2
    assert client.post("/jarvis/api/rapports/%s/modifier" % ident,
                       json={"params": {}}, headers=h).status_code == 422
    h2 = {"X-Jarvis-Session": client.post("/jarvis/api/session").json()["token"]}
    assert client.get("/jarvis/api/rapports/%s/apercu" % ident, headers=h2).status_code == 404
    assert client.post("/jarvis/api/rapports/%s/modifier" % ident, json={"params": {"revert": True}},
                       headers=h2).status_code == 404


def test_chat_edit_report_annonce_la_nouvelle_version(client):
    h = {"X-Jarvis-Session": client.post("/jarvis/api/session").json()["token"]}
    ctx = client.app.state.ctx
    ctx.claude = FakeClaude(reply="ok", tool_calls=[
        ("generate_report", {"type": "vulnerabilite", "zone": "Pikine"})])
    evts = sse_events(client.post("/jarvis/api/chat", json={"message": "rapport"}, headers=h).text)
    ident = [d for n, d in evts if n == "rapport"][0]["id"]
    _attendre(client, h, ident)
    ctx.claude = FakeClaude(reply="ok", tool_calls=[("read_report", {}), (
        "edit_report", {"changes": {"zone": "Rufisque"}, "remove_visuals": ["Figure 1"]})])
    evts = sse_events(client.post("/jarvis/api/chat", json={"message": "pour Rufisque"},
                                  headers=h).text)
    rapports = [d for n, d in evts if n == "rapport"]
    assert len(rapports) == 1 and rapports[0]["id"] == ident and rapports[0]["version"] == 2
    assert any("Rufisque" in m for m in rapports[0]["modifications"])
    plan = json.loads(ctx.claude.tool_results[0]["content"])
    assert plan["rapport_id"] == ident and plan["visuels"]
    assert _attendre(client, h, ident, 2)["version"] == 2


def test_edit_report_sans_rapport(client):
    h = {"X-Jarvis-Session": client.post("/jarvis/api/session").json()["token"]}
    client.app.state.ctx.claude = FakeClaude(reply="ok", tool_calls=[
        ("edit_report", {"instruction": "raccourcis"})])
    evts = sse_events(client.post("/jarvis/api/chat", json={"message": "x"}, headers=h).text)
    assert not [d for n, d in evts if n == "rapport"]
    assert client.app.state.ctx.claude.tool_results[0]["is_error"]


def test_widget_apercu_sans_scripts():
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "jarvis" / "widget" /
              "widget.html").read_text(encoding="utf-8")
    assert 'id="apercu-rapport"' in source
    assert 'sandbox="allow-same-origin"' in source and "allow-scripts" not in source
    assert "/apercu" in source and "Apercu.ouvrir" in source
