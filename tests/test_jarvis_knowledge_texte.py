"""Traitement du texte francais: normalisation, racines, decoupage, extraits.

Ces fonctions sont appliquees des DEUX cotes -- a la construction de l index et
a la recherche. Une divergence entre les deux rendrait l index muet sans
qu aucune erreur ne soit levee: d ou des tests sur les invariants, pas
seulement sur des cas.
"""
import pytest

from jarvis.knowledge import texte


# --- normalisation -----------------------------------------------------------
def test_accents_et_casse():
    assert texte.normaliser("Précipitations Extrêmes") == "precipitations extremes"


def test_les_nombres_sont_conserves():
    """'Nino 3.4' et '1981-2023' doivent rester trouvables."""
    assert texte.tokeniser("Nino 3.4") == ["nino", "3", "4"]
    assert "1981" in texte.tokeniser("periode 1981-2023")


def test_mots_vides_retires():
    assert texte.tokeniser("le role de la correlation") == ["role", "correlation"]


def test_mot_de_discours_retire():
    """Regression: 'plutot' et 'base' l emportaient sur 'CHIRPS' dans
    'Pourquoi CHIRPS plutot qu une autre base de pluie ?'."""
    assert "plutot" not in texte.tokeniser("CHIRPS plutot qu autre chose")


# --- racines -----------------------------------------------------------------
@pytest.mark.parametrize("pluriel,singulier", [
    ("precipitations", "precipitation"),
    ("evenements", "evenement"),
    ("pluies", "pluie"),
    ("donnees", "donnee"),
])
def test_pluriel_et_singulier_convergent(pluriel, singulier):
    assert texte.tokeniser(pluriel) == texte.tokeniser(singulier)


def test_desuffixation_ne_tronque_pas_les_mots_courts():
    assert texte.racine("sst") == "sst"
    assert texte.racine("lag") == "lag"


# --- synonymes ---------------------------------------------------------------
def test_pluie_retrouve_precipitation():
    """Le corpus dit 'precipitations' la ou un visiteur ecrit 'pluie':
    sans cette table, le terme ne touchait aucun passage (df=0)."""
    assert "precipitation" in texte.etendre_requete("pluie au Senegal")


def test_synonymes_appliques_a_la_requete_seulement():
    assert "precipitation" in texte.etendre_requete("pluie")
    assert "precipitation" not in texte.tokeniser("pluie")


def test_extension_conserve_les_jetons_d_origine():
    etendus = texte.etendre_requete("lag saisonnier")
    assert "lag" in etendus and "decalage" in etendus


# --- decoupage ---------------------------------------------------------------
def test_decoupage_respecte_la_taille_visee():
    paragraphes = ["mot " * 50] * 6
    passages = texte.decouper(paragraphes, taille=100, recouvrement=20)
    assert len(passages) > 1
    assert all(len(p.split()) <= 160 for p in passages)


def test_recouvrement_entre_passages():
    """Sans recouvrement, une phrase a cheval sur deux passages ne serait
    retrouvable dans aucun des deux."""
    paragraphes = ["alpha " * 40, "beta " * 40, "gamma " * 40]
    passages = texte.decouper(paragraphes, taille=60, recouvrement=30)
    assert len(passages) >= 2
    fin_du_premier = passages[0].split()[-5:]
    assert any(mot in passages[1].split() for mot in fin_du_premier)


def test_paragraphe_plus_long_que_la_cible_reste_entier():
    long = "mot " * 400
    passages = texte.decouper([long], taille=100, recouvrement=20)
    assert len(passages) == 1


def test_aucun_paragraphe():
    assert texte.decouper([]) == []


# --- extraits ----------------------------------------------------------------
def test_extrait_court_non_modifie():
    contenu, tronque = texte.extrait("Texte bref.", 100)
    assert contenu == "Texte bref." and tronque is False


def test_extrait_coupe_sur_une_frontiere_de_mot():
    contenu, tronque = texte.extrait("alpha beta gamma delta epsilon" * 10, 40)
    assert tronque is True
    assert contenu.endswith("[...]")
    assert "  " not in contenu


def test_extrait_plafonne_la_longueur():
    contenu, _ = texte.extrait("mot " * 500, 200)
    assert len(contenu) <= 210  # 200 + le marqueur de troncature
