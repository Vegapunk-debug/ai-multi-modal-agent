"""SM-2 spaced repetition unit tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from server.db.repo import Repo


@pytest.fixture
async def repo(tmp_path):
    db = tmp_path / "test.sqlite"
    r = Repo(db_path=db)
    await r.init()
    return r


@pytest.mark.asyncio
async def test_first_correct_review_schedules_next(repo):
    res = await repo.upsert_vocab("u1", "spanish", "hola", correct=True)
    assert res["repetitions"] == 1
    assert res["interval_days"] == 1.0


@pytest.mark.asyncio
async def test_second_correct_jumps_to_six_days(repo):
    await repo.upsert_vocab("u1", "spanish", "hola", correct=True)
    res = await repo.upsert_vocab("u1", "spanish", "hola", correct=True)
    assert res["repetitions"] == 2
    assert res["interval_days"] == 6.0


@pytest.mark.asyncio
async def test_incorrect_resets_repetitions(repo):
    for _ in range(3):
        await repo.upsert_vocab("u1", "spanish", "hola", correct=True)
    res = await repo.upsert_vocab("u1", "spanish", "hola", correct=False)
    assert res["repetitions"] == 0
    assert res["interval_days"] == 1.0


@pytest.mark.asyncio
async def test_ease_factor_floor(repo):
    for _ in range(5):
        await repo.upsert_vocab("u1", "spanish", "hola", correct=False, quality=0)
    res = await repo.upsert_vocab("u1", "spanish", "hola", correct=False, quality=0)
    assert res["ease"] >= 1.3


@pytest.mark.asyncio
async def test_mistake_log_and_weak_areas(repo):
    await repo.log_mistake("u1", "s1", "spanish", "es_greetings", "buenos días", "buenas días", "gender")
    await repo.log_mistake("u1", "s1", "spanish", "es_greetings", "la cuenta", "el cuenta", "gender")
    await repo.log_mistake("u1", "s1", "spanish", "es_numbers", "siete", "ocho", "vocab")
    weak = await repo.get_weak_areas("u1", "spanish")
    assert weak[0]["error_type"] == "gender"
    assert weak[0]["count"] == 2
