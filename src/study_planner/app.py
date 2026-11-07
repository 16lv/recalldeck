from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


class ModuleCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=16, pattern="^[A-Za-z0-9_-]+$")
    title: str = Field(..., min_length=3, max_length=140)
    credits: int = Field(default=20, ge=5, le=60)
    semester: str = Field(default="Autumn", pattern="^(Autumn|Spring|Full Year)$")


class AssessmentCreate(BaseModel):
    module_code: str = Field(..., min_length=3, max_length=16)
    title: str = Field(..., min_length=3, max_length=160)
    weight_pct: float = Field(..., gt=0.0, le=100.0)
    due_date: date
    completed: bool = False


class ReviewUpdate(BaseModel):
    quality: int = Field(..., ge=0, le=5)


def compute_sm2_schedule(
    quality: int,
    repetitions: int,
    easiness: float,
    interval_days: int,
) -> tuple[int, float, int]:
    # SuperMemo-2 (SM-2) formula: grades < 3 reset the interval back to 1 day.
    # Easiness factor is clamped at 1.3 so intervals don't get stuck shrinking forever.
    if quality < 0 or quality > 5:
        raise ValueError("SM-2 quality rating must be between 0 and 5")

    if quality < 3:
        new_reps = 0
        next_interval = 1
    else:
        if repetitions == 0:
            next_interval = 1
        elif repetitions == 1:
            next_interval = 6
        else:
            next_interval = max(1, round(interval_days * easiness))
        new_reps = repetitions + 1

    new_ef = easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, round(new_ef, 3))
    return new_reps, new_ef, next_interval


class PlannerDatabase:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS modules (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                credits INTEGER NOT NULL,
                semester TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_code TEXT NOT NULL,
                title TEXT NOT NULL,
                weight_pct REAL NOT NULL,
                due_date TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(module_code) REFERENCES modules(code)
            );

            CREATE TABLE IF NOT EXISTS revision_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_code TEXT NOT NULL,
                topic TEXT NOT NULL,
                repetitions INTEGER NOT NULL DEFAULT 0,
                easiness REAL NOT NULL DEFAULT 2.5,
                interval_days INTEGER NOT NULL DEFAULT 1,
                next_review_date TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def create_module(self, payload: ModuleCreate) -> dict[str, Any]:
        code = payload.code.upper()
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO modules (code, title, credits, semester, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (code, payload.title.strip(), payload.credits, payload.semester, now),
        )
        self._conn.commit()
        return {
            "code": code,
            "title": payload.title.strip(),
            "credits": payload.credits,
            "semester": payload.semester,
            "created_at": now,
        }

    def list_modules(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM modules ORDER BY code ASC").fetchall()
        return [dict(r) for r in rows]

    def create_assessment(self, payload: AssessmentCreate) -> dict[str, Any]:
        code = payload.module_code.upper()
        mod = self._conn.execute(
            "SELECT code FROM modules WHERE code = ?", (code,)
        ).fetchone()
        if mod is None:
            raise KeyError(f"Module '{code}' does not exist")

        cur = self._conn.execute(
            """
            INSERT INTO assessments (module_code, title, weight_pct, due_date, completed)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                code,
                payload.title.strip(),
                payload.weight_pct,
                payload.due_date.isoformat(),
                1 if payload.completed else 0,
            ),
        )
        self._conn.commit()
        return {
            "id": int(cur.lastrowid or 0),
            "module_code": code,
            "title": payload.title.strip(),
            "weight_pct": payload.weight_pct,
            "due_date": payload.due_date.isoformat(),
            "completed": payload.completed,
        }

    def list_assessments(self, module_code: str | None = None) -> list[dict[str, Any]]:
        if module_code:
            rows = self._conn.execute(
                "SELECT * FROM assessments WHERE module_code = ? ORDER BY due_date ASC",
                (module_code.upper(),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM assessments ORDER BY due_date ASC"
            ).fetchall()
        return [
            {
                "id": r["id"],
                "module_code": r["module_code"],
                "title": r["title"],
                "weight_pct": r["weight_pct"],
                "due_date": r["due_date"],
                "completed": bool(r["completed"]),
            }
            for r in rows
        ]

    def add_revision_topic(self, module_code: str, topic: str) -> dict[str, Any]:
        code = module_code.upper()
        today = date.today().isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO revision_topics (
                module_code, topic, repetitions, easiness, interval_days, next_review_date
            ) VALUES (?, ?, 0, 2.5, 1, ?)
            """,
            (code, topic.strip(), today),
        )
        self._conn.commit()
        return {
            "id": int(cur.lastrowid or 0),
            "module_code": code,
            "topic": topic.strip(),
            "repetitions": 0,
            "easiness": 2.5,
            "interval_days": 1,
            "next_review_date": today,
        }

    def record_topic_review(self, topic_id: int, quality: int) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM revision_topics WHERE id = ?", (topic_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Topic ID {topic_id} not found")

        reps, ef, interval = compute_sm2_schedule(
            quality=quality,
            repetitions=int(row["repetitions"]),
            easiness=float(row["easiness"]),
            interval_days=int(row["interval_days"]),
        )
        next_date = (date.today() + timedelta(days=interval)).isoformat()
        self._conn.execute(
            """
            UPDATE revision_topics
            SET repetitions = ?, easiness = ?, interval_days = ?, next_review_date = ?
            WHERE id = ?
            """,
            (reps, ef, interval, next_date, topic_id),
        )
        self._conn.commit()
        return {
            "id": topic_id,
            "module_code": row["module_code"],
            "topic": row["topic"],
            "repetitions": reps,
            "easiness": ef,
            "interval_days": interval,
            "next_review_date": next_date,
        }


