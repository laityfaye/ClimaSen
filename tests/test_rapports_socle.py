"""Rapports d'Iris, socle: registre de faits, document, manifeste, gazetteer,
fiche de demande et regle de la question unique.

Le gazetteer et la fiche tournent sur un petit jeu synthetique; un test final
verifie la resolution sur les vraies tables (Pikine, Dakar, Mbao).
"""
import datetime as dt

import pandas as pd
import pytest

from jarvis.rapports import document as doc
from jarvis.rapports import faits, gazetteer, manifest
from jarvis.rapports import spec as S
from jarvis.tools.common import ToolInputError

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


# =============================================================================
# Faits
# =============================================================================
def test_formatage_francais():
    r = faits.RegistreFaits()
    r.ajouter("pop", 763377, "population", "observe", "ANSD RGPH-5", "2023", format="entier",
              suffixe=" habitants")
    r.ajouter("indice", 0.2852, "indice", "observe", "s", "p", decimales=2)
    r.ajouter("proba", 0.307, "p", "projete", "s", "p", format="fraction_pct", decimales=0)
    r.ajouter("taux", 9.3, "t", "observe", "s", "p", format="pct", decimales=1)
    r.ajouter("pente", -0.25, "pente", "observe", "s", "p", format="signe", decimales=2)
    r.ajouter("d", "2012-09-28", "date", "observe", "s", "p", format="date")
    assert r.t("pop") == "763 377 habitants"
    assert r.t("indice") == "0,29"
    assert r.t("proba") == "31 %"
    assert r.t("taux") == "9,3 %"
    assert r.t("pente") == "−0,25"
    assert r.t("d") == "28 septembre 2012"


def test_remplacement_des_renvois_et_fait_inconnu():
    r = faits.RegistreFaits()
    r.ajouter("n", 12, "n", "observe", "s", "p", format="entier")
    assert r.remplacer("On compte {{fait:n}} cas, {{ fait : n }} au total.") == \
        "On compte 12 cas, 12 au total."
    assert r.inconnus("{{fait:n}} et {{fait:absent}}") == ["absent"]
    with pytest.raises(faits.FaitInconnu):
        r.remplacer("{{fait:absent}}")


@pytest.mark.parametrize("kwargs", [
    dict(id="x", valeur=1, libelle="l", statut="certain", source="s", periode="p"),
    dict(id="x", valeur=1, libelle="l", statut="observe", source="", periode="p"),
    dict(id="x", valeur=float("nan"), libelle="l", statut="observe", source="s", periode="p"),
    dict(id="x y", valeur=1, libelle="l", statut="observe", source="s", periode="p"),
    dict(id="x", valeur="abc", libelle="l", statut="observe", source="s", periode="p"),
])
def test_faits_invalides_refuses(kwargs):
    with pytest.raises(faits.FaitInvalide):
        faits.Fait(**kwargs)


def test_doublon_et_valeur_absente():
    r = faits.RegistreFaits()
    r.ajouter("a", 1, "a", "observe", "s", "p")
    with pytest.raises(faits.FaitInvalide):
        r.ajouter("a", 2, "a", "observe", "s", "p")
    assert r.ajouter_si("b", None, "b", "observe", "s", "p") is None
    assert r.ajouter_si("c", float("nan"), "c", "observe", "s", "p") is None
    assert "b" not in r and "c" not in r


def test_registre_en_csv():
    r = faits.RegistreFaits()
    r.ajouter("a", 1.5, "lib", "correle", "src", "1983-2023")
    lignes = r.en_csv().splitlines()
    assert lignes[0].startswith("id,libelle,valeur")
    assert "correle" in lignes[1] and "1983-2023" in lignes[1]


