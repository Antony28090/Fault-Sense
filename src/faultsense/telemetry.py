"""Telemetry seam for Phase 3 (ESP32 current/vibration sensors over Modbus TCP)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


@dataclass(frozen=True)
class Reading:
    timestamp: datetime
    signal: str  # e.g. "motor_current", "vibration_rms"
    value: float
    unit: str


class TelemetrySource(Protocol):
    def recent(self, machine_id: str, window: timedelta) -> list[Reading]: ...


class NullTelemetrySource:
    """Phase 1: no sensors are connected."""

    def recent(self, machine_id: str, window: timedelta) -> list[Reading]:
        return []
