"""Host monitor service — async wrapper with TTL cache.

A single cached result is shared across all concurrent requests (multiple
browser tabs, repeated polls).  The cache expires after CACHE_TTL_S seconds
so data stays fresh enough for a monitoring page while eliminating duplicate
psutil collection runs.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from app.services.host_monitor import collect_snapshot, collect_cpu, collect_memory

# Cache TTL in seconds — matches the frontend poll interval (3 s) with a
# small margin so at most one collection runs per interval even with many tabs.
CACHE_TTL_S: float = 2.5

# ── Shared cache state ────────────────────────────────────────────────────────

_snapshot_cache: Optional[Dict[str, Any]] = None
_snapshot_ts: float = 0.0
_snapshot_lock = asyncio.Lock()


async def get_snapshot() -> Dict[str, Any]:
    """Full host snapshot with TTL cache.

    Concurrent callers that arrive while a collection is in progress will wait
    on the lock and then receive the freshly-collected result — only one
    psutil run happens per TTL window regardless of how many tabs are open.
    """
    global _snapshot_cache, _snapshot_ts

    now = time.monotonic()
    if _snapshot_cache is not None and (now - _snapshot_ts) < CACHE_TTL_S:
        return _snapshot_cache

    async with _snapshot_lock:
        # Re-check after acquiring lock — another waiter may have refreshed.
        now = time.monotonic()
        if _snapshot_cache is not None and (now - _snapshot_ts) < CACHE_TTL_S:
            return _snapshot_cache

        result = await asyncio.to_thread(collect_snapshot)
        _snapshot_cache = result
        _snapshot_ts = time.monotonic()
        return result


async def get_cpu() -> Dict[str, Any]:
    """CPU-only stats (not cached separately — delegates to snapshot cache)."""
    snap = await get_snapshot()
    return snap["cpu"]


async def get_memory() -> Dict[str, Any]:
    """Memory-only stats (delegates to snapshot cache)."""
    snap = await get_snapshot()
    return snap["memory"]
