"""Application lifespan — startup and shutdown logic."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging import get_logger
from app.db.migrate import ensure_schema
from app.db.session import init_engine
from app.services.nodes.instance import node_manager
from app.services.shared.recorder import get_recorder
from app.services.status_aggregator import (
    notify_status_change,
    start_status_aggregator,
    stop_status_aggregator,
)
from app.services.websocket.manager import manager

logger = get_logger("app.lifespan")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    engine = init_engine()
    ensure_schema(engine)

    from app.services.app_settings import load_overrides
    load_overrides()

    recorder = get_recorder()
    manager.recorder = recorder

    # Replay runs left queued/running by a crash can never finish.
    try:
        from app.services.replay import get_replay_service
        get_replay_service().recover_interrupted()
    except Exception as exc:
        logger.warning("Replay run recovery failed: %s", exc)

    node_manager.load_config()
    await node_manager.start(asyncio.get_running_loop())

    # Sweep orphaned result directories with no DB record
    try:
        from app.api.v1.results.router import _get_service as _get_results_service
        await _get_results_service().sweep_orphans()
    except Exception as exc:
        logger.warning("Startup orphan sweep failed: %s", exc)

    manager.register_topic("shapes")

    start_status_aggregator()

    from app.services.retention import start_retention
    start_retention()
    for node_id in node_manager.nodes:
        notify_status_change(node_id)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    from app.services.retention import stop_retention
    stop_retention()
    stop_status_aggregator()
    await recorder.stop_all_recordings()
    await node_manager.stop()
