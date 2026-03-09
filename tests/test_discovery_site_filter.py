from __future__ import annotations

import applypilot.pipeline as pipeline


def test_run_discover_site_filter_runs_only_matching_smartextract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_load_sites():
        return [
            {"name": "Lensa", "url": "https://lensa.com/jobs?k={query_encoded}", "type": "search"},
            {"name": "Dice", "url": "https://dice.com/jobs?q={query_encoded}", "type": "search"},
        ]

    def _fake_run_smart_extract(sites=None, workers=1):
        captured["sites"] = sites
        captured["workers"] = workers
        return {"ok": True}

    monkeypatch.setattr("applypilot.discovery.smartextract.load_sites", _fake_load_sites)
    monkeypatch.setattr("applypilot.discovery.smartextract.run_smart_extract", _fake_run_smart_extract)

    result = pipeline._run_discover(workers=3, site_filter=["lensa"])

    assert captured["workers"] == 3
    selected = captured["sites"]
    assert isinstance(selected, list)
    assert len(selected) == 1
    assert selected[0]["name"] == "Lensa"
    assert result["jobspy"] == "skipped (site-filter)"
    assert result["workday"] == "skipped (site-filter)"
    assert result["smartextract"] == "ok"
