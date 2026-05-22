"""SQLite repo: progress, vocab mastery (SM-2), mistakes, sessions."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from server.config import SETTINGS

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class Repo:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or SETTINGS.db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA_PATH.read_text())
            await db.commit()

    async def ensure_user(self, user_id: str, target_lang: str, gender: str | None = None) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, target_lang, gender) VALUES (?, ?, ?)",
                (user_id, target_lang, gender),
            )
            await db.execute(
                "UPDATE users SET target_lang = ? WHERE user_id = ?",
                (target_lang, user_id),
            )
            await db.commit()

    async def start_session(self, session_id: str, user_id: str, target_lang: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO sessions (session_id, user_id, target_lang) VALUES (?, ?, ?)",
                (session_id, user_id, target_lang),
            )
            await db.commit()

    async def end_session(self, session_id: str, summary: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET ended_at = datetime('now'), summary = ? WHERE session_id = ?",
                (summary, session_id),
            )
            await db.commit()

    async def record_lesson(
        self, user_id: str, lesson_id: str, language: str, status: str, score: float | None = None
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            completed_at = "datetime('now')" if status == "completed" else "NULL"
            await db.execute(
                f"""
                INSERT INTO lesson_progress (user_id, lesson_id, language, status, score, completed_at)
                VALUES (?, ?, ?, ?, ?, {completed_at})
                ON CONFLICT(user_id, lesson_id) DO UPDATE SET
                    status=excluded.status, score=excluded.score,
                    completed_at=CASE WHEN excluded.status='completed' THEN datetime('now') ELSE completed_at END
                """,
                (user_id, lesson_id, language, status, score),
            )
            await db.commit()

    async def log_mistake(
        self,
        user_id: str,
        session_id: str,
        language: str,
        lesson_id: str | None,
        expected: str,
        got: str,
        error_type: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO mistakes (user_id, session_id, language, lesson_id, expected, got, error_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, session_id, language, lesson_id, expected, got, error_type),
            )
            await db.commit()

    async def get_weak_areas(self, user_id: str, language: str, limit: int = 5) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT error_type, COUNT(*) AS count
                   FROM mistakes WHERE user_id = ? AND language = ?
                   GROUP BY error_type ORDER BY count DESC LIMIT ?""",
                (user_id, language, limit),
            )
            return [dict(r) for r in await cur.fetchall()]

    # ---- SM-2 vocabulary scheduling ----

    async def upsert_vocab(
        self,
        user_id: str,
        language: str,
        word: str,
        correct: bool,
        quality: int | None = None,
    ) -> dict[str, Any]:
        """Apply SM-2 update. quality: 0-5 (>=3 = correct)."""
        if quality is None:
            quality = 4 if correct else 2

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM vocab_mastery WHERE user_id = ? AND language = ? AND word = ?",
                (user_id, language, word),
            )
            row = await cur.fetchone()

            if row is None:
                interval_days = 0.0
                ease = 2.5
                reps = 0
                correct_n = 0
                incorrect_n = 0
            else:
                interval_days = row["interval_days"]
                ease = row["ease_factor"]
                reps = row["repetitions"]
                correct_n = row["correct_count"]
                incorrect_n = row["incorrect_count"]

            # SM-2 algorithm
            if quality < 3:
                reps = 0
                interval_days = 1.0
                incorrect_n += 1
            else:
                if reps == 0:
                    interval_days = 1.0
                elif reps == 1:
                    interval_days = 6.0
                else:
                    interval_days = math.ceil(interval_days * ease)
                reps += 1
                correct_n += 1
                ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))

            due_at = (datetime.now(timezone.utc) + timedelta(days=interval_days)).isoformat()

            await db.execute(
                """INSERT INTO vocab_mastery
                   (user_id, language, word, interval_days, ease_factor, repetitions,
                    due_at, correct_count, incorrect_count, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(user_id, language, word) DO UPDATE SET
                       interval_days=excluded.interval_days,
                       ease_factor=excluded.ease_factor,
                       repetitions=excluded.repetitions,
                       due_at=excluded.due_at,
                       correct_count=excluded.correct_count,
                       incorrect_count=excluded.incorrect_count,
                       last_seen=datetime('now')""",
                (user_id, language, word, interval_days, ease, reps, due_at, correct_n, incorrect_n),
            )
            await db.commit()
            return {
                "word": word,
                "interval_days": interval_days,
                "ease": ease,
                "due_at": due_at,
                "repetitions": reps,
            }

    async def get_due_vocab(self, user_id: str, language: str, limit: int = 10) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT word, interval_days, ease_factor, repetitions, correct_count, incorrect_count
                   FROM vocab_mastery
                   WHERE user_id = ? AND language = ? AND due_at <= datetime('now')
                   ORDER BY due_at ASC LIMIT ?""",
                (user_id, language, limit),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def progress_summary(self, user_id: str, language: str) -> dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            lessons_cur = await db.execute(
                """SELECT lesson_id, status, score FROM lesson_progress
                   WHERE user_id = ? AND language = ?""",
                (user_id, language),
            )
            lessons = [dict(r) for r in await lessons_cur.fetchall()]

            vocab_cur = await db.execute(
                """SELECT COUNT(*) AS n_known,
                          SUM(CASE WHEN repetitions >= 3 THEN 1 ELSE 0 END) AS n_mastered
                   FROM vocab_mastery WHERE user_id = ? AND language = ?""",
                (user_id, language),
            )
            vocab = dict(await vocab_cur.fetchone())

            weak = await self.get_weak_areas(user_id, language)
            return {"lessons": lessons, "vocab": vocab, "weak_areas": weak}
