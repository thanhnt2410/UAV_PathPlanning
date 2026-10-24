"""Small, validated configuration shared by the GUI and MAVSDK service."""
import math
from pathlib import Path

import yaml

from planning.geometry import validate_point


class ConfigLoader:
    def __init__(self, path=None):
        self.ROOT_DIR = Path(__file__).resolve().parents[1]
        path = Path(path) if path else self.ROOT_DIR / 'config/uav_config.yaml'
        with path.open(encoding='utf-8') as stream:
            self.uav = yaml.safe_load(stream)
        if not isinstance(self.uav, dict):
            raise ValueError('Configuration must be a YAML mapping')
        config_dir = self.ROOT_DIR / 'config'
        with (config_dir / 'init_pos_uavs.yaml').open(encoding='utf-8') as stream:
            self.init_pos = yaml.safe_load(stream)
        if not isinstance(self.init_pos, dict) or not isinstance(self.init_pos.get('uav_1'), dict):
            raise ValueError('init_pos_uavs.yaml must define uav_1 latitude and longitude')
        position = self.init_pos['uav_1']
        coordinates = (position.get('latitude'), position.get('longitude'))
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in coordinates):
            raise ValueError('uav_1 latitude and longitude must be numbers')
        self.initial_position = validate_point(coordinates)
        with (config_dir / 'interface_config.yaml').open(encoding='utf-8') as stream:
            self.interface = yaml.safe_load(stream)
        if not isinstance(self.interface, dict) or not isinstance(self.interface.get('map'), dict):
            raise ValueError('interface_config.yaml must define map.main_html')
        map_url = self.interface['map'].get('main_html')
        if not isinstance(map_url, str) or not map_url.startswith('file://'):
            raise ValueError('map.main_html must be a local file:// URL')
        self.map_html = Path(map_url[7:].replace('{ROOT_DIR}', str(self.ROOT_DIR)))
        if not self.map_html.is_file():
            raise ValueError(f'Map HTML does not exist: {self.map_html}')
        self.connection = self.uav['connection']
        self.planning = self.uav['planning']
        self.safety = self.uav['safety']
        self.analysis = self.uav['analysis']
        self.energy_model = self.uav['energy_model']
        for section in (self.connection, self.planning, self.safety, self.analysis, self.energy_model):
            if not isinstance(section, dict):
                raise ValueError('Configuration sections must be mappings')
        # Keep the planner API; the initial position has a single YAML source.
        self.planning['start'] = self.initial_position
        if not isinstance(self.connection['system_address'], str) or not self.connection['system_address']:
            raise ValueError('A MAVSDK system_address is required')
        for section, key in ((self.connection, 'server_port'), (self.planning, 'max_waypoints')):
            value = section[key]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f'{key} must be a positive integer')
        if self.connection['server_port'] > 65535:
            raise ValueError('server_port must be at most 65535')
        for section, keys in (
            (self.planning, ('altitude_m', 'speed_m_s', 'spacing_m', 'max_altitude_m', 'max_radius_m', 'max_distance_m')),
            (self.analysis, ('footprint_width_m', 'turn_threshold_deg')),
            (self.safety, ('connect_timeout_s', 'telemetry_timeout_s', 'command_timeout_s',
                          'takeoff_timeout_s', 'mission_timeout_s', 'telemetry_interval_s')),
        ):
            for key in keys:
                value = section[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise ValueError(f'{key} must be finite and positive')
        if self.analysis['turn_threshold_deg'] > 180:
            raise ValueError('turn_threshold_deg must be at most 180')
        for key in ('turn_penalty_m', 'time_weight', 'energy_weight'):
            value = self.analysis[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{key} must be finite and nonnegative')
        for key in ('directory', 'name'):
            if not isinstance(self.energy_model[key], str) or not self.energy_model[key].strip():
                raise ValueError(f'energy_model.{key} must be a nonempty string')
        if any(char in self.energy_model['name'] for char in '/\\'):
            raise ValueError('energy_model.name must be a model name, not a path')
        if self.planning['altitude_m'] > self.planning['max_altitude_m']:
            raise ValueError('altitude_m must not exceed max_altitude_m')
        arm = self.safety['minimum_battery_percent']
        rtl = self.safety['return_battery_percent']
        if not 0 < rtl < arm <= 100:
            raise ValueError('Require 0 < return_battery_percent < minimum_battery_percent <= 100')
        if self.safety['battery_percent_scale'] not in (1, 100):
            raise ValueError('battery_percent_scale must be 1 or 100')
