"""Hachage et verification du mot de passe administrateur.

Les tests utilisent un cout scrypt reduit (n=2**10 au lieu de 2**14): le
parametre est porte par le hache lui-meme, donc la logique testee est
exactement celle de production, mais la suite reste rapide.
"""
import pytest

from jarvis import auth

COUT_TEST = 2 ** 10
MDP = "mot-de-passe-de-test-2026"


def hacher(mot_de_passe=MDP):
    return auth.hacher(mot_de_passe, n=COUT_TEST)


# --- hachage -----------------------------------------------------------------
def test_format_du_hache():
    h = hacher()
    morceaux = h.split("$")
    assert morceaux[0] == "scrypt"
    assert int(morceaux[1]) == COUT_TEST
    assert len(morceaux) == 6


def test_le_mot_de_passe_n_apparait_pas_dans_le_hache():
    assert MDP not in hacher()


def test_deux_haches_du_meme_mot_de_passe_different():
    """Sel aleatoire: deux comptes au meme mot de passe ne se reconnaissent
    pas, et un hache vole ne se compare pas a une table pre-calculee."""
    assert hacher() != hacher()


def test_les_parametres_sont_portes_par_le_hache():
    """Permet de durcir le cout plus tard sans invalider l'existant."""
    ancien = auth.hacher(MDP, n=2 ** 10)
    recent = auth.hacher(MDP, n=2 ** 11)
    assert auth.verifier(MDP, ancien)
    assert auth.verifier(MDP, recent)


@pytest.mark.parametrize("mauvais", ["", "   ", "court", "onzecarac"])
def test_mot_de_passe_trop_faible_refuse(mauvais):
    with pytest.raises(auth.MotDePasseInvalide):
        auth.hacher(mauvais)


def test_longueur_minimale_acceptee():
    assert auth.hacher("a" * auth.LONGUEUR_MINIMALE, n=COUT_TEST)


# --- verification -------------------------------------------------------------
def test_bon_mot_de_passe():
    assert auth.verifier(MDP, hacher()) is True


def test_mauvais_mot_de_passe():
    assert auth.verifier("autre-mot-de-passe-xyz", hacher()) is False


def test_casse_significative():
    assert auth.verifier(MDP.upper(), hacher()) is False


@pytest.mark.parametrize("stocke", [
    "", None, "nimporte quoi", "scrypt$abc$8$1$sel$hache",
    "scrypt$1024$8$1$pas-du-base64!$xx", "bcrypt$1024$8$1$aaaa$bbbb",
    "scrypt$1024$8$1$aaaa",
])
def test_hache_invalide_ne_leve_jamais(stocke):
    """Une exception ici distinguerait 'mal configure' de 'mauvais mot de
    passe' dans la reponse HTTP, ce qui renseignerait un attaquant."""
    assert auth.verifier(MDP, stocke) is False


def test_mot_de_passe_vide():
    assert auth.verifier("", hacher()) is False
    assert auth.verifier(None, hacher()) is False


def test_profil_admin_non_configure():
    """Hache absent: toute tentative echoue, aucune ne passe."""
    assert auth.verifier(MDP, "") is False
    assert auth.verifier("", "") is False
