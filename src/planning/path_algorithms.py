"""Replace plan_path() to teach or implement a different waypoint ordering."""
from .geometry import distance_between_points


def build_closed_path(route, start):
    route = [tuple(point) for point in route if tuple(point) != tuple(start)]
    return [tuple(start), *route, tuple(start)] if route else [tuple(start)]


def closed_path_distance(route, start):
    points = build_closed_path(route, start)
    return sum(distance_between_points(a, b) for a, b in zip(points, points[1:]))


def find_zigzag_path(points, start):
    """Choose the shortest of four row-wise sweep directions (not a global optimum)."""
    rows = {}
    for point in points:
        rows.setdefault(round(point[0], 9), []).append(tuple(point))
    ordered_rows = [sorted(rows[key], key=lambda point: point[1]) for key in sorted(rows)]
    candidates = []
    for row_order in (ordered_rows, ordered_rows[::-1]):
        for reverse_first in (False, True):
            route = []
            for index, row in enumerate(row_order):
                route.extend(row[::-1] if bool(index % 2) != reverse_first else row)
            candidates.append(route)
    return min(candidates, key=lambda route: closed_path_distance(route, start))


def plan_path(points: list[tuple[float, float]], start: tuple[float, float]) -> list[tuple[float, float]]:
    """Return survey waypoints only, as (latitude, longitude), each exactly once.

    The caller validates the permutation and adds the fixed start at both ends.
    Keep this function free of GUI and flight commands.
    """
    return find_zigzag_path(points, start)


def get_algorithms():
    """Add your algorithms here; the GUI compares and displays every entry."""
    return {'Zigzag': find_zigzag_path, 'Custom': plan_path}
