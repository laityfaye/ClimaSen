"""Outil get_pipeline_status: presence, dates et etapes perimees.

Arborescence temporaire dont on fixe les dates de modification: aucun acces
aux vrais fichiers du projet.
"""
import os

import pytest

from jarvis.tools import pipeline_statut as outil
from jarvis.tools.common import ToolInputError

JOUR = 86400
T0 = 1_750_000_000  # date de reference arbitraire


def _etape(ident, sorties, exports=()):
    return {"id": ident, "num": 1, "label": "Etape %s" % ident,
            "script": "%s.py" % ident, "category": "Test",
            "outputs": list(sorties),
            "exports": {"data": [{"path": p, "label": p} for p in exports]}}


def _ecrire(base, chemin, ts):
    fichier = base / chemin
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text("x", encoding="utf-8")
    os.utime(fichier, (ts, ts))


@pytest.fixture
def projet(tmp_path):
    etapes = [
        _etape("01", ["data/events.csv"], ["data/report.txt"]),
        _etape("sst", ["data/indices.csv"]),
        _etape("04", ["out/corr.csv"]),
        _etape("11", ["out/clusters.csv"], ["out/rapport.txt"]),
        _etape("14", ["out/cartes.png"]),
    ]
    _ecrire(tmp_path, "data/events.csv", T0)
    _ecrire(tmp_path, "data/report.txt", T0)
    _ecrire(tmp_path, "data/indices.csv", T0)
    _ecrire(tmp_path, "out/corr.csv", T0 + JOUR)
    _ecrire(tmp_path, "out/clusters.csv", T0 + 10 * JOUR)
    _ecrire(tmp_path, "out/rapport.txt", T0 + JOUR)
    _ecrire(tmp_path, "out/cartes.png", T0 + 5 * JOUR)   # avant les clusters
    # Pas d'etapes complementaires (26-37) ici : elles ont leurs propres tests.
    return {"pipeline": {"steps": etapes, "base": str(tmp_path), "complementaires": []}}


def _par_id(res):
    return {e["etape"]: e for e in res["etapes"]}


def test_etapes_a_jour(projet):
    etapes = _par_id(outil.run({}, projet))
    assert etapes["01"]["statut"] == "a jour"
    assert etapes["04"]["statut"] == "a jour"
    detail = outil.run({"step": "01"}, projet)["etapes"][0]
    assert detail["fichiers_presents"] == "2/2"


def test_etape_plus_ancienne_que_son_amont_est_a_relancer(projet):
    etapes = _par_id(outil.run({}, projet))
    assert etapes["14"]["statut"] == "a relancer"
    assert etapes["14"]["amont_plus_recent_que_cette_etape"] == ["11"]


def test_amont_relance_rend_l_aval_perime(projet, tmp_path):
    _ecrire(tmp_path, "data/events.csv", T0 + 20 * JOUR)
    etapes = _par_id(outil.run({}, projet))
    assert etapes["04"]["statut"] == "a relancer"
    assert etapes["04"]["amont_plus_recent_que_cette_etape"] == ["01"]


def test_meme_lancement_n_est_pas_perime(projet, tmp_path):
    """Deux etapes ecrites dans la meme minute: pas de fausse alerte."""
    _ecrire(tmp_path, "out/corr.csv", T0 - 30)
    etapes = _par_id(outil.run({}, projet))
    assert etapes["04"]["statut"] == "a jour"


def test_sorties_d_ages_differents_signalees(projet):
    etapes = _par_id(outil.run({}, projet))
    assert etapes["11"]["sorties_de_lancements_differents"] is True
    assert etapes["11"]["ecart_entre_sorties_jours"] == pytest.approx(9.0)
    detail = outil.run({"step": "01"}, projet)["etapes"][0]
    assert detail["sorties_de_lancements_differents"] is False


def test_fichier_manquant(projet, tmp_path):
    (tmp_path / "data/report.txt").unlink()
    etape = _par_id(outil.run({}, projet))["01"]
    assert etape["statut"] == "incomplet"
    assert etape["fichiers_manquants"] == ["data/report.txt"]
    assert etape["fichiers_presents"] == "1/2"


