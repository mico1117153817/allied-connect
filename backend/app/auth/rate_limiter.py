"""In-memory rate limiter for PIN and IP based login throttling."""

import time
from collections import defaultdict


class RateLimiter:
    """Track failed login attempts and enforce temporary lockouts.

    PIN lockout: 5 failures within 15 minutes.
    IP ban: 10 failures within 1 hour.
    """

    PIN_MAX_FAILURES: int = 5
    PIN_WINDOW_SECONDS: int = 15 * 60  # 15 minutes

    IP_MAX_FAILURES: int = 10
    IP_WINDOW_SECONDS: int = 60 * 60  # 1 hour

    def __init__(self) -> None:
        self._pin_attempts: dict[str, list[float]] = defaultdict(list)
        self._ip_attempts: dict[str, list[float]] = defaultdict(list)

    # ── helpers ────────────────────────────────────────────────────

    @staticmethod
    def _prune(attempts: list[float], window: int) -> list[float]:
        """Return only timestamps that fall within the *window*."""
        cutoff = time.time() - window
        return [t for t in attempts if t > cutoff]

    # ── PIN ─────────────────────────────────────────────────────────

    def is_pin_locked(self, pin: str) -> bool:
        """True when *pin* has >= PIN_MAX_FAILURES failures in the window."""
        attempts = self._prune(self._pin_attempts[pin], self.PIN_WINDOW_SECONDS)
        self._pin_attempts[pin] = attempts
        return len(attempts) >= self.PIN_MAX_FAILURES

    def record_failed_pin(self, pin: str) -> None:
        """Record a failed authentication attempt for *pin*."""
        self._pin_attempts[pin].append(time.time())

    def clear_pin_attempts(self, pin: str) -> None:
        """Clear all failed attempts for *pin* (e.g. after a successful login)."""
        self._pin_attempts.pop(pin, None)

    # ── IP ──────────────────────────────────────────────────────────

    def is_ip_banned(self, ip: str) -> bool:
        """True when *ip* has >= IP_MAX_FAILURES failures in the window."""
        attempts = self._prune(self._ip_attempts[ip], self.IP_WINDOW_SECONDS)
        self._ip_attempts[ip] = attempts
        return len(attempts) >= self.IP_MAX_FAILURES

    def record_failed_ip(self, ip: str) -> None:
        """Record a failed authentication attempt from *ip*."""
        self._ip_attempts[ip].append(time.time())


# Module-level singleton
rate_limiter = RateLimiter()
