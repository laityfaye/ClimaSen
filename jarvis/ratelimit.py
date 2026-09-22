"""Rate limiting par seau a jetons (token bucket), en memoire.

Pourquoi un seau a jetons plutot qu'un compteur par fenetre: il autorise une
rafale courte (l'utilisateur qui pose 3 questions d'affilee) tout en bornant le
debit moyen, ce qui borne la facture API.

En memoire = suffisant pour un process unique. Multi-worker ou multi-machine
exigerait Redis: note dans jarvis/README.md, a traiter en Phase 6 si besoin.
"""
import threading
import time


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float, max_keys: int = 10000):
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self.max_keys = max_keys
        self._buckets = {}   # key -> [tokens, last_seen]
        self._lock = threading.Lock()

    def consume(self, key: str, amount: float = 1.0) -> tuple:
        """Retourne (autorise: bool, retry_after_secondes: int)."""
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_second)

            if tokens >= amount:
                self._buckets[key] = (tokens - amount, now)
                allowed, retry_after = True, 0
            else:
                self._buckets[key] = (tokens, now)
                missing = amount - tokens
                retry_after = int(missing / self.refill_per_second) + 1 if self.refill_per_second > 0 else 60
                allowed = False

            if len(self._buckets) > self.max_keys:
                self._evict_locked(now)
            return allowed, retry_after

    def _evict_locked(self, now: float) -> None:
        """Purge les seaux pleins (donc inactifs): ils n'ont plus d'etat utile."""
        full = [k for k, (t, _) in self._buckets.items() if t >= self.capacity]
        for k in full:
            del self._buckets[k]
        if len(self._buckets) > self.max_keys:
            oldest = sorted(self._buckets.items(), key=lambda kv: kv[1][1])
            for k, _ in oldest[: len(self._buckets) - self.max_keys]:
                del self._buckets[k]

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
