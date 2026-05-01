from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class SimpleRateLimiter:
    """按 key 维度的最小间隔限频（阻塞式）。"""

    min_interval_seconds: float = 0.2
    _last_call_at: Dict[str, float] = field(default_factory=dict)

    def wait(self, key: str) -> None:
        if self.min_interval_seconds <= 0:
            return
        now = time.time()
        last = self._last_call_at.get(key)
        if last is not None:
            gap = now - last
            if gap < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - gap)
        self._last_call_at[key] = time.time()
