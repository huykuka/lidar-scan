"""LiDAR device discovery: subnet resolution, TCP probe scan, parser, WS broadcast.

Ported from find.py. State is in-memory only (singleton job + cache).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import ipaddress
import re
import socket
import threading
import json
import time
import urllib.request
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.logging import get_logger
from app.services.websocket.manager import manager
from .dto import Device, ScanJob

logger = get_logger("discovery")

TOPIC = "device_discovery"
SEARCH_TIMEOUT = 0.3
MAX_WORKERS = 64
MAX_HOSTS = 4096
DEFAULT_PORT = 2111
BROADCAST_INTERVAL = 0.2
_PROBE_PAYLOAD = b"\x02sRN DeviceIdent\x03"
_ORDNUM_PAYLOAD = b"\x02sRN OrdNum\x03"
REST_TIMEOUT = 0.5
_REST_ENDPOINTS = ("/api/v1/system/info", "/rest/system/info")

_lock = threading.Lock()
_job: ScanJob | None = None
_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class DiscoveryError(Exception):
    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.detail = {"code": code, "message": message, **extra}


def _http(err: DiscoveryError) -> HTTPException:
    return HTTPException(status_code=422, detail=err.detail)


# ---------------------------------------------------------------------------
# Parser / mapping
# ---------------------------------------------------------------------------

# normalized (lowercase, no space/-/_) device-name prefix -> profile model_id
_TYPE_PREFIXES: dict[str, str] = {
    "multiscan136": "multiscan136",
    "multiscan165": "multiscan165",
    "picoscan120": "picoscan_120",
    "picoscan150": "picoscan_150",
    "tim24": "tim_240",
    "tim55": "tim_5xx",
    "tim56": "tim_5xx",
    "tim57": "tim_5xx",
    "tim78": "tim_7xx",
    "tim781s": "tim_7xxs",
    "lms10": "lms_1xx",
    "lms11": "lms_1xx",
    "lms14": "lms_1xx",
    "lms15": "lms_1xx",
    "lms4": "lms_4xxx",
    "lms5": "lms_5xx",
    "mrs1": "mrs_1xxx",
    "mrs6": "mrs_6xxx",
    "lrs4": "lrs_4xxx",
    "lrs3600": "lrs_36x0",
    "lrs3601": "lrs_36x1",
    "ldmrs": "ldmrs",
    "oem15": "oem_15xx",
    "nav2": "nav_2xx",
    "nav31": "nav_31x",
    "nav350": "nav_350",
    "rms": "rms_xxxx",
}
# Family-only fallbacks (normalized) -> profile model_id.
_FAMILY_FALLBACKS: dict[str, str] = {
    "picoscan": "picoscan_150",
    "multiscan": "multiscan136",
    "tim7": "tim_7xx",
    "tim5": "tim_5xx",
    "lms1": "lms_1xx",
}
_TYPE_KEYS = sorted(_TYPE_PREFIXES, key=len, reverse=True)


# SICK part number -> (variant label, profile model_id). multiScan166 has no
# dedicated profile; closest existing is multiscan165.
SICK_PART_TABLE: dict[str, tuple[str, str]] = {
    "1156324": ("multiScan165 (MULS1AA-114322)", "multiscan165"),
    "1140133": ("multiScan136 (MULS1AA-112211)", "multiscan136"),
    "1154495": ("multiScan136 3DOD-A", "multiscan136"),
    "1154598": ("multiScan166 (MULS1AA-115511)", "multiscan165"),
    "1151596": ("multiScan165S (MULS1AAS-114322)", "multiscan165"),
    "1143873": ("multiScan165S (MULS1AAS-114322)", "multiscan165"),
    "1155238": ("multiScan166 (MULS1AA-115511)", "multiscan165"),
    "1131164": ("multiScan136 (MULS1AA-112211)", "multiscan136"),
    "1137723": ("multiScan165 (MULS1AA-114322)", "multiscan165"),
    "1154496": ("multiScan165 3DOD-A", "multiscan165"),
    "1140134": ("multiScan136 (MULS1AA-112211)", "multiscan136"),
    "1140110": ("multiScan136 (MULS1AA-112211)", "multiscan136"),
    "1141496": ("multiScan165 (MULS1AA-114322)", "multiscan165"),
    "1147803": ("multiScan165 (MULS1AA-114322)", "multiscan165"),
    "1134608": ("PICS150-01000 Core-1", "picoscan_150"),
    "1134610": ("PICS150-01000 Pro-1", "picoscan_150"),
    "1142270": ("PICS150-01000 Core-2 6 I/O", "picoscan_150"),
    "1142273": ("PICS150-01000 Pro-2 6 I/O", "picoscan_150"),
    "1134609": ("PICS150-01000 Prime-1", "picoscan_150"),
    "1141751": ("PICS120-AX1100 (picoScan120)", "picoscan_120"),
    "1141397": ("PICS150-01000 LOC Pro", "picoscan_150"),
    "1134607": ("PICS150-01000 Core w/o add-ons", "picoscan_150"),
    "1141396": ("PICS150-01000 LOC Prime", "picoscan_150"),
    "1142269": ("PICS150-01000 Core 6 I/O w/o add-ons", "picoscan_150"),
    "1142272": ("PICS150-01000 Prime-2 6 I/O", "picoscan_150"),
    "1141395": ("PICS150-01000 LOC Core", "picoscan_150"),
}


def resolve_variant_name(device_name: str | None, part_number: str | None) -> str | None:
    """Table label for part number, else family-based fallback, else None."""
    if part_number and part_number in SICK_PART_TABLE:
        return SICK_PART_TABLE[part_number][0]
    if part_number:
        low = (device_name or "").lower()
        if "picoscan" in low:
            return f"picoScan Series (Part No: {part_number})"
        if "multiscan" in low:
            return f"multiScan Series (Part No: {part_number})"
        return f"Part No: {part_number}"
    return None


def resolve_lidar_type(device_name: str | None, part_number: str | None) -> str | None:
    """Priority: exact part number -> device name variant/family -> None."""
    if part_number and part_number in SICK_PART_TABLE:
        return SICK_PART_TABLE[part_number][1]
    return map_lidar_type(device_name)


def parse_order_number(resp: bytes | None) -> str | None:
    if not resp or b"OrdNum" not in resp:
        return None
    tokens = _decode_raw(resp).split()
    if len(tokens) < 3:
        return None
    return tokens[-1] or None


def query_rest_order_number(ip: str, timeout: float = REST_TIMEOUT) -> str | None:
    for ep in _REST_ENDPOINTS:
        try:
            req = urllib.request.Request(
                f"http://{ip}{ep}",
                headers={"User-Agent": "SICK-Scanner", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(65536).decode("utf-8", errors="ignore")
            if not body.strip().startswith("{"):
                continue
            data = json.loads(body)
            order = data.get("orderNumber") or data.get("partNumber") or data.get("deviceId")
            if order:
                return str(order).strip() or None
        except Exception:  # noqa: BLE001
            continue
    return None


def map_lidar_type(device_name: str | None) -> str | None:
    if not device_name:
        return None
    norm = re.sub(r"[\s\-_]+", "", device_name.lower())
    for key in _TYPE_KEYS:
        if norm.startswith(key):
            return _TYPE_PREFIXES[key]
    # Device may prepend a vendor/family prefix (e.g. "SICK picoScan150"); match anywhere.
    for key in _TYPE_KEYS:
        if len(key) >= 6 and key in norm:
            return _TYPE_PREFIXES[key]
    # Bare family names (real devices report e.g. "picoScan", "multiScan" with no variant).
    # Exact variants above always win; these are best-effort defaults.
    for key in _FAMILY_FALLBACKS:
        if norm.startswith(key):
            return _FAMILY_FALLBACKS[key]
    return None


def _decode_raw(resp: bytes) -> str:
    text = resp.decode("ascii", errors="replace")
    return text.replace("\x02", "").replace("\x03", "").strip()


def _read_field(rest: str) -> tuple[str, str] | None:
    """Read '<hexlen> <value>' from start of rest. Returns (value, remainder)."""
    m = re.match(r"\s*([0-9A-Fa-f]+)\s", rest)
    if not m:
        return None
    n = int(m.group(1), 16)
    start = m.end()
    value = rest[start:start + n]
    if len(value) != n:
        return None
    return value, rest[start + n:]


def parse_device_ident(ip: str, resp: bytes, port: int = DEFAULT_PORT,
                       part_number: str | None = None) -> Device:
    raw = _decode_raw(resp)
    name = version = None
    m = re.match(r"^sRA\s+DeviceIdent\s+(.*)$", raw, re.DOTALL)
    if m:
        first = _read_field(m.group(1))
        if first:
            second = _read_field(first[1])
            if second:
                name, version = first[0], second[0]
    return Device(
        ip=ip, port=port, device_name=name, firmware_version=version,
        serial=None, raw=raw, lidar_type=resolve_lidar_type(name, part_number),
        part_number=part_number, variant_name=resolve_variant_name(name, part_number),
    )


# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------

def _excluded_ip(ip: ipaddress.IPv4Address) -> bool:
    return ip.is_loopback or ip.is_link_local


def get_local_ips() -> list[str]:
    """Local IPv4 addresses (find.py methods 1 + 2), excluding loopback/link-local."""
    ips: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    out: list[str] = []
    for ip in ips:
        try:
            addr = ipaddress.IPv4Address(ip)
        except ValueError:
            continue
        if not _excluded_ip(addr) and ip not in out:
            out.append(ip)
    return out


def resolve_targets(cidrs: list[str] | None) -> tuple[list[str], list[str]]:
    """Return (subnet strings, host list). Raises DiscoveryError."""
    local = get_local_ips()
    local_set = set(local)

    nets: list[ipaddress.IPv4Network] = []
    if cidrs:
        for c in cidrs:
            try:
                net = ipaddress.ip_network(str(c).strip(), strict=False)
            except ValueError:
                raise DiscoveryError("invalid_cidr", f"Invalid CIDR: {c}", cidr=c)
            if not isinstance(net, ipaddress.IPv4Network):
                raise DiscoveryError("invalid_cidr", f"Only IPv4 supported: {c}", cidr=c)
            nets.append(net)
    else:
        for ip in local:
            nets.append(ipaddress.ip_network(f"{ip}/24", strict=False))

    nets = sorted(set(ipaddress.collapse_addresses(nets)))
    if not nets:
        raise DiscoveryError("no_subnet", "No scannable subnet found")

    estimate = sum(max(n.num_addresses - 2, 1) if n.prefixlen < 31 else n.num_addresses for n in nets)
    if estimate > MAX_HOSTS:
        raise DiscoveryError("too_many_hosts", f"Too many hosts: {estimate} (max {MAX_HOSTS})",
                             total=estimate, max=MAX_HOSTS)

    seen: set[str] = set()
    hosts: list[str] = []
    for n in nets:
        for h in n.hosts():
            s = str(h)
            if s in seen or s in local_set:
                continue
            seen.add(s)
            hosts.append(s)
    if not hosts:
        raise DiscoveryError("no_subnet", "No hosts to scan")
    return [str(n) for n in nets], hosts


# ---------------------------------------------------------------------------
# Probe / scan
# ---------------------------------------------------------------------------

def probe_sick_device(ip: str, port: int = DEFAULT_PORT, timeout: float = SEARCH_TIMEOUT
                      ) -> tuple[bytes, str | None] | None:
    """Returns (DeviceIdent reply, order number|None) or None if not a CoLa device."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.sendall(_PROBE_PAYLOAD)
        resp = s.recv(256)
        if not (resp and b"DeviceIdent" in resp):
            return None
        order = None
        try:
            s.sendall(_ORDNUM_PAYLOAD)
            order = parse_order_number(s.recv(256))
        except OSError:
            pass
        if order is None:
            order = query_rest_order_number(ip)
        return resp, order
    except OSError:
        pass
    finally:
        s.close()
    return None


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ip_key(ip: str) -> tuple:
    try:
        return (0, int(ipaddress.IPv4Address(ip)))
    except ValueError:
        return (1, 0)


