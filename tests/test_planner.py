from __future__ import annotations

from fastapi.testclient import TestClient

from src.study_planner.app import PlannerDatabase, compute_sm2_schedule, create_app


def test_sm2_spaced_repetition_interval_progression() -> None:
    reps1, ef1, int1 = compute_sm2_schedule(quality=5, repetitions=0, easiness=2.5, interval_days=1)
    assert (reps1, int1) == (1, 1)
    assert ef1 == 2.6

    reps2, ef2, int2 = compute_sm2_schedule(
        quality=5, repetitions=reps1, easiness=ef1, interval_days=int1
    )
    assert (reps2, int2) == (2, 6)

    reps3, _, int3 = compute_sm2_schedule(
        quality=5, repetitions=reps2, easiness=ef2, interval_days=int2
    )
    assert reps3 == 3
    assert int3 >= 15

    # Low recall quality (<3) resets interval back to 1 day
    reset_reps, _, reset_int = compute_sm2_schedule(
        quality=2, repetitions=reps3, easiness=ef2, interval_days=int3
    )
    assert reset_reps == 0
    assert reset_int == 1


def test_sm2_easiness_floor_never_drops_below_1_3() -> None:
    _, ef, _ = compute_sm2_schedule(quality=0, repetitions=3, easiness=1.35, interval_days=10)
    assert ef >= 1.3


def test_full_module_assessment_and_revision_workflow() -> None:
    db = PlannerDatabase(":memory:")
    client = TestClient(create_app(db))

    mod_resp = client.post(
        "/api/modules",
        json={
            "code": "cm2102",
            "title": "Database Systems",
            "credits": 20,
            "semester": "Autumn",
        },
    )
    assert mod_resp.status_code == 201
    assert mod_resp.json()["code"] == "CM2102"

    modules_list = client.get("/api/modules")
    assert modules_list.status_code == 200
    assert len(modules_list.json()) == 1

    ass_resp = client.post(
        "/api/assessments",
        json={
            "module_code": "CM2102",
            "title": "PostgreSQL Normalization & Indexing Coursework",
            "weight_pct": 40.0,
            "due_date": "2026-11-28",
            "completed": False,
        },
    )
    assert ass_resp.status_code == 201

    topic_resp = client.post(
        "/api/topics",
        params={"module_code": "CM2102", "topic": "BCNF and 3NF Dependency Preservation"},
    )
    assert topic_resp.status_code == 201
    topic_id = topic_resp.json()["id"]

    rev_resp = client.post(f"/api/topics/{topic_id}/review", json={"quality": 5})
    assert rev_resp.status_code == 200
    assert rev_resp.json()["repetitions"] == 1
