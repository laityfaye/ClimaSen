"""Seau a jetons: rafale, refus, recharge."""
from jarvis.ratelimit import TokenBucket


def test_rafale_autorisee_jusqu_a_la_capacite():
    b = TokenBucket(capacity=3, refill_per_second=0.0)
    assert [b.consume("u")[0] for _ in range(3)] == [True, True, True]


def test_refus_au_dela_de_la_capacite():
    b = TokenBucket(capacity=2, refill_per_second=0.0)
    b.consume("u"); b.consume("u")
    allowed, retry_after = b.consume("u")
    assert allowed is False
    assert retry_after > 0


def test_les_cles_sont_independantes():
    b = TokenBucket(capacity=1, refill_per_second=0.0)
    assert b.consume("alice")[0] is True
    assert b.consume("bob")[0] is True
    assert b.consume("alice")[0] is False


def test_recharge_avec_le_temps(monkeypatch):
    import jarvis.ratelimit as rl
    faux_temps = {"t": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: faux_temps["t"])

    b = TokenBucket(capacity=2, refill_per_second=1.0)
    b.consume("u"); b.consume("u")
    assert b.consume("u")[0] is False

    faux_temps["t"] += 1.0          # un jeton regenere
    assert b.consume("u")[0] is True
    assert b.consume("u")[0] is False


def test_retry_after_coherent_avec_le_debit():
    b = TokenBucket(capacity=1, refill_per_second=0.5)  # 1 jeton toutes les 2 s
    b.consume("u")
    _, retry_after = b.consume("u")
    assert 1 <= retry_after <= 3


def test_purge_des_seaux_inactifs():
    b = TokenBucket(capacity=2, refill_per_second=100.0, max_keys=5)
    for i in range(20):
        b.consume("cle-%d" % i)
    assert len(b._buckets) <= 5
