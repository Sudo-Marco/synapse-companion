from __future__ import annotations
from pathlib import Path
import sqlite3

class ActionLog:
    """Action audit without keyboard text or window titles."""
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS actions(
                id INTEGER PRIMARY KEY, tool TEXT, outcome TEXT, reward REAL,
                context_category TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)""")

    def record(self, tool: str, outcome: str, reward: float, context_category: str) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO actions(tool,outcome,reward,context_category) VALUES(?,?,?,?)",
                       (tool, outcome, reward, context_category))
