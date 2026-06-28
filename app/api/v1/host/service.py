"""Host monitor service — thin async wrapper around the blocking psutil collector."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.services.host_monitor import collect_snapshot, collect_cpu, collect_memory


async def get_snapshot() -> Dict[str, Any]:
    """Full host snapshot (CPU + memory + disk + network + process). Runs in thread."""
    return await asyncio.to_thread(collect_snapshot)


async def get_cpu() -> Dict[str, Any]:
    return await asyncio.to_thread(collect_cpu)


async def get_memory() -> Dict[str, Any]:
    return await asyncio.to_thread(collect_memory)