# =============================================================================
# Document
# =============================================================================
@pytest.mark.parametrize("manquant", ["titre", "legende", "unite", "periode", "source"])
def test_figure_sans_metadonnee_refusee(manquant):
    champs = dict(png=PNG, titre="T", legende="L", unite="U", periode="P", source="S")
    champs[manquant] = ""
    with pytest.raises(doc.DocumentInvalide):
        doc.Figure(**champs)


def test_figure_sans_image_refusee():
    with pytest.raises(doc.DocumentInvalide):
        doc.Figure(png=b"pas une image", titre="T", legende="L", unite="U", periode="P",
                   source="S")


@pytest.mark.parametrize("manquant", ["titre", "legende", "unite", "periode", "source"])
def test_tableau_sans_metadonnee_refuse(manquant):
    champs = dict(colonnes=["a"], lignes=[["1"]], titre="T", legende="L", unite="U",
                  periode="P", source="S")
    champs[manquant] = ""
    with pytest.raises(doc.DocumentInvalide):
        doc.Tableau(**champs)


def test_tableau_ligne_de_mauvaise_largeur():
    with pytest.raises(doc.DocumentInvalide):
        doc.Tableau(colonnes=["a", "b"], lignes=[["1"]], titre="T", legende="L", unite="U",
                    periode="P", source="S")


def _meta():
    return doc.Meta(id="R1", type="historique", titre="T", sous_titre="S", genere_le="g",
                    version_donnees="D-1", commit="c", redaction="gabarit", modele="aucun",
                    public="p", zone="z", periode="p")


def test_structure_fixe_et_numerotation():
    r = doc.Rapport(_meta())
    assert [s.cle for s in r.dans_l_ordre()] == list(doc.CLES_SECTIONS)
    for cle in doc.CLES_SECTIONS:
        r.ajouter(cle, doc.Paragraphe("texte"))
    r.ajouter("analyse", doc.Figure(png=PNG, titre="A", legende="L", unite="U", periode="P",
                                    source="S"))
    r.ajouter("analyse", doc.Figure(png=PNG, titre="B", legende="L", unite="U", periode="P",
                                    source="S"))
    r.finaliser()
    assert [f.numero for f in r.figures()] == [1, 2]


def test_section_vide_refusee():
    r = doc.Rapport(_meta())
    r.ajouter("contexte", doc.Paragraphe("x"))
    with pytest.raises(doc.DocumentInvalide):
        r.finaliser()


def test_section_inconnue_refusee():
    with pytest.raises(doc.DocumentInvalide):
        doc.Rapport(_meta()).ajouter("annexe_secrete", doc.Paragraphe("x"))


# =============================================================================
# Manifeste
# =============================================================================
def test_manifeste_reproductible_et_sensible_aux_donnees(tmp_path, monkeypatch):
    (tmp_path / "a.csv").write_text("x\n1\n", encoding="utf-8")
    monkeypatch.setattr(manifest, "FICHIERS", {"a": ("a.csv", "S", "P"),
                                               "b": ("absent.csv", "S", "P")})
    m1 = manifest.calculer(tmp_path)
    m2 = manifest.calculer(tmp_path)
    assert m1["version_donnees"] == m2["version_donnees"]
    assert m1["absents"] == ["b"]
    assert m1["fichiers"]["a"]["sha256"]
    (tmp_path / "a.csv").write_text("x\n2\n", encoding="utf-8")
    assert manifest.calculer(tmp_path)["version_donnees"] != m1["version_donnees"]


def test_manifeste_reel_sans_fichier_absent():
    m = manifest.calculer()
    assert m["version_donnees"].startswith("D-")
    assert m["absents"] == []


