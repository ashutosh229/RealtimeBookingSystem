"""Admission control in front of the allocation policy (C3). Pure logic, no I/O.

admit() returns None to let a request into the queue, or a reason code to reject it at the door.
"""

from collections.abc import Hashable
from typing import Protocol


class Admission(Protocol):
    name: str

    def admit(
        self, user: Hashable, rnd: int, queue_len: int, capacity: int, rid: int
    ) -> str | None: ...

    def on_win(self, rid: int) -> None: ...

    def on_expire(self, rid: int) -> None: ...


class TokenBucket:
    """Per-user token bucket: `rate` tokens per round, at most `burst` stored, one token per request."""

    name = "TOKEN_BUCKET"

    def __init__(self, rate: float, burst: float) -> None:
        if rate < 0 or burst < 1:
            raise ValueError("rate must be >= 0 and burst >= 1")
        self.rate, self.burst = rate, burst
        self._state: dict[Hashable, tuple[float, int]] = {}  # user -> (tokens, last round)

    def admit(self, user, rnd, queue_len, capacity, rid):
        tokens, last = self._state.get(user, (float(self.burst), rnd))
        tokens = min(float(self.burst), tokens + self.rate * (rnd - last))
        if tokens >= 1.0:
            self._state[user] = (tokens - 1.0, rnd)
            return None
        self._state[user] = (tokens, rnd)
        return "RATE_LIMITED"

    def on_win(self, rid):
        pass

    def on_expire(self, rid):
        pass


class QueueCap:
    """Tail drop: reject while the queue already holds `max_queue` requests."""

    name = "QUEUE_CAP"

    def __init__(self, max_queue: int) -> None:
        if max_queue < 1:
            raise ValueError("max_queue must be >= 1")
        self.max_queue = max_queue

    def admit(self, user, rnd, queue_len, capacity, rid):
        return "QUEUE_FULL" if queue_len >= self.max_queue else None

    def on_win(self, rid):
        pass

    def on_expire(self, rid):
        pass


class CreditWallet:
    """Simulated credits (not money). Earn `income` per round up to `cap`; a request costs `price`.

    price = min(max_price, base_price * (1 + surge_k * max(0, queue_len / capacity - threshold))).
    The price is held in escrow: spent when the request wins, refunded if it expires unserved.
    """

    name = "CREDITS"

    def __init__(
        self,
        income: float,
        cap: float,
        start: float | None = None,
        base_price: float = 1.0,
        surge_k: float = 1.0,
        threshold: float = 1.0,
        max_price: float = 4.0,
    ) -> None:
        if income < 0 or cap <= 0 or base_price <= 0 or max_price < base_price:
            raise ValueError("invalid wallet parameters")
        self.income, self.cap = income, cap
        self.start = cap if start is None else start
        self.base_price, self.surge_k, self.threshold, self.max_price = (
            base_price,
            surge_k,
            threshold,
            max_price,
        )
        self._state: dict[Hashable, tuple[float, int]] = {}  # user -> (balance, last round)
        self._escrow: dict[int, tuple[Hashable, float]] = {}  # request id -> (user, held price)

    def price(self, queue_len: int, capacity: int) -> float:
        load = queue_len / capacity if capacity else 0.0
        return min(
            self.max_price,
            self.base_price * (1 + self.surge_k * max(0.0, load - self.threshold)),
        )

    def balance(self, user: Hashable, rnd: int) -> float:
        bal, last = self._state.get(user, (self.start, rnd))
        return min(self.cap, bal + self.income * (rnd - last))

    def admit(self, user, rnd, queue_len, capacity, rid):
        bal, p = self.balance(user, rnd), self.price(queue_len, capacity)
        if bal + 1e-9 >= p:
            self._state[user] = (bal - p, rnd)
            self._escrow[rid] = (user, p)
            return None
        self._state[user] = (bal, rnd)
        return "NO_CREDITS"

    def on_win(self, rid):
        self._escrow.pop(rid, None)  # spent

    def on_expire(self, rid):
        held = self._escrow.pop(rid, None)
        if held:
            user, p = held
            bal, last = self._state[user]
            self._state[user] = (bal + p, last)  # refund


class Chain:
    """Apply several controls in order; the first rejection wins. Put cheap global checks first,
    so a rejected request does not burn a user's tokens."""

    name = "CHAIN"

    def __init__(self, *parts: Admission) -> None:
        self.parts = parts

    def admit(self, user, rnd, queue_len, capacity, rid):
        for part in self.parts:
            reason = part.admit(user, rnd, queue_len, capacity, rid)
            if reason:
                return reason
        return None

    def on_win(self, rid):
        for part in self.parts:
            part.on_win(rid)

    def on_expire(self, rid):
        for part in self.parts:
            part.on_expire(rid)
