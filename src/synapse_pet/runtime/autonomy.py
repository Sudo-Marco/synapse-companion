from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time


@dataclass(frozen=True, slots=True)
class StoredPostIt:
    note_id: int
    template: str
    emotion: str
    created_at: float
    expires_at: float
    x: int
    y: int


class AutonomyController:
    """Small, auditable action budget for non-tool pet behaviors."""

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        self.history: deque[float] = deque()
        self.last_by_template: dict[str, float] = {}

    def choose_postit(self, state, rates: dict[str, float], now: float,
                      *, enabled: bool, quiet: bool, proposal_pending: bool) -> str | None:
        cfg = self.config
        postit_cfg = cfg.get("postits", {})
        if (not enabled or not bool(cfg.get("enabled", True))
                or not bool(postit_cfg.get("enabled", True)) or quiet
                or proposal_pending or not bool(cfg.get("behaviors", {}).get("postits", True))):
            return None
        while self.history and now - self.history[0] >= 3600.0:
            self.history.popleft()
        if len(self.history) >= max(0, int(cfg.get("max_actions_per_hour", 6))):
            return None

        signals = (
            (state.stress >= float(postit_cfg.get("stress_threshold", 0.70)), "alerta", "estressado"),
            (float(rates.get("atencao", 0.0)) >= float(
                postit_cfg.get("attention_rate_hz", 1.5)), "conversa", "atencao"),
            (state.boredom >= float(postit_cfg.get("boredom_threshold", 0.84)), "pausa", "entediado"),
            (state.curiosity >= float(postit_cfg.get("curiosity_threshold", 0.84)), "curiosidade", "curioso"),
        )
        state_map = cfg.get("state_behaviors", {})
        cooldowns = cfg.get("cooldowns_s", {})
        for active, template, emotion in signals:
            if not active or state_map.get(emotion) != template:
                continue
            cooldown = max(0.0, float(cooldowns.get(template, 900.0)))
            if now - self.last_by_template.get(template, float("-inf")) < cooldown:
                continue
            self.history.append(now)
            self.last_by_template[template] = now
            return template
        return None


class PostItStore:
    """SQLite persistence for template IDs and geometry, never note text."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS postits(
                id INTEGER PRIMARY KEY,
                template TEXT NOT NULL,
                emotion TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL
            )""")

    def add(self, template: str, emotion: str, x: int, y: int,
            expires_in_s: float, now: float | None = None) -> StoredPostIt:
        created = time.time() if now is None else float(now)
        expires = created + max(1.0, float(expires_in_s))
        with sqlite3.connect(self.path) as db:
            cursor = db.execute(
                "INSERT INTO postits(template,emotion,created_at,expires_at,x,y) "
                "VALUES(?,?,?,?,?,?)", (template, emotion, created, expires, int(x), int(y)))
            note_id = int(cursor.lastrowid)
        return StoredPostIt(note_id, template, emotion, created, expires, int(x), int(y))

    def active(self, now: float | None = None) -> list[StoredPostIt]:
        current = time.time() if now is None else float(now)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM postits WHERE expires_at <= ?", (current,))
            rows = db.execute(
                "SELECT id,template,emotion,created_at,expires_at,x,y FROM postits "
                "ORDER BY created_at").fetchall()
        return [StoredPostIt(int(row[0]), str(row[1]), str(row[2]), float(row[3]),
                             float(row[4]), int(row[5]), int(row[6])) for row in rows]

    def move(self, note_id: int, x: int, y: int) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE postits SET x=?, y=? WHERE id=?",
                       (int(x), int(y), int(note_id)))

    def remove(self, note_id: int) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM postits WHERE id=?", (int(note_id),))

