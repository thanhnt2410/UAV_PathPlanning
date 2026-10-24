"""Telemetry is independent of Qt so another GUI can reuse the service."""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class UAVTelemetry:
    connected: bool = False
    armed: bool = False
    in_air: bool = False
    flight_mode: str = 'UNKNOWN'
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_relative_m: float = 0.0
    battery_percent: Optional[float] = None
    gps_fix_type: str = 'UNKNOWN'
    healthy: bool = False
    mission_current: int = 0
    mission_total: int = 0
    error: str = ''

    def as_position(self) -> Optional[Tuple[float, float]]:
        if self.latitude is None or self.longitude is None:
            return None
        return self.latitude, self.longitude

    def has_healthy_gps_fix(self) -> bool:
        return self.gps_fix_type in {'FIX_3D', 'FIX_3D_DGPS', 'RTK_FLOAT', 'RTK_FIXED'}
