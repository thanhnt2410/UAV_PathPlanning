"""CSV mission import/export and the MAVSDK adapter."""
import csv
import math
from pathlib import Path

from domain.mission import Mission


def load_mission_file(mission_file, default_altitude=13.0, name='mission', max_waypoints=500):
    points = []
    with Path(mission_file).open(newline='', encoding='utf-8') as stream:
        for row in csv.reader(stream):
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) not in (2, 3):
                raise ValueError('CSV rows must contain latitude,longitude[,altitude]')
            if len(points) >= max_waypoints:
                raise ValueError('Mission exceeds max_waypoints')
            points.append(tuple(map(float, row)))
    if not points:
        raise ValueError('Mission is empty')
    return Mission.from_waypoints(points, default_altitude, name)


def save_points_file(mission, output_path):
    with Path(output_path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerows((point.latitude, point.longitude, point.altitude) for point in mission)


def to_mavsdk_mission_plan(mission, cruise_speed_ms=3.0):
    from mavsdk.mission import MissionItem, MissionPlan
    if not mission.items or not math.isfinite(cruise_speed_ms) or cruise_speed_ms <= 0:
        raise ValueError('Mission must be nonempty and cruise speed positive')
    return MissionPlan([
        MissionItem(latitude_deg=point.latitude, longitude_deg=point.longitude,
                    relative_altitude_m=point.altitude, speed_m_s=cruise_speed_ms,
                    is_fly_through=False, gimbal_pitch_deg=float('nan'), gimbal_yaw_deg=float('nan'),
                    loiter_time_s=0.0, camera_action=MissionItem.CameraAction.NONE,
                    camera_photo_interval_s=float('nan'), acceptance_radius_m=float('nan'),
                    yaw_deg=float('nan'), camera_photo_distance_m=float('nan'),
                    vehicle_action=MissionItem.VehicleAction.NONE)
        for point in mission
    ])
