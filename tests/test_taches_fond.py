"""Taches longues de la page Pipeline : lanceur detache, etat, annulation, page.

Le lanceur reel (scripts/lancer_tache.py) execute de petits scripts factices :
aucun vrai calcul. Les fichiers d'etat sont ecrits dans outputs/taches/ sous
des noms de test, supprimes a la fin.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

import taches_fond  # noqa: E402


@pytest.fixture
def nom(request):
    n = "test_%s" % request.node.name[:40]
    yield n
    for ext in (".json", ".log", ".annuler", ".json.tmp"):
        (taches_fond.DOSSIER / (n + ext)).unlink(missing_ok=True)


def _script(tmp_path, corps):
    p = tmp_path / "factice.py"
    p.write_text(corps, encoding="utf-8")
    return str(p)          # chemin absolu : lancer_tache le prend tel quel


def _attendre(nom, etats, delai=120):   # large : la suite complete charge la machine
    fin = time.time() + delai
    while time.time() < fin:
        e = taches_fond.etat(nom)
        if e and e["etat"] in etats:
            return e
        time.sleep(0.5)
    raise AssertionError("etat %s non atteint : %s" % (etats, taches_fond.etat(nom)))


def test_tache_terminee_avec_journal(nom, tmp_path):
    script = _script(tmp_path, "print('annee 2023 : ok')\n")
    assert taches_fond.lancer(nom, script)
    e = _attendre(nom, ("termine",))
    assert e["code"] == 0 and not e["active"] and e["fin"]
    assert "annee 2023 : ok" in taches_fond.journal(nom)


def test_tache_en_erreur(nom, tmp_path):
    script = _script(tmp_path, "import sys\nprint('[ERREUR] cube'); sys.exit(3)\n")
    taches_fond.lancer(nom, script)
    e = _attendre(nom, ("erreur",))
    assert e["code"] == 3 and "[ERREUR] cube" in taches_fond.journal(nom)


def test_une_seule_instance_puis_annulation(nom, tmp_path):
    script = _script(tmp_path, "import time\nprint('debut', flush=True)\ntime.sleep(120)\n")
    assert taches_fond.lancer(nom, script)
    _attendre(nom, ("en_cours",))
    assert taches_fond.active(nom)
    assert taches_fond.lancer(nom, script) is False      # deja en cours
    taches_fond.annuler(nom)
    e = _attendre(nom, ("annule",))
    assert not e["active"]


def test_tache_silencieuse_est_interrompue(nom):
    """Etat 'en_cours' jamais rafraichi (serveur redemarre) : interrompue, pas active."""
    taches_fond.DOSSIER.mkdir(parents=True, exist_ok=True)
    vieux = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    (taches_fond.DOSSIER / (nom + ".json")).write_text(json.dumps(
        {"etat": "en_cours", "debut": vieux, "vu_le": vieux}), encoding="utf-8")
    e = taches_fond.etat(nom)
    assert e["etat"] == "interrompu" and not e["active"]


def test_jamais_lancee():
    assert taches_fond.etat("test_jamais_lancee_xyz") is None
    assert taches_fond.journal("test_jamais_lancee_xyz") == ""


# --- Page Pipeline -------------------------------------------------------------
def _app(onglet, admin):
    import logging
    from streamlit.testing.v1 import AppTest
    logging.disable(logging.WARNING)
    try:
        at = AppTest.from_file(str(RACINE / "scripts" / "dashboard.py"), default_timeout=240)
        at.session_state["nav_page"] = "Pipeline"
        at.session_state["pip_tab"] = onglet
        if admin:
            at.session_state["climatsen_admin"] = True
        at.run()
    finally:
        logging.disable(logging.NOTSET)
    assert not at.exception, [e.value for e in at.exception]
    return at


@pytest.fixture
def sans_widget(monkeypatch):
    monkeypatch.setenv("JARVIS_WIDGET", "off")


def test_la_veille_apparait_avec_ses_boutons_en_admin(sans_widget):
    at = _app("Pipeline d'analyse", admin=True)
    textes = " ".join(m.value for m in at.markdown)
    assert "Veille pré-saison" in textes
    assert "Veille — cube SST compact" in textes
    lancer = [b for b in at.button if b.label == "Lancer"]
    assert len(lancer) == 4                      # etapes 19, 20, 21, 22


def test_aucun_bouton_de_tache_sans_admin(sans_widget):
    at = _app("Pipeline d'analyse", admin=False)
    assert not [b for b in at.button if b.label in ("Lancer", "Annuler")]
    at = _app("Données SST", admin=False)
    assert not [b for b in at.button if b.label in ("Reconstruire le cube", "Annuler")]


def test_onglet_sst_propose_la_reconstruction_du_cube(sans_widget):
    at = _app("Données SST", admin=True)
    textes = " ".join(m.value for m in at.markdown)
    assert "Reconstruire le cube SST" in textes
    if any(p.suffix == ".nc" for p in (RACINE / "data" / "raw" / "SST").glob("*.nc")):
        assert [b for b in at.button if b.label == "Reconstruire le cube"]


# --- Pipeline complet : chaine de scripts --------------------------------------
def _scripts(tmp_path, corps):
    chemins = []
    for k, c in enumerate(corps):
        p = tmp_path / ("etape%d.py" % k)
        p.write_text(c, encoding="utf-8")
        chemins.append(str(p))
    return chemins


def test_chaine_dans_l_ordre(nom, tmp_path):
    # Marqueurs uniques : "A", "B", "C" figurent aussi dans les chemins (C:\...).
    scripts = _scripts(tmp_path, ["print('ETAPE_UN')\n", "print('ETAPE_DEUX')\n",
                                  "print('ETAPE_TROIS')\n"])
    assert taches_fond.lancer_chaine(nom, scripts)
    e = _attendre(nom, ("termine",))
    assert [x["etat"] for x in e["etapes"]] == ["termine"] * 3 and e["total"] == 3
    log = taches_fond.journal(nom, n=200)
    assert log.index("ETAPE_UN") < log.index("ETAPE_DEUX") < log.index("ETAPE_TROIS")


def test_chaine_arretee_a_la_premiere_erreur(nom, tmp_path):
    scripts = _scripts(tmp_path, ["print('A')\n", "import sys\nsys.exit(2)\n",
                                  "open('NE_DOIT_PAS_TOURNER', 'w')\n"])
    taches_fond.lancer_chaine(nom, scripts)
    e = _attendre(nom, ("erreur",))
    assert [x["etat"] for x in e["etapes"]] == ["termine", "erreur", "non_lance"]
    assert e["code"] == 2
    assert "arret de la chaine" in taches_fond.journal(nom, n=200)


def test_pipeline_complet_propose_en_admin(sans_widget):
    at = _app("Pipeline d'analyse", admin=True)
    assert [b for b in at.button if b.label == "Lancer le pipeline complet"]
    textes = " ".join(m.value for m in at.markdown)
    assert "18 étapes" in textes
    ordre = " ".join(m.value for m in at.markdown if "01_detection_extremes.py" in m.value)
    assert ordre.index("01_detection") < ordre.index("04_teleconnections") \
        < ordre.index("19_build_sst_cube") < ordre.index("26_indice") < ordre.index("32_manifest")


def test_ordre_de_la_chaine():
    """Dependances : 01 avant 04/11, 19 avant 20, 26 avant 27 et 29, 33 avant 34
    et 37, le manifeste (lit tout) en dernier ; 21, 22, 35, 36, 38 hors chaine."""
    src =(RACINE / "scripts" / "vues" / "pipeline.py").read_text(encoding="utf-8")
    debut = src.index("_HORS_PAGE = [")
    fin = src.index("HORS_CHAINE = (")
    ids_page = ["01", "02", "03", "03b", "sst", "04", "11", "14", "19", "20"]
    ids_hors = __import__("re").findall(r'\{"id": "(\d+)"', src[debut:fin])
    ordre = ids_page + ids_hors
    pos = {i: k for k, i in enumerate(ordre)}
    for amont, aval in (("01", "04"), ("01", "11"), ("11", "14"), ("19", "20"), ("26", "27"),
                        ("26", "29"), ("27", "29"), ("33", "34"), ("33", "37")):
        assert pos[amont] < pos[aval], (amont, aval)
    assert ordre[-1] == "32"
    assert not {"21", "22", "35", "36", "38"} & set(ordre)


def test_observer_un_processus_ne_le_tue_pas():
    """os.kill(pid, 0) tuait le telechargement sous Windows : la verification
    doit laisser le processus vivant, et reconnaitre un processus termine."""
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(6)"])
    try:
        assert taches_fond.processus_vivant(p.pid)
        assert taches_fond.processus_vivant(p.pid)
        assert p.poll() is None                      # toujours en vie
    finally:
        p.wait()
    assert not taches_fond.processus_vivant(p.pid)
    assert not taches_fond.processus_vivant(None)


@pytest.mark.skipif(os.name == "nt", reason="zombies propres a POSIX")
def test_un_enfant_termine_non_recolte_n_est_pas_vivant():
    """La page lance les telechargements avec Popen sans jamais faire wait() :
    l'enfant termine restait zombie et passait pour vivant."""
    import subprocess
    import time
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    time.sleep(1.5)                                  # fini, mais pas recolte
    assert not taches_fond.processus_vivant(p.pid)


def test_plus_aucun_os_kill_dans_la_page():
    src = (RACINE / "scripts" / "vues" / "pipeline.py").read_text(encoding="utf-8")
    assert "os.kill" not in src
