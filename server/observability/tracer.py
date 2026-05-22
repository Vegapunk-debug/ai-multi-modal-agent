"""Per-turn JSONL tracing + structured logging."""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import structlog

from server.config import SETTINGS


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()


class TurnTrace:
    """Captures timing + payloads for one user turn."""

    def __init__(self, session_id: str, traces_dir: Path | None = None):
        self.session_id = session_id
        self.turn_id = str(uuid.uuid4())[:8]
        self.start = time.perf_counter()
        self.events: list[dict[str, Any]] = []
        self.dir = traces_dir or SETTINGS.traces_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def event(self, name: str, **payload: Any) -> None:
        self.events.append(
            {
                "t_ms": round((time.perf_counter() - self.start) * 1000, 2),
                "event": name,
                **payload,
            }
        )

    @contextmanager
    def span(self, name: str, **payload: Any) -> Iterator[None]:
        t0 = time.perf_counter()
        self.event(f"{name}.start", **payload)
        try:
            yield
        finally:
            dt = round((time.perf_counter() - t0) * 1000, 2)
            self.event(f"{name}.end", duration_ms=dt)

    def flush(self) -> None:
        path = self.dir / f"{self.session_id}.jsonl"
        record = {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "total_ms": round((time.perf_counter() - self.start) * 1000, 2),
            "events": self.events,
        }
        with path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        log.info(
            "turn.flush",
            session_id=self.session_id,
            turn_id=self.turn_id,
            total_ms=record["total_ms"],
        )
