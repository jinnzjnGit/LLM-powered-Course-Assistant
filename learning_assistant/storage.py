import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from .config import DATABASE_PATH


@contextmanager
def database():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DATABASE_PATH.exists():
        with database() as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(quiz_attempts)")}
            if columns and "attempt_key" not in columns:
                backup_dir = DATABASE_PATH.parent / "backups"
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / f"learning-before-migration-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
                target = sqlite3.connect(backup_path)
                try:
                    connection.backup(target)
                finally:
                    target.close()
    with database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                file_name TEXT NOT NULL,
                objective_correct INTEGER NOT NULL,
                objective_total INTEGER NOT NULL,
                short_score INTEGER NOT NULL,
                short_total INTEGER NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS study_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                plan_days INTEGER NOT NULL,
                daily_minutes INTEGER NOT NULL,
                content TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(quiz_attempts)")}
        if "attempt_key" not in columns:
            connection.execute("ALTER TABLE quiz_attempts ADD COLUMN attempt_key TEXT")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS quiz_attempt_key ON quiz_attempts(attempt_key)")


def save_quiz_attempt(
    file_name: str,
    objective_correct: int,
    objective_total: int,
    short_score: int,
    short_total: int,
    details: list[dict],
    attempt_key: str | None = None,
) -> int:
    with database() as connection:
        if attempt_key:
            row = connection.execute("SELECT id FROM quiz_attempts WHERE attempt_key = ?", (attempt_key,)).fetchone()
            if row:
                return int(row[0])
        cursor = connection.execute(
            """
            INSERT INTO quiz_attempts (
                created_at, file_name, objective_correct, objective_total,
                short_score, short_total, details_json, attempt_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(attempt_key) DO NOTHING
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                file_name,
                objective_correct,
                objective_total,
                short_score,
                short_total,
                json.dumps(details, ensure_ascii=False),
                attempt_key,
            ),
        )
        if attempt_key:
            return int(connection.execute("SELECT id FROM quiz_attempts WHERE attempt_key = ?", (attempt_key,)).fetchone()[0])
        return int(cursor.lastrowid)

def load_quiz_attempts() -> list[dict]:
    with database() as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM quiz_attempts ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]

def save_study_plan(plan_days: int, daily_minutes: int, content: str) -> int:
    with database() as connection:
        cursor = connection.execute(
            """
            INSERT INTO study_plans (created_at, plan_days, daily_minutes, content)
            VALUES (?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                plan_days,
                daily_minutes,
                content,
            ),
        )
        return int(cursor.lastrowid)

def load_latest_study_plan() -> dict | None:
    with database() as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM study_plans ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None
