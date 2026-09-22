"""Jetons de session: signature, falsification, expiration."""
import time

import pytest

from jarvis.errors import InvalidSessionError
from jarvis.session import issue_token, verify_token

SECRET = "s" * 48


def test_jeton_emis_est_accepte():
    token, info = issue_token(SECRET, "public")
    back = verify_token(SECRET, token, ttl_seconds=3600)
    assert back.session_id == info.session_id
    assert back.profile == "public"


def test_deux_jetons_ont_des_identifiants_distincts():
    a, _ = issue_token(SECRET)
    b, _ = issue_token(SECRET)
    assert a != b


def test_signature_falsifiee_est_refusee():
    token, _ = issue_token(SECRET)
    body, sig = token.split(".")
    with pytest.raises(InvalidSessionError):
        verify_token(SECRET, body + "." + sig[:-2] + "xx", ttl_seconds=3600)


def test_charge_utile_modifiee_est_refusee():
    """Le coeur de la garantie: on ne peut pas se promouvoir admin."""
    import base64
    token, info = issue_token(SECRET, "public")
    _, sig = token.split(".")
    forged_payload = "%s:admin:%d" % (info.session_id, info.issued_at)
    forged_body = base64.urlsafe_b64encode(
        forged_payload.encode()).decode().rstrip("=")
    with pytest.raises(InvalidSessionError):
        verify_token(SECRET, forged_body + "." + sig, ttl_seconds=3600)


def test_autre_secret_est_refuse():
    token, _ = issue_token(SECRET)
    with pytest.raises(InvalidSessionError):
        verify_token("autre-secret-completement-different", token, ttl_seconds=3600)


def test_jeton_expire_est_refuse():
    token, _ = issue_token(SECRET)
    time.sleep(1.1)
    with pytest.raises(InvalidSessionError):
        verify_token(SECRET, token, ttl_seconds=1)


@pytest.mark.parametrize("bad", ["", "nimporte-quoi", "a.b.c", None, 42, "pasdepoint"])
def test_jetons_malformes_sont_refuses(bad):
    with pytest.raises(InvalidSessionError):
        verify_token(SECRET, bad, ttl_seconds=3600)


def test_profil_inconnu_refuse_a_l_emission():
    with pytest.raises(ValueError):
        issue_token(SECRET, "superadmin")