# =============================================================================
# Gazetteer (synthetique)
# =============================================================================
def _gazetteer():
    dep = pd.DataFrame([
        dict(pcode="SN0101", departement="Dakar", region="Dakar"),
        dict(pcode="SN0103", departement="Pikine", region="Dakar"),
        dict(pcode="SN0701", departement="Kolda", region="Kolda"),
    ])
    arr = pd.DataFrame([
        dict(pcode="SN010302", arrondissement="Thiaroye", departement="Pikine", region="Dakar",
             adm2_pcode="SN0103"),
        dict(pcode="SN010303", arrondissement="Pikine Dagoudane", departement="Pikine",
             region="Dakar", adm2_pcode="SN0103"),
    ])
    com = pd.DataFrame([
        dict(COMMUNE="MBAO", adm3_pcode="SN010302", adm3_name="Thiaroye", adm2_pcode="SN0103",
             adm2_name="Pikine", Region="DAKAR", Departement="PIKINE", population_2023=149456.0),
        dict(COMMUNE="KOLDA", adm3_pcode="SN070101", adm3_name="Sare Bidji",
             adm2_pcode="SN0701", adm2_name="Kolda", Region="KOLDA", Departement="KOLDA",
             population_2023=90000.0),
    ])
    return gazetteer.Gazetteer(dep, arr, com)


@pytest.mark.parametrize("texte, niveaux", [
    ("Pikine", ["departement"]),
    ("pikine", ["departement"]),
    ("Dakar", ["region", "departement"]),
    ("Kolda", ["region", "departement", "commune"]),
    ("Thiaroye", ["arrondissement"]),
    ("Mbao", ["commune"]),
    ("Sénégal", ["pays"]),
    ("tout le pays", ["pays"]),
    ("région de Kolda", ["region"]),
    ("commune de Kolda", ["commune"]),
])
def test_resolution(texte, niveaux):
    r = _gazetteer().resoudre(texte)
    assert [l.niveau for l in r.candidats] == niveaux


def test_faute_de_frappe_et_inconnu():
    g = _gazetteer()
    r = g.resoudre("Pickine")
    assert r.unique is not None and r.unique.nom == "Pikine" and not r.exact
    r = g.resoudre("Paris")
    assert r.candidats == []


def test_commune_rattachee_a_son_arrondissement():
    mbao = _gazetteer().resoudre("Mbao").unique
    assert mbao.pcode_arrondissement == "SN010302"
    assert mbao.region == "Dakar"
    assert mbao.population_2023 == 149456.0
    assert mbao.avec_article().startswith("la commune de Mbao")


# =============================================================================
# Fiche de demande et question unique
# =============================================================================
AUJ = dt.date(2026, 10, 7)


def _prep(params, deja=False, bulletins=(2027, 2023, 2022)):
    return S.preparer(params, _gazetteer(), bulletins, AUJ, question_deja_posee=deja)


@pytest.mark.parametrize("jour, horizon, attendu", [
    (dt.date(2026, 10, 7), "prochaine", 2027),
    (dt.date(2026, 3, 1), "prochaine", 2026),
    (dt.date(2026, 5, 2), "prochaine", 2027),
    (dt.date(2026, 7, 15), "en_cours", 2026),
    (dt.date(2026, 11, 20), "en_cours", 2027),
])
def test_saison_visee(jour, horizon, attendu):
    assert S.saison_visee(horizon, jour) == attendu


def test_hivernage_prochain_calcule_par_le_code():
    r = _prep({"type": "veille", "horizon": "prochaine", "zone": "Pikine"})
    assert r["statut"] == "pret"
    assert r["spec"].saison == 2027
    assert r["spec"].lieu.code == "SN0103"


def test_zone_ambigue_une_question_avec_options():
    r = _prep({"type": "vulnerabilite", "zone": "Dakar"})
    assert r["statut"] == "question" and r["champ"] == "zone"
    assert [o["valeur"] for o in r["options"]] == [{"zone_code": "SN01"},
                                                     {"zone_code": "SN0101"}]


def test_reponse_a_la_question_par_code():
    r = _prep({"type": "vulnerabilite", "zone": "Dakar", "zone_code": "SN0101"})
    assert r["statut"] == "pret" and r["spec"].lieu.niveau == "departement"


