"""Tests for LiDAR device discovery (REST + WS + service)."""

import ipaddress
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.api.v1.discovery import service as svc
from app.modules.lidar.profiles import get_profile

GOOD = b"\x02sRA DeviceIdent 0 \x03"


def _ident(name="MRS1104C-111011", ver="1.3.0.0R"):
    return f"\x02sRA DeviceIdent {len(name):X} {name} {len(ver):X} {ver}\x03".encode()


@pytest.fixture(autouse=True)
def _reset():
    svc.reset_state()
    yield
    svc.reset_state()


@pytest.fixture
def dclient(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'd.db'}")
    from app.db.migrate import ensure_schema
    from app.db.session import init_engine

    ensure_schema(init_engine())
    from app.app import app

    with TestClient(app) as c:
        yield c


def _hdr(c, user):
    r = c.post("/api/v1/auth/login", json={"username": user, "password": user})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(svc, "get_local_ips", lambda: ["10.0.0.5"])


def _wait_done(c, h, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        j = c.get("/api/v1/discovery/scan", headers=h).json()
        if j and j["status"] != "running":
            return j
        time.sleep(0.02)
    raise AssertionError("scan did not finish")


# ---- parser / mapping ----

def test_parser_ok():
    d = svc.parse_device_ident("1.2.3.4", _ident())
    assert d.device_name == "MRS1104C-111011"
    assert d.firmware_version == "1.3.0.0R"
    assert d.serial is None and d.port == 2111
    assert d.raw.startswith("sRA DeviceIdent") and "\x02" not in d.raw
    assert d.lidar_type == "mrs_1xxx"


@pytest.mark.parametrize("raw", [b"\x02sRA DeviceIdent\x03", b"\x02sRA DeviceIdent zz\x03",
                                 b"\x02sRA DeviceIdent 20 short 3 1.0\x03", b"DeviceIdent \xff\xfe"])
def test_parser_malformed(raw):
    d = svc.parse_device_ident("1.2.3.4", raw)
    assert d.device_name is None and d.firmware_version is None and d.lidar_type is None
    assert d.raw


@pytest.mark.parametrize("name,expected", [
    ("MRS1104C-111011", "mrs_1xxx"), ("TiM-781S", "tim_7xxs"), ("TiM781", "tim_7xx"),
    ("LMS_511 PRO", "lms_5xx"), ("multiScan136", "multiscan136"), ("picoScan150", "picoscan_150"),
    ("Unknown123", None), (None, None), ("", None),
])
def test_mapping(name, expected):
    assert svc.map_lidar_type(name) == expected


def test_mapped_model_ids_exist():
    for mid in set(svc._TYPE_PREFIXES.values()):
        assert get_profile(mid).model_id == mid


# ---- subnets ----

def test_auto_excludes_and_24(monkeypatch):
    monkeypatch.setattr(svc.socket, "getaddrinfo", lambda *a, **k: [
        (0, 0, 0, "", ("127.0.0.1", 0)), (0, 0, 0, "", ("169.254.1.2", 0)),
        (0, 0, 0, "", ("192.168.1.10", 0)), (0, 0, 0, "", ("192.168.1.11", 0))])

    class S:
        def connect(self, a): pass
        def getsockname(self): return ("10.1.2.3", 1)
        def close(self): pass
    monkeypatch.setattr(svc.socket, "socket", lambda *a, **k: S())
    subnets, hosts = svc.resolve_targets(None)
    assert subnets == ["10.1.2.0/24", "192.168.1.0/24"]
    assert len(hosts) == 254 * 2 - 3
    assert "192.168.1.10" not in hosts and "192.168.1.11" not in hosts and "10.1.2.3" not in hosts


def test_explicit_replaces_auto_and_dedupes(local):
    subnets, hosts = svc.resolve_targets(["192.168.5.0/24", "192.168.5.0/25", "192.168.5.7/24"])
    assert subnets == ["192.168.5.0/24"]
    assert len(hosts) == 254 and len(set(hosts)) == 254
    assert not any(h.startswith("10.0.0.") for h in hosts)


def test_explicit_excludes_local_ip(local):
    _, hosts = svc.resolve_targets(["10.0.0.0/29"])
    assert "10.0.0.5" not in hosts and len(hosts) == 5


@pytest.mark.parametrize("bad", ["abc", "10.0.0.0/33", "::1/128", "300.1.1.1/24"])
def test_invalid_cidr(local, bad):
    with pytest.raises(svc.DiscoveryError) as e:
        svc.resolve_targets([bad])
    assert e.value.detail["code"] == "invalid_cidr" and e.value.detail["cidr"] == bad


def test_host_cap(local):
    with pytest.raises(svc.DiscoveryError) as e:
        svc.resolve_targets(["10.0.0.0/8"])
    d = e.value.detail
    assert d["code"] == "too_many_hosts" and d["max"] == 4096 and d["total"] > 4096
    _, hosts = svc.resolve_targets(["10.0.0.0/20"])  # 4094 hosts - local
    assert len(hosts) == 4093


def test_no_subnet(monkeypatch):
    monkeypatch.setattr(svc, "get_local_ips", lambda: [])
    with pytest.raises(svc.DiscoveryError) as e:
        svc.resolve_targets(None)
    assert e.value.detail["code"] == "no_subnet"


# ---- REST ----

def test_auth(dclient):
    assert dclient.get("/api/v1/discovery/scan").status_code == 401
    assert dclient.post("/api/v1/discovery/scan", json={}).status_code == 401
    u = _hdr(dclient, "user")
    assert dclient.post("/api/v1/discovery/scan", json={}, headers=u).status_code == 403
    assert dclient.get("/api/v1/discovery/scan", headers=u).status_code == 200


def test_get_null(dclient):
    r = dclient.get("/api/v1/discovery/scan", headers=_hdr(dclient, "user"))
    assert r.status_code == 200 and r.json() is None


def test_422_shapes(dclient, local):
    h = _hdr(dclient, "admin")
    r = dclient.post("/api/v1/discovery/scan", json={"cidrs": ["nope"]}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_cidr"
    r = dclient.post("/api/v1/discovery/scan", json={"cidrs": ["10.0.0.0/8"]}, headers=h)
    assert r.json()["detail"]["code"] == "too_many_hosts"


def test_lifecycle_202_200_completed(dclient, local, monkeypatch):
    gate = threading.Event()

    def probe(ip, *a, **k):
        gate.wait(5)
        return _ident() if ip == "10.0.0.2" else None
    monkeypatch.setattr(svc, "probe_sick_device", probe)
    h = _hdr(dclient, "admin")
    r1 = dclient.post("/api/v1/discovery/scan", json={"cidrs": ["10.0.0.0/29"]}, headers=h)
    assert r1.status_code == 202
    j = r1.json()
    assert j["status"] == "running" and j["total"] == 5 and j["subnets"] == ["10.0.0.0/29"]
    assert j["started_at"].endswith("Z")
    r2 = dclient.post("/api/v1/discovery/scan", json={"cidrs": ["10.9.0.0/29"]}, headers=h)
    assert r2.status_code == 200 and r2.json()["id"] == j["id"]
    gate.set()
    done = _wait_done(dclient, h)
    assert done["status"] == "completed" and done["scanned"] == 5 and done["finished_at"]
    assert [d["ip"] for d in done["devices"]] == ["10.0.0.2"]
    # cached + new scan allowed afterwards
    assert dclient.get("/api/v1/discovery/scan", headers=h).json()["id"] == j["id"]
    r3 = dclient.post("/api/v1/discovery/scan", json={"cidrs": ["10.0.0.0/30"]}, headers=h)
    assert r3.status_code == 202 and r3.json()["id"] != j["id"]
    _wait_done(dclient, h)


def test_failed(dclient, local, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(svc, "_scan_blocking", boom)
    h = _hdr(dclient, "admin")
    assert dclient.post("/api/v1/discovery/scan", json={"cidrs": ["10.0.0.0/30"]}, headers=h).status_code == 202
    j = _wait_done(dclient, h)
    assert j["status"] == "failed" and j["error"] == "x" and j["finished_at"]


def test_probe_mocked_socket(monkeypatch):
    class S:
        def settimeout(self, t): assert t == 0.3
        def connect(self, a): assert a == ("1.2.3.4", 2111)
        def sendall(self, b): assert b == b"\x02sRN DeviceIdent\x03"
        def recv(self, n): return _ident()
        def close(self): pass
    monkeypatch.setattr(svc.socket, "socket", lambda *a, **k: S())
    assert b"DeviceIdent" in svc.probe_sick_device("1.2.3.4")


# ---- WS ----

def test_ws_snapshot_and_broadcast(dclient, local, monkeypatch):
    monkeypatch.setattr(svc, "probe_sick_device", lambda ip, *a, **k: _ident() if ip == "10.0.0.1" else None)
    h = _hdr(dclient, "admin")
    token = h["Authorization"].split()[1]
    with pytest.raises(Exception):
        with dclient.websocket_connect("/api/v1/ws/device_discovery"):
            pass
    with dclient.websocket_connect(f"/api/v1/ws/device_discovery?token={token}") as ws:
        assert dclient.post("/api/v1/discovery/scan", json={"cidrs": ["10.0.0.0/29"]}, headers=h).status_code == 202
        last = None
        for _ in range(50):
            last = ws.receive_json()
            if last["status"] != "running":
                break
        assert last["status"] == "completed" and last["devices"][0]["ip"] == "10.0.0.1"
    # late subscriber gets snapshot
    with dclient.websocket_connect(f"/api/v1/ws/device_discovery?token={token}") as ws:
        assert ws.receive_json()["status"] == "completed"


def test_topic_hidden_and_other_topics_ok(dclient):
    topics = dclient.get("/api/v1/topics").json()["topics"]
    assert all(t["topic"] != "device_discovery" for t in topics)
