"""Route metrics and optional predictions from the existing regression models."""
import math
import pickle
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from planning.geometry import distance_between_points, gps_to_xy

FEATURE_COLUMNS = ['total_distance_m', 'stop_count']


class UAVAnalyzer:
    def __init__(self, config):
        self.config = config

    def analyze(self, mission, vertices=None, footprint_width_m=None):
        points = [(point.latitude, point.longitude) for point in mission]
        if len(points) < 2:
            raise ValueError('At least two mission waypoints are required for analysis')
        settings = self.config.analysis
        width = settings['footprint_width_m'] if footprint_width_m is None else footprint_width_m
        if not math.isfinite(width) or width <= 0:
            raise ValueError('Footprint width must be finite and positive')
        distance = sum(distance_between_points(a, b) for a, b in zip(points, points[1:]))
        local = []
        for point in points:
            xy = gps_to_xy(point, points[0])
            if not local or math.dist(local[-1], xy) > 1e-6:
                local.append(xy)
        headings = [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(local, local[1:])]
        turns = sum(abs((b - a + math.pi) % (2 * math.pi) - math.pi)
                    >= math.radians(settings['turn_threshold_deg'])
                    for a, b in zip(headings, headings[1:]))
        metrics = dict(distance_m=distance, turns=turns, waypoint_count=len(points),
                       stop_count=len(points) - 1, cost=distance + settings['turn_penalty_m'] * turns,
                       coverage_percent=None, overlap_percent=None, swept_area_m2=distance * width,
                       predicted_time_s=None, predicted_energy_wh=None, score=None)
        if vertices and len(vertices) >= 3:
            area = Polygon([gps_to_xy(point, points[0]) for point in vertices])
            if not area.is_valid or area.area <= 0:
                raise ValueError('Coverage analysis requires a valid nonzero survey area')
            strips = [LineString([a, b]).buffer(width / 2, cap_style='flat')
                      for a, b in zip(local, local[1:])]
            clipped = [strip.intersection(area) for strip in strips]
            covered = unary_union(clipped).area if clipped else 0.0
            total = sum(strip.area for strip in clipped)
            metrics['coverage_percent'] = min(100.0, 100 * covered / area.area)
            metrics['overlap_percent'] = 100 * max(0.0, total - covered) / total if total else 0.0
        error = ''
        try:
            energy, duration = self._predict_energy_time(distance, len(points) - 1)
            metrics['predicted_energy_wh'] = energy
            metrics['predicted_time_s'] = duration
            metrics['score'] = (metrics['cost'] + settings['time_weight'] * duration
                                + settings['energy_weight'] * energy)
        except Exception as exc:
            # Geometry remains useful when optional model files/dependencies are missing.
            error = f'No regression prediction: {type(exc).__name__}: {exc}'
        return metrics, error

    def _predict_energy_time(self, distance_m, stop_count):
        import pandas as pd
        from sklearn.exceptions import InconsistentVersionWarning
        import warnings

        settings = self.config.energy_model
        folder = Path(settings['directory'])
        if not folder.is_absolute():
            folder = self.config.ROOT_DIR / folder
        features = pd.DataFrame([[distance_m, stop_count]], columns=FEATURE_COLUMNS)
        predictions = {}
        for target in ('total_flight_energy_wh', 'total_flight_time_s'):
            path = folder / f"{target}_{settings['name']}.pkl"
            with warnings.catch_warnings():
                warnings.simplefilter('error', InconsistentVersionWarning)
                with path.open('rb') as stream:
                    model = pickle.load(stream)
            names = getattr(model, 'feature_names_in_', FEATURE_COLUMNS)
            if list(names) != FEATURE_COLUMNS:
                raise ValueError(f'{path.name}: expected features {FEATURE_COLUMNS}')
            value = float(model.predict(features)[0])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f'{path.name}: prediction must be finite and nonnegative')
            predictions[target] = value
        return predictions['total_flight_energy_wh'], predictions['total_flight_time_s']
