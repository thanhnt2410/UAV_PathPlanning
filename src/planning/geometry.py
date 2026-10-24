"""GPS distances and a local metric projection for small survey areas."""
import math

EARTH_RADIUS = 6378137.0


def validate_point(point):
    if len(point) != 2:
        raise ValueError('GPS points must contain latitude and longitude')
    lat, lon = point
    if not all(math.isfinite(value) for value in point) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f'Invalid GPS coordinate: {point}')
    return lat, lon


def distance_between_points(a, b):
    lat_a, lon_a = map(math.radians, validate_point(a))
    lat_b, lon_b = map(math.radians, validate_point(b))
    value = math.sin((lat_b - lat_a) / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    return 2 * EARTH_RADIUS * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def gps_to_xy(point, origin):
    lat, lon = validate_point(point)
    lat_0, lon_0 = validate_point(origin)
    if abs(lat_0) >= 85 or abs(lon - lon_0) >= 180:
        raise ValueError('The basic local planner does not support poles or dateline crossings')
    return (EARTH_RADIUS * math.radians(lon - lon_0) * math.cos(math.radians(lat_0)),
            EARTH_RADIUS * math.radians(lat - lat_0))


def xy_to_gps(point, origin):
    lat, lon = origin
    return (lat + math.degrees(point[1] / EARTH_RADIUS),
            lon + math.degrees(point[0] / (EARTH_RADIUS * math.cos(math.radians(lat)))))
