"""Validator rule tests (C1–C7)."""

from __future__ import annotations

from app.schemas.pipeline import PipelineJSON
from app.services.pipeline_builder.validator import PipelineValidator


_GOOD_PIPELINE: dict = {
    "version": "1.0",
    "name": "Test Pipeline",
    "nodes": [
        {
            "id": "n1",
            "block_id": "block_process_history",
            "block_version": "1.0.0",
            "position": {"x": 0, "y": 0},
            "params": {"tool_id": "EQP-01", "time_range": "24h"},
        },
        {
            "id": "n2",
            "block_id": "block_filter",
            "block_version": "1.0.0",
            "position": {"x": 200, "y": 0},
            "params": {"column": "step", "operator": "==", "value": "STEP_002"},
        },
        {
            "id": "n3",
            "block_id": "block_consecutive_rule",
            "block_version": "1.0.0",
            "position": {"x": 400, "y": 0},
            "params": {"flag_column": "spc_xbar_chart_is_ooc", "count": 3, "sort_by": "eventTime"},
        },
        {
            "id": "n4",
            "block_id": "block_alert",
            "block_version": "1.0.0",
            "position": {"x": 600, "y": 0},
            "params": {"severity": "HIGH"},
        },
    ],
    "edges": [
        {"id": "e1", "from": {"node": "n1", "port": "data"},     "to": {"node": "n2", "port": "data"}},
        {"id": "e2", "from": {"node": "n2", "port": "data"},     "to": {"node": "n3", "port": "data"}},
        {"id": "e3", "from": {"node": "n3", "port": "triggered"},"to": {"node": "n4", "port": "triggered"}},
        {"id": "e4", "from": {"node": "n3", "port": "evidence"}, "to": {"node": "n4", "port": "evidence"}},
    ],
}


