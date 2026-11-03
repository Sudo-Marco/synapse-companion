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
                reward REAL NOT NULL, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, emotion TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS habits (
                context_category TEXT NOT NULL, action TEXT NOT NULL,
                observations INTEGER NOT NULL DEFAULT 0, mean_rpe REAL NOT NULL DEFAULT 0,
                last_rpe REAL NOT NULL DEFAULT 0, learned INTEGER NOT NULL DEFAULT 0,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(context_category, action))""")

    def add(self, context: str, action: str | None, reward: float, emotion: str = "") -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO episodes(context,action,reward,emotion) VALUES(?,?,?,?)",
                       (context, action, reward, emotion))

    def recent(self, limit: int = 100) -> list[tuple[Any, ...]]:
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT context,action,reward,timestamp,emotion FROM episodes ORDER BY id DESC LIMIT ?",
                              (limit,)).fetchall()

    def top_rewarded(self, limit: int = 12) -> list[tuple[Any, ...]]:
        """Return high-value episodes for optional, bounded sleep replay."""
        with sqlite3.connect(self.path) as db:
            return db.execute(
                "SELECT context,action,reward,timestamp,emotion FROM episodes "
                "WHERE ABS(reward) > 0 ORDER BY ABS(reward) DESC, id DESC LIMIT ?",
                (max(0, int(limit)),)).fetchall()

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
