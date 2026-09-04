"""Session logging for the chat app (SQLite). Karam owns this file.

Every answered /chat turn is written to a local SQLite file so conversations
can be reviewed and the escalation rule can look back over a session's answers.
Student data never leaves the machine: the DB file is gitignored.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "chatbot.db"


def _connect() -> sqlite3.Connection:
    """Open a connection, creating the data/ folder on first use."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the two tables if they don't already exist. Safe to call on every startup."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                escalated INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources TEXT NOT NULL,
                language TEXT NOT NULL,
                retrieval_score REAL NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )


def log_turn(
    session_id: str,
    question: str,
    answer: str,
    sources: list,
    language: str,
    retrieval_score: float,
) -> None:
    """Insert one answered turn. Creates the session row on the first turn."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, started_at) VALUES (?, ?)",
            (session_id, now),
        )
        conn.execute(
            """INSERT INTO turns
               (session_id, question, answer, sources, language, retrieval_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                question,
                answer,
                json.dumps(sources, ensure_ascii=False),
                language,
                retrieval_score,
                now,
            ),
        )


def check_and_flag_escalation(session_id: str) -> bool:
    """The engineer's rule: if the last 3 answers in this session are identical,
    flag the session (escalated = 1) and return True. Otherwise return False.

    Once a session is flagged it stays flagged; a further identical answer keeps
    returning True, which is the intended behaviour.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT answer FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT 3",
            (session_id,),
        ).fetchall()
        if len(rows) < 3:
            return False
        answers = [r[0] for r in rows]
        if answers[0] == answers[1] == answers[2]:
            conn.execute(
                "UPDATE sessions SET escalated = 1 WHERE id = ?",
                (session_id,),
            )
            return True
        return False


# --- Read helpers for the admin view (read-only) ---

def list_sessions() -> list[dict]:
    """Every session with its turn count, newest first. For the admin view."""
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT s.id, s.started_at, s.escalated, COUNT(t.id) AS turn_count
               FROM sessions s
               LEFT JOIN turns t ON t.session_id = s.id
               GROUP BY s.id, s.started_at, s.escalated
               ORDER BY s.started_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_session_turns(session_id: str) -> list[dict]:
    """All turns for one session, oldest first. `sources` is parsed back to a list."""
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT question, answer, sources, language, retrieval_score, created_at
               FROM turns WHERE session_id = ? ORDER BY id ASC""",
            (session_id,),
        ).fetchall()
        turns = []
        for r in rows:
            turn = dict(r)
            try:
                turn["sources"] = json.loads(turn["sources"])
            except (ValueError, TypeError):
                turn["sources"] = [turn["sources"]]
            turns.append(turn)
        return turns
