from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any

class EpisodicMemory:
    """Small local SQLite journal; callers provide privacy-safe context only."""
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY, context TEXT NOT NULL, action TEXT,
                reward REAL NOT NULL, timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                emotion TEXT, rpe REAL NOT NULL DEFAULT 0)""")
            columns = {str(row[1]) for row in db.execute("PRAGMA table_info(episodes)")}
            if "rpe" not in columns:
                db.execute("ALTER TABLE episodes ADD COLUMN rpe REAL NOT NULL DEFAULT 0")
            db.execute("""CREATE TABLE IF NOT EXISTS habits (
                context_category TEXT NOT NULL, action TEXT NOT NULL,
                observations INTEGER NOT NULL DEFAULT 0, mean_rpe REAL NOT NULL DEFAULT 0,
                last_rpe REAL NOT NULL DEFAULT 0, learned INTEGER NOT NULL DEFAULT 0,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(context_category, action))""")

    def add(self, context: str, action: str | None, reward: float,
            emotion: str = "", rpe: float | None = None) -> None:
        learning_rpe = float(reward if rpe is None else rpe)
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO episodes(context,action,reward,emotion,rpe) "
                       "VALUES(?,?,?,?,?)",
                       (context, action, reward, emotion, learning_rpe))

    def recent(self, limit: int = 100) -> list[tuple[Any, ...]]:
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT context,action,reward,timestamp,emotion FROM episodes ORDER BY id DESC LIMIT ?",
                              (limit,)).fetchall()

    def top_rpe(self, limit: int = 12) -> list[tuple[Any, ...]]:
        """Return episodes with highest absolute RPE for optional sleep replay."""
        with sqlite3.connect(self.path) as db:
            return db.execute(
                "SELECT context,action,rpe,timestamp,emotion FROM episodes "
                "WHERE ABS(rpe) > 0 ORDER BY ABS(rpe) DESC, id DESC LIMIT ?",
                (max(0, int(limit)),)).fetchall()

    def replay_candidates(self, limit: int = 12,
                          recent_fraction: float = 0.25) -> list[tuple[Any, ...]]:
        """Mix high-absolute-RPE examples with recent reward events.

        Recent samples keep replay from becoming a pure reward archive. IDs
        are removed from the returned payload after deterministic de-duplication.
        """
        count = max(0, int(limit))
        if count == 0:
            return []
        fraction = max(0.0, min(1.0, float(recent_fraction)))
        top_count = max(1, min(count, int(round(count * (1.0 - fraction)))))
        recent_count = count - top_count
        with sqlite3.connect(self.path) as db:
            top = db.execute(
                "SELECT id,context,action,rpe,timestamp,emotion FROM episodes "
                "WHERE ABS(rpe) > 0 ORDER BY ABS(rpe) DESC,id DESC LIMIT ?",
                (top_count,)
            ).fetchall()
            rows = list(top)
            if recent_count:
                excluded = [int(row[0]) for row in top]
                query = ("SELECT id,context,action,rpe,timestamp,emotion "
                         "FROM episodes WHERE ABS(rpe) > 0")
                params: list[Any] = []
                if excluded:
                    query += f" AND id NOT IN ({','.join('?' for _ in excluded)})"
                    params.extend(excluded)
                query += " ORDER BY id DESC LIMIT ?"
                params.append(recent_count)
                rows.extend(db.execute(query, params).fetchall())
        return [(context, action, rpe, timestamp, emotion)
                for _row_id, context, action, rpe, timestamp, emotion in rows]

    def observe_habit(self, context_category: str, action: str, rpe: float,
                      *, minimum_observations: int = 4,
                      minimum_mean_rpe: float = 0.015) -> bool:
        """Update an aggregate counter and return true exactly on first learning."""
        context = str(context_category)[:32]
        action_name = str(action)[:48]
        value = max(-1.0, min(1.0, float(rpe)))
        with sqlite3.connect(self.path) as db:
            db.execute("""INSERT INTO habits(context_category,action,observations,
                    mean_rpe,last_rpe,learned) VALUES(?,?,1,?,?,0)
                    ON CONFLICT(context_category,action) DO UPDATE SET
                    mean_rpe=(habits.mean_rpe*habits.observations+excluded.last_rpe)/
                             (habits.observations+1),
                    observations=habits.observations+1,
                    last_rpe=excluded.last_rpe,last_updated=CURRENT_TIMESTAMP""",
                       (context, action_name, value, value))
            row = db.execute("SELECT observations,mean_rpe,learned FROM habits "
                             "WHERE context_category=? AND action=?",
                             (context, action_name)).fetchone()
            learned_now = (not bool(row[2]) and int(row[0]) >= minimum_observations
                           and float(row[1]) >= minimum_mean_rpe)
            if learned_now:
                db.execute("UPDATE habits SET learned=1 WHERE context_category=? AND action=?",
                           (context, action_name))
            return learned_now

    def habits(self, limit: int = 100) -> list[tuple[Any, ...]]:
        with sqlite3.connect(self.path) as db:
            return db.execute(
                "SELECT context_category,action,observations,mean_rpe,last_rpe,last_updated "
                "FROM habits ORDER BY learned DESC, observations DESC LIMIT ?",
                (max(0, int(limit)),)).fetchall()
