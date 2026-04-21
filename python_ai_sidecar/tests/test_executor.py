"""DAG walker unit tests — no FastAPI, no Java."""

from __future__ import annotations

from python_ai_sidecar.executor.dag import DAGError, execute_dag


def test_empty_pipeline_validation_error():
    assert execute_dag(None)["status"] == "validation_error"
    assert execute_dag({})["status"] == "validation_error"
    assert execute_dag({"nodes": []})["status"] == "validation_error"


def test_single_loader_node():
    pipeline = {
        "nodes": [{"id": "n1", "block": "load_inline_rows",
                   "params": {"rows": [{"x": 1}, {"x": 2}]}}],
        "edges": [],
    }
    res = execute_dag(pipeline)
    assert res["status"] == "success"
    assert res["node_results"]["n1"]["rows"] == 2
    assert res["terminal_nodes"] == ["n1"]
    assert res["preview"][0]["x"] == 1


def test_load_filter_count_chain():
    pipeline = {
        "nodes": [
            {"id": "src", "block": "load_inline_rows",
             "params": {"rows": [{"v": 1}, {"v": 2}, {"v": 3}, {"v": 2}]}},
            {"id": "f", "block": "filter_rows",
             "params": {"field": "v", "op": "gte", "value": 2}},
            {"id": "c", "block": "count_rows", "params": {}},
        ],
        "edges": [{"from": "src", "to": "f"}, {"from": "f", "to": "c"}],
    }
    res = execute_dag(pipeline)
    assert res["status"] == "success"
    assert res["node_results"]["f"]["rows"] == 3
    assert res["node_results"]["c"]["rows"] == 1
    assert res["preview"] == [{"count": 3}]


def test_group_count():
    pipeline = {
        "nodes": [
            {"id": "src", "block": "load_inline_rows",
             "params": {"rows": [{"cat": "a"}, {"cat": "b"}, {"cat": "a"}, {"cat": "a"}]}},
            {"id": "g", "block": "group_count", "params": {"field": "cat"}},
        ],
        "edges": [{"from": "src", "to": "g"}],
    }
    res = execute_dag(pipeline)
    assert res["status"] == "success"
    grouped = {row["cat"]: row["count"] for row in res["preview"]}
    assert grouped == {"a": 3, "b": 1}


def test_unknown_block_surfaces_as_node_error():
    pipeline = {
        "nodes": [{"id": "n1", "block": "nonexistent_block", "params": {}}],
        "edges": [],
    }
    res = execute_dag(pipeline)
    assert res["status"] == "error"
    assert res["node_results"]["n1"]["status"] == "error"
    assert "unknown block" in res["node_results"]["n1"]["error"]


def test_cycle_detected():
    pipeline = {
        "nodes": [
            {"id": "a", "block": "load_inline_rows", "params": {"rows": []}},
            {"id": "b", "block": "filter_rows", "params": {"field": "x", "op": "eq", "value": 1}},
        ],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
    }
    import pytest
    with pytest.raises(DAGError):
        execute_dag(pipeline)
