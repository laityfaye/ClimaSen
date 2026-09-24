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
    return {"pipeline": {"steps": etapes, "base": str(tmp_path)}}


def _par_id(res):
    return {e["etape"]: e for e in res["etapes"]}


def test_etapes_a_jour(projet):
    etapes = _par_id(outil.run({}, projet))
    assert etapes["01"]["statut"] == "a jour"
    assert etapes["04"]["statut"] == "a jour"
    assert etapes["01"]["fichiers_presents"] == "2/2"


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
    assert etapes["01"]["sorties_de_lancements_differents"] is False


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