def _snapshot() -> ScanJob | None:
    """Deep copy of current job (kept until next scan or restart)."""
    with _lock:
        if _job is None:
            return None
        return _job.model_copy(deep=True)


def get_last_job() -> ScanJob | None:
    return _snapshot()


async def _broadcast() -> None:
    snap = _snapshot()
    if snap is None:
        return
    try:
        await manager.broadcast(TOPIC, snap.model_dump(mode="json"))
    except Exception:
        logger.exception("discovery broadcast failed")


def _scan_blocking(job_id: str, hosts: list[str], loop: asyncio.AbstractEventLoop) -> None:
    last_emit = 0.0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(probe_sick_device, h): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            ip = futures[fut]
            try:
                res = fut.result()
            except Exception:
                res = None
            with _lock:
                if _job is None or _job.id != job_id:
                    continue
                _job.scanned += 1
                if res:
                    _job.devices.append(parse_device_ident(ip, res[0], part_number=res[1]))
                    _job.devices.sort(key=lambda d: _ip_key(d.ip))
            now = time.monotonic()
            if now - last_emit >= BROADCAST_INTERVAL:
                last_emit = now
                try:
                    asyncio.run_coroutine_threadsafe(_broadcast(), loop)
                except RuntimeError:
                    pass


async def _run(job_id: str, hosts: list[str]) -> None:
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _scan_blocking, job_id, hosts, loop)
        status, error = "completed", None
    except Exception as exc:  # noqa: BLE001
        logger.exception("discovery scan failed")
        status, error = "failed", str(exc) or exc.__class__.__name__
    with _lock:
        if _job is not None and _job.id == job_id:
            _job.status = status
            _job.error = error
            _job.finished_at = _utcnow()
    await _broadcast()


async def start_scan(cidrs: list[str] | None) -> tuple[ScanJob, bool]:
    """Returns (job, created). created False -> already running."""
    global _job, _task
    running = _snapshot()
    if running and running.status == "running":
        return running, False
    try:
        subnets, hosts = await asyncio.to_thread(resolve_targets, [c for c in (cidrs or []) if str(c).strip()] or None)
    except DiscoveryError as e:
        raise _http(e)

    with _lock:
        if _job is not None and _job.status == "running":
            return _job.model_copy(deep=True), False
        job = ScanJob(
            id=str(uuid.uuid4()), status="running", subnets=subnets,
            scanned=0, total=len(hosts), started_at=_utcnow(),
        )
        _job = job
        _task = asyncio.get_running_loop().create_task(_run(job.id, hosts))
        snap = job.model_copy(deep=True)
    await _broadcast()
    return snap, True


async def send_snapshot(websocket) -> None:
    """Send current job to a freshly connected subscriber (if any)."""
    snap = _snapshot()
    if snap is not None:
        await websocket.send_json(snap.model_dump(mode="json"))


def reset_state() -> None:
    """Test helper: clear singleton state."""
    global _job, _task
    with _lock:
        _job = None
        _task = None
