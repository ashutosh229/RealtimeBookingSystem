from collections import Counter

import pytest

from app.allocation.admission import Chain, CreditWallet, QueueCap, TokenBucket
from app.allocation.fair_share import FairSharePolicy
from app.allocation.fifo import FifoPolicy
from app.allocation.simulator import Request, SimConfig, generate_trace, simulate

FIFO, FAIR = FifoPolicy(), FairSharePolicy()


def flood(counts):
    return [Request(0, u) for u, n in counts.items() for _ in range(n)]


# ---------- token bucket ----------


def test_token_bucket_burst_refill_and_isolation():
    tb = TokenBucket(rate=0.5, burst=2)
    assert [tb.admit(1, 0, 0, 5, i) for i in range(3)] == [None, None, "RATE_LIMITED"]
    assert tb.admit(2, 0, 0, 5, 9) is None  # another user has its own bucket
    assert tb.admit(1, 1, 0, 5, 10) == "RATE_LIMITED"  # 0.5 token: not enough
    assert tb.admit(1, 2, 0, 5, 11) is None  # 1.0 token
    assert tb.admit(1, 100, 0, 5, 12) is None and tb.admit(1, 100, 0, 5, 13) is None
    assert tb.admit(1, 100, 0, 5, 14) == "RATE_LIMITED"  # refill is capped at the burst size


def test_token_bucket_validation():
    for bad in ((-1, 2), (1, 0)):
        with pytest.raises(ValueError):
            TokenBucket(*bad)


# ---------- queue cap and chain ----------


def test_queue_cap_and_chain_order():
    qc = QueueCap(3)
    assert qc.admit(1, 0, 2, 5, 1) is None and qc.admit(1, 0, 3, 5, 2) == "QUEUE_FULL"
    chain = Chain(QueueCap(1), TokenBucket(0, 1))
    assert chain.admit(1, 0, 1, 5, 1) == "QUEUE_FULL"  # rejected first, so no token was spent
    assert chain.admit(1, 0, 0, 5, 2) is None  # the single token is still there
    assert chain.admit(1, 0, 0, 5, 3) == "RATE_LIMITED"
    with pytest.raises(ValueError):
        QueueCap(0)


# ---------- credit wallet ----------


def test_surge_price_rises_with_backlog_and_is_capped():
    w = CreditWallet(income=0, cap=10, base_price=1, surge_k=1, threshold=1, max_price=3)
    assert w.price(5, 10) == 1.0 and w.price(10, 10) == 1.0  # at or below the threshold
    assert w.price(20, 10) == pytest.approx(2.0)
    assert w.price(1000, 10) == 3.0


def test_wallet_escrow_spend_refund_and_income():
    w = CreditWallet(income=1, cap=3, base_price=1, surge_k=0)
    assert [w.admit("u", 0, 0, 5, i) for i in (1, 2, 3, 4)] == [
        None,
        None,
        None,
        "NO_CREDITS",
    ]
    w.on_expire(2)  # refund
    assert w.balance("u", 0) == pytest.approx(1.0)
    w.on_win(1)  # spent: nothing comes back
    w.on_win(3)
    assert w.admit("u", 0, 0, 5, 5) is None and w.admit("u", 0, 0, 5, 6) == "NO_CREDITS"
    assert w.balance("u", 10) == 3  # income accrues but never exceeds the cap
    w.on_expire(999)  # unknown request id is harmless


def test_wallet_validation():
    with pytest.raises(ValueError):
        CreditWallet(income=-1, cap=3)
    with pytest.raises(ValueError):
        CreditWallet(income=1, cap=3, base_price=2, max_price=1)


# ---------- inside the simulator ----------


def test_no_admission_is_the_default_path():
    trace = generate_trace(30, 20, 3, 2.0, seed=5)
    cfg = SimConfig(rounds=20, capacity=3)
    plain = simulate(FAIR, trace, cfg)
    assert plain.rejected == Counter() and plain.retries == 0 and plain.gave_up == Counter()
    assert generate_trace(30, 20, 3, 2.0, seed=5, surge_frac=0.0) == trace


