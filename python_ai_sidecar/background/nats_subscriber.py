"""NATS event subscriber.

Same pattern as ``event_poller`` — lifecycle-managed background task gated by
``NATS_SUBSCRIBER_ENABLED``. Publishing path already threaded through
``JavaAPIClient.create_generated_event``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from ..auth import CallerContext
from ..clients.java_client import JavaAPIClient, JavaAPIError

log = logging.getLogger("python_ai_sidecar.background.nats")


class NatsSubscriber:

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="nats-subscriber")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
            log.warning("nats subscriber forced to cancel")
        self._task = None

    async def _run(self) -> None:
        enabled = os.getenv("NATS_SUBSCRIBER_ENABLED", "0") == "1"
        if not enabled:
            log.info("NATS subscriber disabled (NATS_SUBSCRIBER_ENABLED != 1)")
            return
        log.info("NATS subscriber started")
        svc_caller = CallerContext(user_id=None, roles=("SERVICE_NATS",))
        java = JavaAPIClient.for_caller(svc_caller)
        # Real wiring (Phase 7): use ``nats.aio.client`` — sketch:
        #
        #     nc = await nats.connect(os.getenv("NATS_URL"))
        #     sub = await nc.subscribe(">", cb=lambda msg: _dispatch(msg, java))
        #     await self._stop.wait()
        #     await sub.unsubscribe()
        #
        while not self._stop.is_set():
            await asyncio.sleep(1.0)

    async def _dispatch(self, msg, java: JavaAPIClient) -> None:
        try:
            await java.create_generated_event({
                "eventTypeId": -1,
                "sourceSkillId": -1,
                "mappedParameters": msg.data.decode(errors="replace") if msg else "{}",
            })
        except JavaAPIError as ex:
            log.warning("NATS → Java publish failed: %s", ex)


_instance: Optional[NatsSubscriber] = None


def get_instance() -> NatsSubscriber:
    global _instance
    if _instance is None:
        _instance = NatsSubscriber()
    return _instance
