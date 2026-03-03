from __future__ import annotations

import pytest

from applypilot.llm import UsageLimitError
from applypilot import pipeline


def test_run_score_propagates_usage_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_usage_limit() -> None:
        raise UsageLimitError("limit", raw_message="You've hit your limit")

    import applypilot.scoring.scorer as scorer

    monkeypatch.setattr(scorer, "run_scoring", _raise_usage_limit)

    with pytest.raises(UsageLimitError):
        pipeline._run_score()


def test_run_tailor_propagates_usage_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_usage_limit(*args, **kwargs) -> None:
        raise UsageLimitError("limit", raw_message="You've hit your limit")

    import applypilot.scoring.tailor as tailor

    monkeypatch.setattr(tailor, "run_tailoring", _raise_usage_limit)

    with pytest.raises(UsageLimitError):
        pipeline._run_tailor(min_score=7, validation_mode="normal")


def test_run_cover_propagates_usage_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_usage_limit(*args, **kwargs) -> None:
        raise UsageLimitError("limit", raw_message="You've hit your limit")

    import applypilot.scoring.cover_letter as cover

    monkeypatch.setattr(cover, "run_cover_letters", _raise_usage_limit)

    with pytest.raises(UsageLimitError):
        pipeline._run_cover(min_score=7, validation_mode="normal")
