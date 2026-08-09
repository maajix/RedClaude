"""Rate and concurrency, keyed on TARGET rather than on client.

v1 keyed its budget on the engagement and optionally on the tool name, which
means two hunters working the same program could each get the configured rate
and the program saw the sum. The unit a program's Rules of Engagement talks
about is the target, so that is the key here.

In-memory is correct for this prototype because there is exactly one proxy
process. It is NOT correct for v2: the moment a second egress lane exists the
bucket has to be shared, which is v1's `rate_budget.py` lesson. In v2 that
shared bucket is a Postgres row, not a flock'd file.
"""

from __future__ import annotations

import asyncio
import time


class TargetBudget:
    def __init__(self, rate: float, burst: float, max_concurrency: int):
        self.rate = float(rate)
        self.burst = float(burst)
        self.tokens = float(burst)
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()
        self.slots = asyncio.BoundedSemaphore(int(max_concurrency))

    async def throttle(self) -> float:
        """Block until a token is free. Returns milliseconds waited."""
        started = time.monotonic()
        while True:
            async with self.lock:
                now = time.monotonic()
                self.tokens = min(
                    self.burst, self.tokens + max(0.0, now - self.updated) * self.rate
                )
                self.updated = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return (time.monotonic() - started) * 1000.0
                wait = (1.0 - self.tokens) / self.rate
            # Never sleep holding the lock, or one waiter stalls a ready one.
            await asyncio.sleep(wait)


class Budgets:
    def __init__(self, targets: list[dict]):
        self.by_target: dict[str, TargetBudget] = {}
        for target in targets:
            rate = target.get("rate") or {}
            self.by_target[target["id"]] = TargetBudget(
                rate.get("rps", 10.0),
                rate.get("burst", 10),
                rate.get("max_concurrency", 4),
            )

    def get(self, target_id: str) -> TargetBudget | None:
        return self.by_target.get(target_id)
