# University Study & SM-2 Revision Planner

![CI Status](https://github.com/16lv/study-planner/actions/workflows/ci.yml/badge.svg)

A full-stack academic module, assessment deadline, and **SuperMemo-2 (SM-2)** spaced-repetition revision planner built with **Python 3.12**, **FastAPI**, **SQLite**, and a responsive browser workspace.

## Overview

Built for managing university Computer Science coursework deadlines alongside active recall revision intervals:
- **Module & Credit Tracking:** Register university modules (`CM2102`, `CM2104`, etc.) with credit weights and semester allocation.
- **Weighted Assessment Deadlines:** Track coursework and exam weightings (`weight_pct`) with foreign-key validation against registered modules.
- **SuperMemo-2 Spaced Repetition Scheduler:** Calculates dynamic review intervals (`interval_days`) and easiness factors (`easiness >= 1.3`) based on recall quality ratings (`0..5`).

## Running Locally

```bash
pip install -e ".[dev]"
uvicorn src.study_planner.app:app --reload --port 8000
```

### Run Automated Tests & Linter

```bash
ruff check .
pytest -v
```
