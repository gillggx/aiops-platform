"""MongoDB tail-based event poller.

Phase 5c: lifecycle wiring only. The actual Mongo cursor loop is expected to
be ported from ``fastapi_backend_service.app.services.event_poller_service``
in a later phase — the adapter here demonstrates the publish path.

To enable at runtime, set ``EVENT_POLLER_ENABLED=1``. When disabled the task
starts, logs a one-liner, and exits cleanly — so production can roll this out
gradually without gating behind a redeploy.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from ..auth import CallerContext
from ..clients.java_client import JavaAPIClient, JavaAPIError

log = logging.getLogger("python_ai_sidecar.background.event_poller")


class EventPoller:
    """Minimal async task skeleton + clean shutdown handle."""

    def __init__(self, poll_interval_sec: float = 5.0):
        self.poll_interval_sec = poll_interval_sec
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="event-poller")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
            log.warning("event poller forced to cancel")
        self._task = None

    async def _run(self) -> None:
        enabled = os.getenv("EVENT_POLLER_ENABLED", "0") == "1"
        if not enabled:
            log.info("event poller is disabled (EVENT_POLLER_ENABLED != 1)")
            return
        log.info("event poller started — will publish via /internal/generated-events")
        # Use a service-account CallerContext so Java audit-logs tag the poller.
        svc_caller = CallerContext(user_id=None, roles=("SERVICE_POLLER",))
        java = JavaAPIClient.for_caller(svc_caller)
        while not self._stop.is_set():
            try:
                await self._poll_once(java)
            except JavaAPIError as ex:
                log.warning("Java push failed: %s", ex)
            except Exception:  # noqa: BLE001
                log.exception("unexpected poller iteration failure")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_sec)
            except asyncio.TimeoutError:
                pass

    async def _poll_once(self, java: JavaAPIClient) -> None:
        """Replace the pass with a real Mongo tail cursor when wiring up.

        Sketch of the final shape:

            async for doc in mongo_collection.watch(...):
                await java.create_generated_event({
                    "eventTypeId": resolve_event_type_id(doc['kind']),
                    "sourceSkillId": doc.get('source_skill_id', -1),
                    "mappedParameters": json.dumps(doc.get('payload', {})),
                    "skillConclusion": doc.get('conclusion'),
                })
        """
        pass


_instance: Optional[EventPoller] = None


def get_instance() -> EventPoller:
    global _instance
    if _instance is None:
        _instance = EventPoller()
    return _instance
