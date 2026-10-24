"""Sample parallel scan lines inside a convex polygon, using meters."""
import math

from shapely.geometry import LineString, Polygon


def generate_grid(vertices, spacing_m, max_waypoints=500):
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError('Scan spacing must be finite and positive')
    polygon = Polygon(vertices)
    if not polygon.is_valid or polygon.is_empty or polygon.area <= 1e-6:
        raise ValueError('Draw a valid polygon with nonzero area')
    if polygon.convex_hull.area - polygon.area > max(1e-6, polygon.area * 1e-8):
        raise ValueError('The basic example accepts convex polygons only')
    min_x, min_y, max_x, max_y = polygon.bounds
    row_count = max(1, math.ceil((max_y - min_y) / spacing_m))
    if row_count * 2 > max_waypoints:
        raise ValueError('Too many scan rows; increase spacing or reduce the area')
    points = []
    for row in range(row_count):
        y = min_y + (row + 0.5) * (max_y - min_y) / row_count
        segment = polygon.intersection(LineString([(min_x - 1, y), (max_x + 1, y)]))
        if segment.is_empty:
            continue
        if segment.geom_type != 'LineString':
            raise ValueError('Unsupported scan-line intersection')
        count = max(1, math.ceil(segment.length / spacing_m))
        if len(points) + count + 1 > max_waypoints:
            raise ValueError('Too many waypoints; increase spacing or reduce the area')
        for index in range(count + 1):
            point = segment.interpolate(index / count, normalized=True)
            points.append((point.x, point.y))
    return points
