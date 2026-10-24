"""Validated mission data; no dependency on Qt or MAVSDK."""
import math
from dataclasses import dataclass, field
from typing import List

from planning.geometry import validate_point


@dataclass(frozen=True)
class MissionItem:
    latitude: float
    longitude: float
    altitude: float = 13.0

    def __post_init__(self):
        validate_point((self.latitude, self.longitude))
        if not math.isfinite(self.altitude) or self.altitude <= 0:
            raise ValueError('Waypoint altitude must be finite and positive')


@dataclass
class Mission:
    items: List[MissionItem] = field(default_factory=list)
    name: str = 'mission'

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    @classmethod
    def from_waypoints(cls, waypoints, default_altitude=13.0, name='mission'):
        items = []
        for point in waypoints:
            if len(point) not in (2, 3):
                raise ValueError('Waypoints must contain lat, lon and optionally altitude')
            altitude = point[2] if len(point) == 3 else default_altitude
            items.append(MissionItem(float(point[0]), float(point[1]), float(altitude)))
        return cls(items=items, name=name)
