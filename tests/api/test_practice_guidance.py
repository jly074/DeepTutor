"""Synthetic source-quality gates and durable question-specific retest evidence."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from deeptutor.services.practice.guidance import GuidanceUpdate, update, view
from deeptutor.services.practice.storage import PracticeStore, ReviewConflict
from tests.api.test_practice import bank as bank
from tests.api.test_practice import seed


def setting(**kwargs):
    return GuidanceUpdate(
        request_id="guidance_request_0001", version=0, quality="ready", kind="simulated", **kwargs
    )


def inspect(repo, identity, now):
    with repo.connect() as conn:
        return view(
            conn,
            conn.execute("SELECT * FROM notebook_entries WHERE id=?", (identity,)).fetchone(),
            now,
        )


def test_wrong_explanation_delayed_retest_is_not_mastery_and_survives_reopen(bank):
    store, repo, client = bank
    entry = seed(
        store,
        question="中文原文五選項？",
        options={"A": "甲", "B": "乙", "C": "丙", "D": "丁", "E": "戊"},
        explanation="合成來源：乙。",
        source_metadata={"filename": "synthetic.pdf", "pdf_page": 2, "question_number": "7"},
    )
    identity = entry["id"]
    assert inspect(repo, identity, 0)["status"] == "needs_confirmation"
    update(repo, identity, setting(note="合成補講：比較甲與乙。", reference="synthetic.pdf p2 Q7"))
    original = asyncio.run(store.get_notebook_entry(identity))
    wrong = repo.review(
        identity, "wrong_attempt_0001", repo.state(identity)["version"], "again", "A", 100
    )
    due = wrong["due_at"]
    assert wrong["mastered"] is False and wrong["deferred"]
    assert inspect(repo, identity, 101)["status"] == "retest_waiting"
    repo.review(identity, "early_correct_0001", repo.state(identity)["version"], "good", "B", 101)
    assert inspect(repo, identity, 102)["status"] == "retest_waiting"
    assert inspect(repo, identity, due)["status"] == "retest_due"
    good = repo.review(
        identity, "later_correct_0001", repo.state(identity)["version"], "good", "B", due + 1
    )
    assert good["mastered"] is False
    reopened = PracticeStore(repo.db_path)
    evidence = inspect(reopened, identity, due + 2)
    assert (
        evidence["status"] == "delayed_retest_correct" and evidence["mastery"] == "not_established"
    )
    assert evidence["evidence_ids"] == ["wrong_attempt_0001", "later_correct_0001"]
    after = asyncio.run(store.get_notebook_entry(identity))
    for key in [
        "question",
        "options",
        "correct_answer",
        "source_metadata",
        "user_answer",
        "explanation",
    ]:
        assert after[key] == original[key]


@pytest.mark.parametrize("quality", ["missing_image", "disputed"])
def test_quality_blocks_grade_and_review_without_creating_weakness(bank, quality):
    store, repo, client = bank
    entry = seed(store)
    identity = entry["id"]
    payload = setting().model_copy(update={"quality": quality})
    update(repo, identity, payload)
    before = repo.state(identity)
    assert (
        client.post(f"/practice/questions/{identity}/check", json={"answer": "A"}).json()["correct"]
        is None
    )
    with pytest.raises(ReviewConflict):
        repo.review(identity, "blocked_attempt_0001", before["version"], "again", "A", 100)
    assert repo.state(identity) == before
    data = inspect(repo, identity, 101)
    assert (
        data["status"] == "needs_confirmation"
        and data["evidence_ids"] == []
        and data["attempts"] == []
    )


def test_retry_concurrency_correction_and_source_change(bank):
    store, repo, client = bank
    entry = seed(store)
    identity = entry["id"]
    payload = setting()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: update(repo, identity, payload), range(8)))
    assert inspect(repo, identity, 0)["config"]["version"] == 1
    args = (identity, "same_attempt_0001", repo.state(identity)["version"], "again", "A", 100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: repo.review(*args), range(8)))
    assert all(r == results[0] for r in results)
    assert len(inspect(repo, identity, 101)["attempts"]) == 1
    with pytest.raises(ReviewConflict):
        update(
            repo, identity, payload.model_copy(update={"note": "changed", "reference": "synthetic"})
        )
    correction = payload.model_copy(
        update={
            "request_id": "guidance_request_0002",
            "version": 1,
            "note": "Revised explanation",
            "reference": "Synthetic correction p3",
        }
    )
    update(repo, identity, correction)
    data = inspect(repo, identity, 101)
    assert data["status"] == "awaiting_evidence" and not data["attempts"][0]["current_version"]
    with sqlite3.connect(repo.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM practice_guidance_changes").fetchone()[0] == 2
    repo.review(identity, "new_wrong_attempt_1", repo.state(identity)["version"], "again", "A", 200)
    seed(store, question="Corrected source text")
    changed = inspect(repo, identity, 201)
    assert changed["status"] == "awaiting_evidence"
    assert changed["attempts"][-1]["question_snapshot"]["question"] == "2 + 2?"


def test_note_reference_validation_self_report_and_missing_question(bank):
    store, repo, client = bank
    entry = seed(store)
    identity = entry["id"]
    body = setting().model_dump()
    body["note"] = "Uncited explanation"
    assert client.post(f"/practice/questions/{identity}/guidance", json=body).status_code == 422
    assert (
        client.post("/practice/questions/999999/guidance", json=setting().model_dump()).status_code
        == 404
    )
    update(repo, identity, setting())
    repo.review(
        identity,
        "self_report_0001",
        repo.state(identity)["version"],
        "good",
        "",
        100,
        self_report=True,
    )
    assert inspect(repo, identity, 101)["status"] == "awaiting_evidence"
