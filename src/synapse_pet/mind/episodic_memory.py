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

    def add(self, context: str, action: str | None, reward: float, emotion: str = "") -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO episodes(context,action,reward,emotion) VALUES(?,?,?,?)",
                       (context, action, reward, emotion))

    def recent(self, limit: int = 100) -> list[tuple[Any, ...]]:
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT context,action,reward,timestamp,emotion FROM episodes ORDER BY id DESC LIMIT ?",
                              (limit,)).fetchall()
