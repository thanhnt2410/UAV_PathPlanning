"""Validate survey inputs, call the student's algorithm, and build a mission."""
from collections import Counter
from dataclasses import dataclass, field
from time import perf_counter

from domain.mission import Mission
from planning import path_algorithms
from planning.geometry import distance_between_points, gps_to_xy, validate_point, xy_to_gps
from planning.grid import generate_grid
from planning.uav_analyzer import UAVAnalyzer


@dataclass
class PlanningResult:
    algorithm: str
    mission: Mission | None = None
    metrics: dict = field(default_factory=dict)
    error: str = ''
    energy_error: str = ''


class MissionPlanner:
    def __init__(self, config):
        self.config = config
        self.analyzer = UAVAnalyzer(config)

    def plan(self, vertices, start, spacing_m=None, altitude_m=None, algorithm=None) -> Mission:
        settings = self.config.planning
        altitude_m = altitude_m if altitude_m is not None else settings['altitude_m']
        if not 0 < altitude_m <= settings['max_altitude_m']:
            raise ValueError('Altitude must be positive and no greater than max_altitude_m')
        start = tuple(validate_point(start))
        if len(vertices) < 3:
            raise ValueError('Select at least three polygon vertices')
        if len(vertices) > settings['max_waypoints']:
            raise ValueError('Too many polygon vertices')
        if any(distance_between_points(start, point) > settings['max_radius_m'] for point in vertices):
            raise ValueError('Survey area exceeds max_radius_m from the start')
        local = [gps_to_xy(point, start) for point in vertices]
        points = generate_grid(local, spacing_m if spacing_m is not None else settings['spacing_m'],
                               settings['max_waypoints'] - 2)
        points = [xy_to_gps(point, start) for point in points]
        algorithm = path_algorithms.plan_path if algorithm is None else algorithm
        route = [tuple(point) for point in algorithm(points.copy(), start)]
        if not points or Counter(route) != Counter(points):
            raise ValueError('plan_path() must return every survey waypoint exactly once')
        if path_algorithms.closed_path_distance(route, start) > settings['max_distance_m']:
            raise ValueError('Route exceeds max_distance_m')
        return Mission.from_waypoints(path_algorithms.build_closed_path(route, start),
                                      altitude_m if altitude_m is not None else settings['altitude_m'])

    def compare(self, vertices, start, spacing_m=None, altitude_m=None, footprint_width_m=None):
        results = []
        for name, algorithm in path_algorithms.get_algorithms().items():
            result = PlanningResult(algorithm=name)
            started = perf_counter()
            try:
                mission = self.plan(vertices, start, spacing_m, altitude_m, algorithm)
                elapsed_ms = (perf_counter() - started) * 1000
                result.metrics, result.energy_error = self.analyzer.analyze(mission, vertices, footprint_width_m)
                result.metrics['planning_time_ms'] = elapsed_ms
                result.mission = mission
            except Exception as exc:
                result.error = f'{type(exc).__name__}: {exc}'
            results.append(result)
        return results
