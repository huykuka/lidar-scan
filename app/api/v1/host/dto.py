"""DTOs for host monitoring endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CpuFreq(BaseModel):
    current: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class CpuInfo(BaseModel):
    percent_total: float
    percent_per_core: List[float]
    count_logical: Optional[int]
    count_physical: Optional[int]
    freq_mhz: CpuFreq
    load_avg_1_5_15: List[float]


class RamInfo(BaseModel):
    total_mb: Optional[float]
    available_mb: Optional[float]
    used_mb: Optional[float]
    percent: float


class SwapInfo(BaseModel):
    total_mb: Optional[float]
    used_mb: Optional[float]
    percent: Optional[float]


class MemoryInfo(BaseModel):
    ram: RamInfo
    swap: Optional[SwapInfo]


class DiskPartition(BaseModel):
    device: str
    mountpoint: str
    fstype: str
    total_gb: Optional[float]
    used_gb: Optional[float]
    free_gb: Optional[float]
    percent: Optional[float]


class DiskIO(BaseModel):
    read_mb: Optional[float]
    write_mb: Optional[float]
    read_count: Optional[int]
    write_count: Optional[int]


class DiskInfo(BaseModel):
    partitions: List[DiskPartition]
    io: Optional[DiskIO]


class NetworkInterface(BaseModel):
    name: str
    ipv4: Optional[str]
    ipv6: Optional[str]
    is_up: Optional[bool]
    speed_mbps: Optional[int]
    sent_mb: Optional[float]
    recv_mb: Optional[float]
    packets_sent: Optional[int]
    packets_recv: Optional[int]
    errin: Optional[int]
    errout: Optional[int]


class NetworkInfo(BaseModel):
    interfaces: List[NetworkInterface]


class ProcessInfo(BaseModel):
    pid: int
    cpu_percent: Optional[float]
    rss_mb: Optional[float]
    vms_mb: Optional[float]
    num_threads: Optional[int]
    num_fds: Optional[int]
    create_time: Optional[float]
    uptime_s: float


class HostInfo(BaseModel):
    hostname: Optional[str]
    platform: Optional[str]
    python: Optional[str]
    boot_time: float
    uptime_s: float


class HostSnapshotResponse(BaseModel):
    host: HostInfo
    cpu: CpuInfo
    memory: MemoryInfo
    disk: DiskInfo
    network: NetworkInfo
    process: ProcessInfo
    collected_at: float
