"""Store de conversations: proprietaire, plafonds, expiration."""
import time

import pytest

from jarvis.conversations import ConversationStore
from jarvis.errors import AccessDeniedError, ConversationNotFoundError


def store(**kw):
    base = dict(ttl_seconds=60, max_turns=5, max_history_chars=1000)
    base.update(kw)
    return ConversationStore(**base)


def test_creation_et_relecture():
    s = store()
    c = s.create("sess-a", "public")
    assert s.get(c.conversation_id, "sess-a").conversation_id == c.conversation_id


def test_une_autre_session_ne_peut_pas_lire_le_fil():
    """Garantie centrale: pas de fuite d'une conversation vers un autre visiteur."""
    s = store()
    c = s.create("sess-a", "public")
    with pytest.raises(AccessDeniedError):
        s.get(c.conversation_id, "sess-b")


def test_identifiant_inconnu():
    with pytest.raises(ConversationNotFoundError):
        store().get("nexistepas", "sess-a")


def test_get_or_create_repart_a_neuf_sur_id_inconnu():
    """Apres un redemarrage serveur, le widget ne doit pas tomber en erreur."""
    s = store()
    c = s.get_or_create("id-perime", "sess-a", "public")
    assert c.conversation_id != "id-perime"


def test_get_or_create_refuse_quand_meme_le_vol_de_fil():
    s = store()
    c = s.create("sess-a", "public")
    with pytest.raises(AccessDeniedError):
        s.get_or_create(c.conversation_id, "sess-b", "public")


def test_expiration_par_ttl():
    s = store(ttl_seconds=0)
    c = s.create("sess-a", "public")
    time.sleep(0.01)
    with pytest.raises(ConversationNotFoundError):
        s.get(c.conversation_id, "sess-a")


def test_plafond_du_nombre_de_tours():
    s = store(max_turns=3)
    c = s.create("sess-a", "public")
    for i in range(10):
        s.append(c, "user", "question %d" % i)
        s.append(c, "assistant", "reponse %d" % i)
    assert len(c.messages) == 6                 # 3 tours
    assert c.messages[0]["role"] == "user"      # contrainte API


def test_plafond_de_taille_de_l_historique():
    s = store(max_turns=50, max_history_chars=200)
    c = s.create("sess-a", "public")
    for i in range(20):
        s.append(c, "user", "q" * 50)
        s.append(c, "assistant", "r" * 50)
    assert sum(len(m["content"]) for m in c.messages) <= 200
    assert c.messages[0]["role"] == "user"


def test_le_dernier_tour_survit_meme_s_il_depasse():
    """Un message tres long ne doit pas effacer la question en cours."""
    s = store(max_history_chars=10)
    c = s.create("sess-a", "public")
    s.append(c, "user", "x" * 500)
    s.append(c, "assistant", "y" * 500)
    assert len(c.messages) == 2


def test_role_invalide_refuse():
    s = store()
    c = s.create("sess-a", "public")
    with pytest.raises(ValueError):
        s.append(c, "system", "tentative d'injection")


def test_purge_supprime_les_fils_expires():
    s = store(ttl_seconds=0)
    s.create("sess-a", "public")
    s.create("sess-b", "public")
    time.sleep(0.01)
    assert s.sweep() == 2
    assert s.size() == 0


def test_garde_fou_memoire():
    s = store(max_conversations=5)
    for i in range(30):
        s.create("sess-%d" % i, "public")
    s.sweep()
    assert s.size() <= 5


def test_export_public_ne_fuit_pas_la_session():
    s = store()
    c = s.create("sess-a", "public")
    s.append(c, "user", "bonjour")
    data = c.to_public_dict()
    assert "session_id" not in data
    assert data["messages"] == [{"role": "user", "content": "bonjour",
                                 "figures": []}]
