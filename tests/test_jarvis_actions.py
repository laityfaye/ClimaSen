"""Registre des propositions de modification.

La garantie testee ici est la plus importante de la Phase 5: le modele ne peut
que DEPOSER. L'ecriture passe par une route que seul l'utilisateur declenche.
"""
import time

import pytest

from jarvis import actions


@pytest.fixture
def registre():
    return actions.RegistreActions(ttl_seconds=60)


def deposer(registre, session="sess1"):
    return registre.deposer(session, "document_remplacer", "resume",
                            {"document": "article"},
                            {"document": "article", "avant": "a", "apres": "b"})


def test_depot_en_attente(registre):
    action = deposer(registre)
    assert action.statut == actions.EN_ATTENTE
    assert action.id


def test_listee_pour_sa_session(registre):
    """Regression: _actions vaut {id: (session, action)}; une iteration sur
    .items() comparait l'identifiant d'action a celui de session, et la
    console n'affichait donc jamais aucune proposition."""
    deposer(registre, "sess1")
    liste = registre.lister("sess1")
    assert len(liste) == 1
    assert liste[0]["statut"] == actions.EN_ATTENTE


def test_invisible_pour_une_autre_session(registre):
    deposer(registre, "sess1")
    assert registre.lister("sess2") == []


def test_non_approuvable_depuis_une_autre_session(registre):
    """Une proposition faite dans une session ne doit pas pouvoir etre
    approuvee depuis une autre."""
    action = deposer(registre, "sess1")
    with pytest.raises(actions.ActionIntrouvable):
        registre.recuperer("sess2", action.id)


def test_identifiant_inconnu(registre):
    with pytest.raises(actions.ActionIntrouvable):
        registre.recuperer("sess1", "nexiste-pas")


def test_non_rejouable(registre):
    action = deposer(registre)
    registre.recuperer("sess1", action.id)
    registre.marquer(action, actions.APPLIQUEE, {"ok": True})
    with pytest.raises(actions.ActionIntrouvable) as exc:
        registre.recuperer("sess1", action.id)
    assert "deja traitee" in str(exc.value)


def test_refus_puis_rejeu_impossible(registre):
    action = deposer(registre)
    registre.marquer(action, actions.REFUSEE)
    with pytest.raises(actions.ActionIntrouvable):
        registre.recuperer("sess1", action.id)


def test_expiration(registre, monkeypatch):
    """Une proposition oubliee ne doit pas rester approuvable indefiniment."""
    action = deposer(registre)
    # L'instant doit etre calcule AVANT le remplacement: une lambda qui
    # appelle time.time() appellerait la fonction qu'elle remplace.
    plus_tard = time.time() + 3600
    monkeypatch.setattr(actions.time, "time", lambda: plus_tard)
    with pytest.raises(actions.ActionIntrouvable) as exc:
        registre.recuperer("sess1", action.id)
    assert "expiree" in str(exc.value).lower()


def test_purge_des_traitees(registre):
    for _ in range(3):
        registre.marquer(deposer(registre), actions.APPLIQUEE)
    en_attente = deposer(registre)
    assert registre.purger() == 3
    assert registre.taille() == 1
    assert registre.recuperer("sess1", en_attente.id)


def test_plafond_du_registre():
    petit = actions.RegistreActions(ttl_seconds=60, maximum=5)
    for _ in range(12):
        deposer(petit)
    assert petit.taille() <= 5


def test_type_d_action_inconnu(registre, tmp_path):
    from jarvis.config import Settings

    action = registre.deposer("sess1", "lancer_les_missiles", "resume", {}, {})
    s = Settings(secret_key="k" * 48, env="dev", anthropic_api_key="x",
                 log_dir=str(tmp_path))
    with pytest.raises(actions.ActionIntrouvable):
        actions.executer(s, action)


def test_vue_publique_ne_fuit_pas_la_charge(registre):
    """La charge est ce que le serveur executera: elle n'a rien a faire dans
    la reponse HTTP, qui est lue par le navigateur."""
    action = deposer(registre)
    vue = action.vue_publique()
    assert "payload" not in vue
    assert set(vue) == {"id", "type", "resume", "details", "statut",
                        "cree_le", "expire_dans", "resultat"}