def test_valid_pipeline(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    assert v.validate(_GOOD_PIPELINE) == []


def test_c1_schema_invalid_json(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    bad = {"nodes": [], "edges": []}  # missing 'name'
    errors = v.validate(bad)
    assert any(e["rule"] == "C1_SCHEMA" for e in errors)


def test_c2_block_not_exists(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    p = dict(_GOOD_PIPELINE)
    p = {**p, "nodes": [dict(n) for n in p["nodes"]]}
    p["nodes"][0] = {**p["nodes"][0], "block_id": "block_does_not_exist"}
    errors = v.validate(p)
    assert any(e["rule"] == "C2_BLOCK_EXISTS" for e in errors)


def test_c3_status_enforcement(block_catalog) -> None:
    # Flip one block to draft and require production
    cat = {k: dict(v) for k, v in block_catalog.items()}
    cat[("block_filter", "1.0.0")]["status"] = "draft"
    v = PipelineValidator(cat, enforce_pipeline_status="production")
    errors = v.validate(_GOOD_PIPELINE)
    assert any(e["rule"] == "C3_BLOCK_STATUS" for e in errors)


def test_c4_port_type_mismatch(block_catalog) -> None:
    # block_consecutive_rule has no 'data' output — force an invalid edge name
    v = PipelineValidator(block_catalog)
    p = {**_GOOD_PIPELINE, "edges": list(_GOOD_PIPELINE["edges"])}
    p["edges"] = [dict(e) for e in p["edges"]]
    p["edges"][-1] = {
        "id": "e4",
        "from": {"node": "n3", "port": "data"},  # invalid: n3 has no 'data' output
        "to": {"node": "n4", "port": "evidence"},
    }
    errors = v.validate(p)
    assert any(e["rule"] == "C4_PORT_COMPAT" for e in errors)


def test_c5_cycle(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    p = dict(_GOOD_PIPELINE)
    # alert.alert (dataframe) → n1 would be cycle if n1 accepted dataframe inputs;
    # the cycle check should fire regardless of type validity.
    p["edges"] = list(_GOOD_PIPELINE["edges"]) + [
        {"id": "e_cycle", "from": {"node": "n4", "port": "alert"}, "to": {"node": "n1", "port": "data"}},
    ]
    errors = v.validate(p)
    assert any(e["rule"] == "C5_CYCLE" for e in errors)


def test_c6_missing_required_param(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    p = dict(_GOOD_PIPELINE)
    p["nodes"] = [dict(n) for n in p["nodes"]]
    # block_filter requires "column" + "operator"; blank them out
    p["nodes"][1] = {**p["nodes"][1], "params": {}}
    errors = v.validate(p)
    assert any(
        e["rule"] == "C6_PARAM_SCHEMA" and e.get("node_id") == "n2"
        for e in errors
    )


def test_c6_enum_violation(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    p = dict(_GOOD_PIPELINE)
    p["nodes"] = [dict(n) for n in p["nodes"]]
    # block_filter operator has enum
    p["nodes"][1] = {
        **p["nodes"][1],
        "params": {"column": "step", "operator": "LIKE", "value": "x"},
    }
    errors = v.validate(p)
    assert any(e["rule"] == "C6_PARAM_SCHEMA" for e in errors)


def test_c7_no_source(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    p = dict(_GOOD_PIPELINE)
    p["nodes"] = [n for n in _GOOD_PIPELINE["nodes"] if n["id"] != "n1"]
    p["edges"] = [e for e in _GOOD_PIPELINE["edges"] if e["id"] != "e1"]
    errors = v.validate(p)
    assert any(e["rule"] == "C7_ENDPOINTS" and "source" in e["message"].lower() for e in errors)


def test_c7_no_output(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    p = dict(_GOOD_PIPELINE)
    # drop the alert node (the only 'output'-category node)
    p["nodes"] = [n for n in _GOOD_PIPELINE["nodes"] if n["id"] != "n4"]
    p["edges"] = [e for e in _GOOD_PIPELINE["edges"] if e["id"] not in ("e3", "e4")]
    errors = v.validate(p)
    assert any(e["rule"] == "C7_ENDPOINTS" and "output" in e["message"].lower() for e in errors)


def test_multiple_alerts_allowed(block_catalog) -> None:
    """Phase β: multiple block_alert nodes are allowed (e.g. one per SPC chart type)."""
    v = PipelineValidator(block_catalog)
    p = dict(_GOOD_PIPELINE)
    p["nodes"] = list(_GOOD_PIPELINE["nodes"]) + [
        {
            "id": "n5",
            "block_id": "block_alert",
            "block_version": "1.0.0",
            "position": {"x": 800, "y": 0},
            "params": {"severity": "LOW"},
        },
    ]
    # The extra alert is orphan (no edge), but validator should not surface
    # C8-style errors about duplicate alerts — only care about port compat.
    errors = v.validate(p)
    assert not any(e["rule"] == "C8_SINGLE_ALERT" for e in errors)


def test_c9_duplicate_chart_sequence(block_catalog) -> None:
    """Two chart nodes sharing the same sequence should trigger a warning."""
    v = PipelineValidator(block_catalog)
    # Swap the alert node for two chart nodes with duplicate sequence=1.
    p = dict(_GOOD_PIPELINE)
    p["nodes"] = [n for n in _GOOD_PIPELINE["nodes"] if n["id"] != "n4"] + [
        {
            "id": "c1", "block_id": "block_chart", "block_version": "1.0.0",
            "position": {"x": 800, "y": 0},
            "params": {"chart_type": "line", "x": "eventTime", "y": "spc_xbar_chart_value", "sequence": 1},
        },
        {
            "id": "c2", "block_id": "block_chart", "block_version": "1.0.0",
            "position": {"x": 1000, "y": 0},
            "params": {"chart_type": "bar", "x": "step", "y": "spc_xbar_chart_value", "sequence": 1},
        },
    ]
    p["edges"] = [e for e in _GOOD_PIPELINE["edges"] if e["id"] not in ("e3", "e4")] + [
        {"id": "ec1", "from": {"node": "n2", "port": "data"}, "to": {"node": "c1", "port": "data"}},
        {"id": "ec2", "from": {"node": "n2", "port": "data"}, "to": {"node": "c2", "port": "data"}},
    ]
    errors = v.validate(p)
    assert any(e["rule"] == "C9_CHART_SEQUENCE" for e in errors)


def test_valid_parses_from_pydantic(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    pj = PipelineJSON.model_validate(_GOOD_PIPELINE)
    assert v.validate(pj) == []
