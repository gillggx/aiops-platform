"""Phase 4-C / Phase 5 — PIPELINE_ONLY_MODE feature flag tests.

Phase 5 rename: `plan_pipeline` → `build_pipeline_live` (pb_pipeline engine).

Verifies:
  - `execute_skill` hidden when flag on (same as 4-C)
  - `build_pipeline_live` is always visible
  - `execute_mcp` / `query_data` / `execute_analysis` always hidden
"""

from __future__ import annotations

import pytest

from app.services.agent_orchestrator_v2.nodes.llm_call import _visible_tools


def test_legacy_mode_includes_execute_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default flag off → execute_skill IS visible + build_pipeline_live too."""
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "PIPELINE_ONLY_MODE", False)
    names = {t["name"] for t in _visible_tools()}
    assert "build_pipeline_live" in names  # Phase 5 successor of plan_pipeline
    assert "execute_skill" in names  # legacy path


def test_pipeline_only_mode_hides_execute_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flag on → execute_skill hidden; build_pipeline_live retained."""
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "PIPELINE_ONLY_MODE", True)
    names = {t["name"] for t in _visible_tools()}
    assert "build_pipeline_live" in names
    assert "execute_skill" not in names


def test_always_hidden_tools_stay_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """execute_mcp / query_data / execute_analysis must be hidden regardless of flag."""
    from app.config import get_settings
    settings = get_settings()
    for flag in (False, True):
        monkeypatch.setattr(settings, "PIPELINE_ONLY_MODE", flag)
        names = {t["name"] for t in _visible_tools()}
        for always_hidden in ("execute_mcp", "query_data", "execute_analysis"):
            assert always_hidden not in names, f"{always_hidden} leaked with flag={flag}"


def test_directive_text_is_appendable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When flag is on, load_context injects the Phase 5 Pipeline-Only Mode block."""
    import inspect
    from app.services.agent_orchestrator_v2.nodes import load_context
    src = inspect.getsource(load_context)
    assert "Pipeline-Only Mode" in src
    assert "build_pipeline_live" in src
    assert "search_published_skills" in src
