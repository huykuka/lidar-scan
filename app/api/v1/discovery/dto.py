"""Schemas for LiDAR device discovery."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Device(BaseModel):
    ip: str
    port: int = 2111
    device_name: str | None = None
    firmware_version: str | None = None
    serial: str | None = None
    raw: str
    lidar_type: str | None = None


class ScanJob(BaseModel):
    id: str
    status: Literal["running", "completed", "failed"]
    subnets: list[str]
    scanned: int
    total: int
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    devices: list[Device] = Field(default_factory=list)


class ScanRequest(BaseModel):
    cidrs: list[str] | None = None
