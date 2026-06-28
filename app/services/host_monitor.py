"""
Host system monitor — wraps psutil for CPU, memory, disk, network, and process stats.

Used by the /api/v1/host/* endpoints for operator troubleshooting.
All collection is synchronous (psutil is blocking); callers run via asyncio.to_thread.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import psutil


def _safe(fn, default=None):
    """Call fn(), return default on any exception (e.g. AccessDenied, NoSuchProcess)."""
    try:
        return fn()
    except Exception:
        return default


# ── CPU ──────────────────────────────────────────────────────────────────────

def collect_cpu() -> Dict[str, Any]:
    freq = _safe(psutil.cpu_freq)
    return {
        "percent_total": psutil.cpu_percent(interval=0.2),
        "percent_per_core": psutil.cpu_percent(interval=0.2, percpu=True),
        "count_logical": psutil.cpu_count(logical=True),
        "count_physical": psutil.cpu_count(logical=False),
        "freq_mhz": {
            "current": round(freq.current, 1) if freq else None,
            "min":     round(freq.min, 1)     if freq else None,
            "max":     round(freq.max, 1)     if freq else None,
        },
        "load_avg_1_5_15": [round(x, 2) for x in _safe(os.getloadavg, (0.0, 0.0, 0.0))],
    }


# ── Memory ────────────────────────────────────────────────────────────────────

def _mb(b: Optional[int]) -> Optional[float]:
    return round(b / 1024 / 1024, 1) if b is not None else None


def collect_memory() -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    sw = _safe(psutil.swap_memory)
    return {
        "ram": {
            "total_mb":     _mb(vm.total),
            "available_mb": _mb(vm.available),
            "used_mb":      _mb(vm.used),
            "percent":      vm.percent,
        },
        "swap": {
            "total_mb": _mb(sw.total) if sw else None,
            "used_mb":  _mb(sw.used)  if sw else None,
            "percent":  sw.percent    if sw else None,
        } if sw else None,
    }


# ── Disk ──────────────────────────────────────────────────────────────────────

def collect_disk() -> Dict[str, Any]:
    partitions = []
    for part in _safe(psutil.disk_partitions, []):
        usage = _safe(lambda p=part: psutil.disk_usage(p.mountpoint))
        partitions.append({
            "device":      part.device,
            "mountpoint":  part.mountpoint,
            "fstype":      part.fstype,
            "total_gb":    round(usage.total / 1e9, 2) if usage else None,
            "used_gb":     round(usage.used  / 1e9, 2) if usage else None,
            "free_gb":     round(usage.free  / 1e9, 2) if usage else None,
            "percent":     usage.percent if usage else None,
        })

    io = _safe(psutil.disk_io_counters)
    return {
        "partitions": partitions,
        "io": {
            "read_mb":  round(io.read_bytes  / 1e6, 1) if io else None,
            "write_mb": round(io.write_bytes / 1e6, 1) if io else None,
            "read_count":  io.read_count  if io else None,
            "write_count": io.write_count if io else None,
        },
    }


# ── Network ───────────────────────────────────────────────────────────────────

def collect_network() -> Dict[str, Any]:
    ifaces = []
    addrs  = _safe(psutil.net_if_addrs, {})
    stats  = _safe(psutil.net_if_stats, {})
    io_all = _safe(lambda: psutil.net_io_counters(pernic=True), {})

    for name, addr_list in (addrs or {}).items():
        ipv4 = next((a.address for a in addr_list if a.family.name == "AF_INET"), None)
        ipv6 = next((a.address for a in addr_list if a.family.name == "AF_INET6"), None)
        st   = stats.get(name) if stats else None
        io   = io_all.get(name) if io_all else None
        ifaces.append({
            "name":        name,
            "ipv4":        ipv4,
            "ipv6":        ipv6,
            "is_up":       st.isup if st else None,
            "speed_mbps":  st.speed if st else None,
            "sent_mb":     round(io.bytes_sent / 1e6, 1) if io else None,
            "recv_mb":     round(io.bytes_recv / 1e6, 1) if io else None,
            "packets_sent": io.packets_sent if io else None,
            "packets_recv": io.packets_recv if io else None,
            "errin":       io.errin  if io else None,
            "errout":      io.errout if io else None,
        })

    return {"interfaces": ifaces}


# ── Process (current backend process) ─────────────────────────────────────────

def collect_process() -> Dict[str, Any]:
    proc = psutil.Process(os.getpid())
    mem  = _safe(proc.memory_info)
    cpu  = _safe(lambda: proc.cpu_percent(interval=0.1))
    fds  = _safe(proc.num_fds)
    thrs = _safe(proc.num_threads)
    return {
        "pid":           proc.pid,
        "cpu_percent":   cpu,
        "rss_mb":        _mb(mem.rss) if mem else None,
        "vms_mb":        _mb(mem.vms) if mem else None,
        "num_threads":   thrs,
        "num_fds":       fds,
        "create_time":   _safe(proc.create_time),
        "uptime_s":      round(time.time() - _safe(proc.create_time, time.time()), 1),
    }


# ── Host info ─────────────────────────────────────────────────────────────────

def collect_host_info() -> Dict[str, Any]:
    boot = psutil.boot_time()
    return {
        "hostname":    _safe(lambda: __import__("socket").gethostname()),
        "platform":    _safe(lambda: __import__("platform").platform()),
        "python":      _safe(lambda: __import__("platform").python_version()),
        "boot_time":   boot,
        "uptime_s":    round(time.time() - boot, 1),
    }


# ── Top-level snapshot ────────────────────────────────────────────────────────

def collect_snapshot() -> Dict[str, Any]:
    """Full host snapshot — intended to run in a thread (all psutil calls are blocking)."""
    return {
        "host":    collect_host_info(),
        "cpu":     collect_cpu(),
        "memory":  collect_memory(),
        "disk":    collect_disk(),
        "network": collect_network(),
        "process": collect_process(),
        "collected_at": time.time(),
    }