def test_apres_une_question_plus_aucune_question():
    r = _prep({"type": "vulnerabilite", "zone": "Dakar"}, deja=True)
    assert r["statut"] == "pret"
    assert any("ambiguë" in h for h in r["spec"].hypotheses)
    r = _prep({}, deja=True)
    assert r["statut"] == "pret" and r["spec"].type == "historique"
    assert any("Type de rapport non précisé" in h for h in r["spec"].hypotheses)


def test_type_manquant_question():
    r = _prep({"zone": "Pikine"})
    assert r["statut"] == "question" and r["champ"] == "type"
    assert len(r["options"]) == 4


def test_vulnerabilite_sans_zone_question_puis_national():
    assert _prep({"type": "vulnerabilite"})["champ"] == "zone"
    r = _prep({"type": "vulnerabilite"}, deja=True)
    assert r["spec"].lieu.niveau == "pays"


def test_historique_sans_zone_national_sans_question():
    r = _prep({"type": "historique"})
    assert r["statut"] == "pret" and r["spec"].lieu.niveau == "pays"
    assert (r["spec"].annee_debut, r["spec"].annee_fin) == (1981, 2023)


def test_periode_hors_donnees_question_puis_complete():
    r = _prep({"type": "historique", "year_min": 2024, "year_max": 2025})
    assert r["statut"] == "question" and r["champ"] == "periode"
    r = _prep({"type": "historique", "year_min": 2024, "year_max": 2025}, deja=True)
    assert (r["spec"].annee_debut, r["spec"].annee_fin) == (1981, 2023)


def test_periode_partielle_bornee_avec_hypothese():
    r = _prep({"type": "historique", "year_min": 1970, "year_max": 2000})
    assert (r["spec"].annee_debut, r["spec"].annee_fin) == (1981, 2000)
    assert any("ramenée" in h for h in r["spec"].hypotheses)


def test_teleconnexions_nationales_et_periode_fixe():
    r = _prep({"type": "teleconnexions", "zone": "Pikine", "year_min": 2000})
    sp = r["spec"]
    assert sp.lieu.niveau == "pays" and (sp.annee_debut, sp.annee_fin) == (1983, 2023)
    assert len(sp.hypotheses) >= 2


def test_saison_sans_bulletin():
    r = _prep({"type": "veille", "season": 2025})
    assert r["statut"] == "question" and r["champ"] == "saison"
    r = _prep({"type": "veille", "season": 2025}, deja=True)
    assert r["spec"].saison in (2023, 2027)


def test_zone_introuvable():
    assert _prep({"type": "historique", "zone": "Paris"})["statut"] == "question"
    r = _prep({"type": "historique", "zone": "Paris"}, deja=True)
    assert r["spec"].lieu.niveau == "pays"


@pytest.mark.parametrize("params", [
    {"type": "roman"}, {"type": "historique", "phase": "hiver"},
    {"type": "historique", "zone_code": "XX99"},
    {"type": "historique", "extra_figures": "pas une liste"},
])
def test_parametres_invalides(params):
    with pytest.raises(ToolInputError):
        _prep(params)


def test_etat_clarification(monkeypatch):
    e = S.EtatClarification(ttl_seconds=10)
    assert not e.deja_posee("s")
    e.noter("s")
    assert e.deja_posee("s") and not e.deja_posee("autre")
    e.effacer("s")
    assert not e.deja_posee("s")


# =============================================================================
# Vraies donnees
# =============================================================================
def test_gazetteer_reel():
    g = gazetteer.charger()
    assert g.resoudre("Pikine").unique.code == "SN0103"
    assert len(g.resoudre("Dakar").candidats) == 2
    mbao = g.resoudre("Mbao").unique
    assert mbao.niveau == "commune" and mbao.arrondissement == "Thiaroye"
    assert sum(1 for l in g.lieux if l.niveau == "commune") >= 550