def test_door_rejection_counts_as_an_unserved_attempt():
    cfg = SimConfig(rounds=2, capacity=10, admission=lambda: TokenBucket(0, 2))
    res = simulate(FIFO, flood({0: 5, 1: 1}), cfg)
    assert res.allocated == Counter({0: 2, 1: 1})
    assert res.rejected == Counter({"RATE_LIMITED": 3}) and res.gave_up == Counter({0: 3})
    m = res.metrics
    assert m["success_rate"] == pytest.approx(3 / 6) and m["gave_up_rate"] == pytest.approx(3 / 6)


def test_backoff_retries_recover_rejected_requests_deterministically():
    cfg = SimConfig(
        rounds=12,
        capacity=10,
        patience=10,
        max_retries=3,
        admission_seed=1,
        admission=lambda: TokenBucket(rate=1, burst=1),
    )
    a, b = simulate(FIFO, flood({0: 3}), cfg), simulate(FIFO, flood({0: 3}), cfg)
    assert a.allocated == Counter({0: 3}) and a.gave_up == Counter() and a.retries >= 2
    assert (a.allocated, a.waits, a.retries) == (b.allocated, b.waits, b.retries)
    assert max(a.waits) >= 1  # waiting time includes the backoff delay


def test_retries_stop_at_the_limit_and_the_patience():
    never = SimConfig(
        rounds=12,
        capacity=10,
        patience=10,
        max_retries=2,
        admission=lambda: TokenBucket(0, 1),
    )
    res = simulate(FIFO, flood({0: 3}), never)
    assert res.allocated == Counter({0: 1}) and res.gave_up == Counter({0: 2})
    short = SimConfig(
        rounds=12,
        capacity=10,
        patience=0,
        max_retries=5,
        admission=lambda: TokenBucket(0, 1),
    )
    assert simulate(FIFO, flood({0: 3}), short).retries == 0  # a retry would outlive the patience


def test_credit_exhaustion_and_queue_metrics():
    cfg = SimConfig(
        rounds=3,
        capacity=1,
        patience=100,
        admission=lambda: CreditWallet(income=0, cap=2, base_price=1, surge_k=0),
    )
    res = simulate(FIFO, flood({0: 4, 1: 1}), cfg)
    assert res.rejected == Counter({"NO_CREDITS": 2}) and res.gave_up == Counter({0: 2})
    plain = simulate(FIFO, flood({0: 6}), SimConfig(rounds=1, capacity=1, patience=100))
    assert plain.metrics["queue_peak"] == 6 and plain.metrics["queue_mean"] == pytest.approx(6.0)


def test_surge_trace_concentrates_requests_and_keeps_volume():
    flat = generate_trace(100, 100, 10, 2.0, seed=4)
    surge = generate_trace(100, 100, 10, 2.0, seed=4, surge_frac=1.0, surge_start=40, surge_len=3)
    assert len(flat) == len(surge) and all(40 <= r.round < 43 for r in surge)
    mixed = generate_trace(100, 100, 10, 2.0, seed=4, surge_frac=0.5, surge_start=40, surge_len=3)
    assert 0.4 < sum(1 for r in mixed if 40 <= r.round < 43) / len(mixed) < 0.6


def test_token_bucket_improves_the_heavy_users_share_during_a_flash_crowd():
    users, rounds, cap = 100, 60, 10
    trace = generate_trace(
        users, rounds, cap, 2.0, seed=3, surge_frac=0.5, surge_start=20, surge_len=3
    )
    base = SimConfig(rounds=rounds, capacity=cap, heavy_users=frozenset(range(20)))
    cfg = SimConfig(
        rounds=rounds,
        capacity=cap,
        heavy_users=frozenset(range(20)),
        admission=lambda: TokenBucket(0.3, 3),
    )
    unprotected, protected = (
        simulate(FIFO, trace, base).metrics,
        simulate(FIFO, trace, cfg).metrics,
    )
    assert protected["queue_peak"] < unprotected["queue_peak"]
    assert protected["heavy_share_alloc"] < unprotected["heavy_share_alloc"]
    assert protected["gave_up_heavy_share"] > 0.5  # the limiter mostly stops the heavy users
