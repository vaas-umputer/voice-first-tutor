"""Basic sanity tests for problem_bank.py — Section 3 acceptance criteria:
>= 10 problems authored, 3 difficulty levels, one skill cluster for MVP demo."""

from __future__ import annotations

from orchestrator import problem_bank


def test_load_populates_at_least_10_problems():
    problem_bank.load()
    assert len(problem_bank._BANK) >= 10


def test_three_difficulty_levels_present():
    problem_bank.load()
    difficulties = {p.difficulty for p in problem_bank._BANK.values()}
    assert difficulties == {"easy", "medium", "hard"}


def test_select_for_level_respects_difficulty():
    problem_bank.load()
    for _ in range(10):
        p = problem_bank.select_for_level("hard")
        assert p.difficulty == "hard"


def test_select_for_level_respects_exclude_ids():
    problem_bank.load()
    hard_ids = [p.id for p in problem_bank._BANK.values() if p.difficulty == "hard"]
    assert len(hard_ids) >= 2, "need at least 2 hard problems to test exclusion"
    exclude = hard_ids[:-1]  # exclude all but one
    for _ in range(10):
        p = problem_bank.select_for_level("hard", exclude_ids=exclude)
        assert p.id == hard_ids[-1]


def test_select_for_level_wraps_around_when_exhausted():
    problem_bank.load()
    all_hard_ids = [p.id for p in problem_bank._BANK.values() if p.difficulty == "hard"]
    # Exclude every hard problem — should wrap around and still return a hard problem.
    p = problem_bank.select_for_level("hard", exclude_ids=all_hard_ids)
    assert p.difficulty == "hard"
