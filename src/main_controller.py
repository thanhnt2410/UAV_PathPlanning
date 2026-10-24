"""Connect the example view to reusable planning and flight services."""
import asyncio
import math

from PyQt5 import QtCore, QtWidgets

from interface_base import Interface
from planning.geometry import validate_point, xy_to_gps
from services.drone_service import DroneService
from services.mission_io import load_mission_file, save_points_file
from services.mission_planner import MissionPlanner, PlanningResult
from utils.logger import get_logger


class MainController:
    def __init__(self, config):
        self.config = config
        self.drone_service = DroneService(config)
        self.planner = MissionPlanner(config)
        self.view = Interface(config)
        self.logger = get_logger()
        self.mission = None
        self.results = []
        self._revision = 0
        self._tasks = set()
        self._busy = None
        origin = config.planning['start']
        points = [xy_to_gps(point, origin) for point in ((-30, -30), (60, -30), (60, 60), (-30, 60))]
        self.view.vertices.setPlainText('\n'.join(f'{lat:.8f},{lon:.8f}' for lat, lon in points))
        self.view.map.point_clicked.connect(self._add_vertex)
        self.view.map.polygon_changed.connect(self._set_polygon)
        self.view.map.load_error.connect(self._message)
        self.view.vertices.textChanged.connect(self._invalidate)
        self.view.spacing.valueChanged.connect(self._invalidate)
        self.view.altitude.valueChanged.connect(self._invalidate)
        self.view.footprint.valueChanged.connect(self._invalidate)
        self.view.results.itemSelectionChanged.connect(self._select_result)
        actions = {'Connect': self.drone_service.connect, 'Plan': self._plan,
                   'Upload': self._upload, 'Arm': self.drone_service.arm,
                   'Disarm': self.drone_service.disarm, 'Takeoff': self.drone_service.takeoff,
                   'Start / Resume': self._start, 'Pause': self.drone_service.pause_mission,
                   'RTL': self.drone_service.return_to_launch, 'Land': self.drone_service.land}
        for label, action in actions.items():
            self.view.buttons[label].clicked.connect(
                lambda checked=False, label=label, action=action:
                self._submit(label, action, priority=label in {'Pause', 'RTL', 'Land'}))
        self.view.buttons['Clear polygon'].clicked.connect(self.view.vertices.clear)
        self.view.buttons['Load CSV'].clicked.connect(self._load)
        self.view.buttons['Save CSV'].clicked.connect(self._save)
        self.view.close_requested.connect(lambda: self._submit('Close', self._close))
        self.timer = QtCore.QTimer(self.view)
        self.timer.timeout.connect(self._update_status)
        self.timer.start(500)
        self._draw(fit=True)

    def _submit(self, label, action, priority=False):
        if self._busy is not None and not self._busy.done() and not priority:
            self._message('Wait for the current action; Pause, RTL and Land remain available')
            return
        task = asyncio.create_task(self._perform(label, action))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        if not priority:
            self._busy = task

    async def _perform(self, label, action):
        try:
            self._message(f'{label}…')
            await action()
            self._message(f'{label}: done')
        except Exception as exc:
            self.logger.exception('%s failed', label)
            self._message(f'{label}: {exc}')

    def _message(self, text):
        self.view.messages.appendPlainText(text)

    def _vertices(self):
        points = []
        for line in self.view.vertices.toPlainText().splitlines():
            if line.strip():
                points.append(tuple(validate_point(tuple(map(float, line.split(','))))))
        return points

    def _add_vertex(self, latitude, longitude):
        self.view.vertices.appendPlainText(f'{latitude:.8f},{longitude:.8f}')

    def _set_polygon(self, points):
        self.view.vertices.setPlainText('\n'.join(f'{lat:.8f},{lon:.8f}' for lat, lon in points))

    def _invalidate(self, *args):
        self._revision += 1
        self.mission = None
        self.results = []
        self.view.show_results([])
        self._draw()

    def _draw(self, fit=False):
        try:
            vertices = self._vertices()
        except ValueError:
            vertices = []
        route = [(point.latitude, point.longitude) for point in self.mission] if self.mission else []
        status = self.drone_service.telemetry
        position = status.as_position() if status.connected else None
        if position is not None and not all(math.isfinite(value) for value in position):
            position = None
        self.view.map.update_map(vertices, route, position, fit)

    async def _plan(self):
        revision = self._revision
        status = self.drone_service.telemetry
        start = status.as_position() if status.connected else tuple(self.config.planning['start'])
        results = await asyncio.to_thread(self.planner.compare, self._vertices(), start,
                                          self.view.spacing.value(), self.view.altitude.value(),
                                          self.view.footprint.value())
        if revision != self._revision:
            raise RuntimeError('Inputs changed during planning; plan again')
        self.results = results
        self.mission = None
        self.view.show_results(results)
        for error in dict.fromkeys(result.error or result.energy_error for result in results):
            if error:
                self.logger.warning('%s', error)
                self._message(error)
        valid = [index for index, result in enumerate(results) if result.mission is not None]
        if not valid:
            self._draw()
            raise RuntimeError('No algorithm produced a valid route; see the result table')
        best = min(valid, key=lambda index: results[index].metrics['cost'])
        self.view.results.selectRow(best)
        self._message('Selected the lowest geometric cost. Preview only; no flight command sent.')

    def _select_result(self):
        row = self.view.results.currentRow()
        if not 0 <= row < len(self.results):
            return
        result = self.results[row]
        self.mission = result.mission
        self._draw(fit=True)
        if result.mission is not None:
            self._message(f'{result.algorithm}: {len(result.mission)} waypoints selected')
        elif result.error:
            self._message(result.error)

    async def _upload(self):
        if self.mission is None:
            raise RuntimeError('Plan or load a CSV mission first')
        await self.drone_service.upload_mission(self.mission)

    async def _start(self):
        if self.mission is None:
            raise RuntimeError('Plan and upload the current route before starting')
        await self.drone_service.start_mission(self.mission)

    def _load(self):
        dialog = QtWidgets.QFileDialog(self.view, 'Load mission CSV')
        dialog.setNameFilter('CSV files (*.csv)')
        dialog.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        dialog.fileSelected.connect(lambda filename: self._submit('Load CSV', lambda: self._load_file(filename)))
        dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        dialog.open()

    async def _load_file(self, filename):
        revision = self._revision
        mission = await asyncio.to_thread(load_mission_file, filename, self.view.altitude.value(),
                                          'mission', self.config.planning['max_waypoints'])
        metrics, error = await asyncio.to_thread(self.planner.analyzer.analyze, mission,
                                                 self._vertices(), self.view.footprint.value())
        if revision != self._revision:
            raise RuntimeError('Inputs changed while loading the mission; load again')
        self.results = [PlanningResult('CSV', mission, metrics, energy_error=error)]
        self.view.show_results(self.results)
        self.view.results.selectRow(0)
        if error:
            self.logger.warning('%s', error)
            self._message(error)

    def _save(self):
        if self.mission is None:
            self._message('Plan or load a mission first')
            return
        mission = self.mission
        dialog = QtWidgets.QFileDialog(self.view, 'Save mission CSV')
        dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dialog.setDefaultSuffix('csv')
        dialog.setNameFilter('CSV files (*.csv)')
        dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        dialog.fileSelected.connect(lambda filename: self._submit(
            'Save CSV', lambda: asyncio.to_thread(save_points_file, mission, filename)))
        dialog.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        dialog.open()

    def _update_status(self):
        state = self.drone_service.telemetry
        percent = 'N/A' if state.battery_percent is None else f'{state.battery_percent:.1f}%'
        self.view.telemetry.setText(
            f'Connected: {state.connected} | Armed: {state.armed}\n'
            f'Mode: {state.flight_mode} | Battery: {percent}\n'
            f'GPS: {state.gps_fix_type} | Health: {state.healthy}\n'
            f'Altitude: {state.altitude_relative_m:.1f} m | '
            f'Mission: {state.mission_current}/{state.mission_total}\n{state.error}')
        self._draw()

    async def _close(self):
        if any(not task.done() and task is not asyncio.current_task() for task in self._tasks):
            raise RuntimeError('Wait for running actions before closing')
        await self.drone_service.close()
        self.timer.stop()
        self.view._allow_close = True
        self.view.close()