def test_etape_jamais_executee(projet, tmp_path):
    (tmp_path / "out/cartes.png").unlink()
    etape = _par_id(outil.run({}, projet))["14"]
    assert etape["statut"] == "jamais execute (aucune sortie)"
    assert etape["derniere_execution"] is None


def test_une_seule_etape(projet):
    res = outil.run({"step": "SST"}, projet)
    assert [e["etape"] for e in res["etapes"]] == ["sst"]


def test_etape_inconnue(projet):
    with pytest.raises(ToolInputError, match="Valeurs acceptees"):
        outil.run({"step": "99"}, projet)


def test_aucun_chemin_absolu_dans_le_resultat(projet, tmp_path):
    (tmp_path / "data/report.txt").unlink()
    import json
    texte = json.dumps(outil.run({}, projet))
    assert str(tmp_path) not in texte
    assert str(tmp_path).replace("\\", "\\\\") not in texte


def test_resume(projet):
    res = outil.run({}, projet)
    assert res["resume"] == {"a jour": 4, "a relancer": 1}


def test_vue_d_ensemble_compacte_les_etapes_a_jour(projet):
    """Une etape a jour tient en une ligne ; une etape a signaler garde son
    detail (sinon la liste depasse le plafond et sa fin est coupee)."""
    etapes = _par_id(outil.run({}, projet))
    assert set(etapes["01"]) == {"etape", "libelle", "statut", "derniere_execution"}
    assert "amont_plus_recent_que_cette_etape" in etapes["14"]      # a relancer
    assert "ecart_entre_sorties_jours" in etapes["11"]              # heterogene


def test_etapes_complementaires_et_synchronisation_ansd(projet, tmp_path):
    projet["pipeline"]["complementaires"] = [
        _etape("35", ["odp/MANIFEST.json"]), _etape("36", ["out/zones.csv"])]
    outil.DEPENDANCES.setdefault("36", ["35"])
    _ecrire(tmp_path, "out/zones.csv", T0)
    _ecrire(tmp_path, "odp/MANIFEST.json", T0 + JOUR)       # ANSD plus recent
    res = outil.run({}, projet)
    etapes = _par_id(res)
    assert etapes["36"]["statut"] == "a relancer"
    assert res["synchronisation_ansd"]["derniere_synchronisation"] is None
    assert "Synchroniser" in res["synchronisation_ansd"]["note"]


def test_synchronisation_ansd_lue(tmp_path):
    import json
    odp = tmp_path / "data" / "raw" / "ansd" / "odp"
    odp.mkdir(parents=True)
    (odp / ".synchro.json").write_text(json.dumps({
        "etat": "termine", "resultat": "inchange", "fin": "2026-10-09T10:00:00+00:00",
        "derniere_verification": "2026-10-09T10:00:00+00:00", "journal": ["long"]}),
        encoding="utf-8")
    (odp / "MANIFEST.json").write_text(json.dumps({"fichiers": [
        {"fichier": "DF_TX_PAUV.csv", "telecharge_le": "2026-10-08T19:41:19+00:00"}]}),
        encoding="utf-8")
    s = outil._synchro_ansd(tmp_path)
    assert s["copie_telechargee_le"] == "2026-10-08T19:41:19+00:00"
    assert s["derniere_synchronisation"]["resultat"] == "inchange"
    assert "journal" not in s["derniere_synchronisation"]


def test_la_vraie_vue_d_ensemble_tient_sous_le_plafond():
    """Toutes les etapes reelles, page + complementaires, sans troncature."""
    import json
    from jarvis.tools import dataset, registry
    res = outil.run({}, {"pipeline": dataset.get("pipeline")})
    ids = {e["etape"] for e in res["etapes"]}
    assert {"01", "04", "26", "33", "35", "37"} <= ids
    assert len(json.dumps(res, ensure_ascii=False, default=str)) <= registry.MAX_RESULT_CHARS