def create_app(db: PlannerDatabase | None = None) -> FastAPI:
    active_db = db or PlannerDatabase("study_planner.db")
    app = FastAPI(
        title="University Study & Revision Planner",
        version="1.0.0",
    )

    @app.get("/", response_class=HTMLResponse)
    def index_ui() -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Study Planner · University Module & SM-2 Revision Workspace</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body { background: #0a0a0c; color: #e8e6e1; font-family: system-ui, sans-serif; margin: 0; padding: 2.5rem; }
    .container { max-width: 1080px; margin: 0 auto; }
    h1 { font-size: 2rem; margin-bottom: 0.25rem; }
    .sub { color: #8a8a92; font-family: monospace; font-size: 0.85rem; margin-bottom: 2rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem; }
    .card { background: #111114; border: 1px solid #232328; padding: 1.5rem; }
    label { display: block; font-family: monospace; font-size: 0.75rem; color: #8a8a92; margin-top: 0.75rem; }
    input, select, button { width: 100%; padding: 0.6rem; margin-top: 0.35rem; background: #0a0a0c; border: 1px solid #232328; color: #e8e6e1; box-sizing: border-box; }
    button { background: #4ade80; color: #0a0a0c; font-weight: 700; cursor: pointer; margin-top: 1rem; border: none; }
  </style>
</head>
<body>
  <div class="container">
    <h1>University Study &amp; SM-2 Revision Planner</h1>
    <p class="sub">FastAPI · SQLite · SuperMemo-2 Spaced Repetition · REST API (/docs)</p>
    <div class="grid">
      <div class="card">
        <h2>Add University Module</h2>
        <label>Module Code (e.g. CM2104)</label><input id="code" value="CM2104" />
        <label>Module Title</label><input id="title" value="Computational Mathematics" />
        <label>Credits</label><input id="credits" type="number" value="20" />
        <button onclick="addModule()">Save Module</button>
      </div>
      <div class="card">
        <h2>Registered Modules</h2>
        <pre id="modules-out">Loading...</pre>
      </div>
    </div>
  </div>
  <script>
    async function refresh() {
      const res = await fetch('/api/modules');
      document.getElementById('modules-out').textContent = JSON.stringify(await res.json(), null, 2);
    }
    async function addModule() {
      await fetch('/api/modules', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          code: document.getElementById('code').value,
          title: document.getElementById('title').value,
          credits: Number(document.getElementById('credits').value),
          semester: 'Autumn'
        })
      });
      refresh();
    }
    refresh();
  </script>
</body>
</html>"""

    @app.post("/api/modules", status_code=201)
    def create_module(payload: ModuleCreate) -> dict[str, Any]:
        return active_db.create_module(payload)

    @app.get("/api/modules")
    def list_modules() -> list[dict[str, Any]]:
        return active_db.list_modules()

    @app.post("/api/assessments", status_code=201)
    def create_assessment(payload: AssessmentCreate) -> dict[str, Any]:
        try:
            return active_db.create_assessment(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/assessments")
    def list_assessments(module_code: str | None = None) -> list[dict[str, Any]]:
        return active_db.list_assessments(module_code)

    @app.post("/api/topics", status_code=201)
    def create_topic(module_code: str, topic: str) -> dict[str, Any]:
        return active_db.add_revision_topic(module_code, topic)

    @app.post("/api/topics/{topic_id}/review")
    def review_topic(topic_id: int, payload: ReviewUpdate) -> dict[str, Any]:
        try:
            return active_db.record_topic_review(topic_id, payload.quality)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
