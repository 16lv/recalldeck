# RecallDeck

![CI Status](https://github.com/16lv/recalldeck/actions/workflows/ci.yml/badge.svg)

**RecallDeck** is a university module tracker, weighted coursework deadline manager, and **SuperMemo-2 (SM-2)** spaced-repetition revision scheduler built with **Python 3.12**, **FastAPI**, and **SQLite**.

## Why I Built It

During exam revision I wanted a lightweight tool that combined my Cardiff University module coursework deadlines with spaced-repetition topic reviews in one SQLite database, without the complexity of syncing large desktop flashcard decks.

## SuperMemo-2 (SM-2) Scheduling Formula

Each revision topic tracks three state variables across reviews: `repetitions` ($n$), `easiness` ($EF$, initialised at `2.5`), and `interval_days` ($I$). When a review is submitted with recall quality $q \in \{0, 1, 2, 3, 4, 5\}$:

1. **Failed Recall ($q < 3$)**: Resets `repetitions = 0` and `interval_days = 1` so the topic is scheduled again tomorrow.
2. **Successful Recall ($q \ge 3$)**:
   - $n = 0 \implies I = 1\text{ day}$
   - $n = 1 \implies I = 6\text{ days}$
   - $n \ge 2 \implies I = \text{round}(I \times EF)$
3. **Easiness Update**:
   $$EF' = \max\left(1.3,\; EF + 0.1 - (5 - q)\cdot(0.08 + (5 - q)\cdot 0.02)\right)$$
   Clamping $EF' \ge 1.3$ prevents difficult topics from entering an unrecoverable interval decay spiral.

## REST API Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Renders the browser dashboard for viewing and adding modules. |
| `POST` | `/api/modules` | Registers a university module (`code`, `title`, `credits`, `semester`). |
| `GET` | `/api/modules` | Lists all registered modules ordered by code. |
| `POST` | `/api/assessments` | Adds a weighted coursework or exam deadline linked to an existing module. |
| `GET` | `/api/assessments` | Lists assessment deadlines sorted by `due_date` (optional `?module_code=` filter). |
| `POST` | `/api/topics` | Registers a revision topic with initial SM-2 parameters (`EF=2.5`, `interval=1`). |
| `POST` | `/api/topics/{id}/review` | Submits a quality grade (`0..5`) and updates `next_review_date`. |

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

## Known Limitations & Future Improvements

- The embedded HTML workspace on `/` currently focuses on module registration; adding interactive review cards directly in the browser UI for `POST /api/topics/{id}/review` is the next planned improvement.
