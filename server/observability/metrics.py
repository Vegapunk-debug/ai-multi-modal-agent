"""Rolling-window latency metrics.

200-sample sliding window per stage. Computes P50/P95/max/mean on demand.
Cheap enough to update every turn.
"""
from __future__ import annotations

import statistics
from collections import deque
from threading import Lock
from typing import Any


class RollingMetrics:
    def __init__(self, window: int = 200):
        self.window = window
        self._buckets: dict[str, deque[float]] = {}
        self._lock = Lock()

    def add(self, stage: str, value: float) -> None:
        if value is None or value < 0:
            return
        with self._lock:
            buf = self._buckets.setdefault(stage, deque(maxlen=self.window))
            buf.append(float(value))

    def _percentile(self, sorted_vals: list[float], q: float) -> float:
        if not sorted_vals:
            return 0.0
        idx = min(len(sorted_vals) - 1, int(round((len(sorted_vals) - 1) * q)))
        return sorted_vals[idx]

    def snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        with self._lock:
            for stage, buf in self._buckets.items():
                vals = sorted(buf)
                if not vals:
                    continue
                out[stage] = {
                    "n": len(vals),
                    "p50_ms": round(self._percentile(vals, 0.5), 1),
                    "p95_ms": round(self._percentile(vals, 0.95), 1),
                    "max_ms": round(vals[-1], 1),
                    "mean_ms": round(statistics.fmean(vals), 1),
                }
        return out


# Module-level singleton shared across requests.
METRICS = RollingMetrics()
