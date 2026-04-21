"""Pipeline executor — walks a pipeline DAG and runs each node.

Phase 5c ships a minimal-but-real executor that handles the handful of block
types Frontend exercises most often (loader, filter, aggregate, chart). Full
parity with ``fastapi_backend_service.app.services.pipeline_executor`` is
Phase 7 work; the module boundary is set up so the swap is a file drop-in.
"""
