"""Pytest fixtures for pipeline_builder tests.

Provides:
  - a catalog dict representing all 5 seeded Phase-1 blocks (no DB needed)
  - a BlockRegistry with those blocks registered (using BUILTIN_EXECUTORS)
"""

from __future__ import annotations

import pytest

from app.services.pipeline_builder.block_registry import BlockRegistry
from app.services.pipeline_builder.blocks import BUILTIN_EXECUTORS
from app.services.pipeline_builder.seed import _blocks


@pytest.fixture
def block_catalog() -> dict[tuple[str, str], dict]:
    """Catalog loaded straight from seed specs (no DB round-trip)."""
    cat: dict[tuple[str, str], dict] = {}
    for spec in _blocks():
        cat[(spec["name"], spec["version"])] = {
            "name": spec["name"],
            "version": spec["version"],
            "category": spec["category"],
            "status": spec["status"],
            "description": spec["description"],
            "input_schema": spec["input_schema"],
            "output_schema": spec["output_schema"],
            "param_schema": spec["param_schema"],
            "implementation": spec["implementation"],
            "is_custom": False,
        }
    return cat


@pytest.fixture
def block_registry(block_catalog) -> BlockRegistry:
    reg = BlockRegistry()
    reg._catalog = block_catalog  # type: ignore[attr-defined]
    reg._executors = {  # type: ignore[attr-defined]
        key: BUILTIN_EXECUTORS[key[0]]()
        for key in block_catalog.keys()
        if key[0] in BUILTIN_EXECUTORS
    }
    return reg
