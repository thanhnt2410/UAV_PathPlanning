"""Single-UAV MAVSDK service with explicit actions and bounded safety checks."""
import asyncio
import math
import time
from dataclasses import replace

from mavsdk import System

from domain.mission import Mission
from domain.uav import UAVTelemetry
from planning.geometry import distance_between_points
from services.mission_io import to_mavsdk_mission_plan
from utils.logger import get_logger


class DroneService:
    def __init__(self, config):
        self.config = config
        self.telemetry = UAVTelemetry()
        self.system = None
        self.logger = get_logger()
        self._poll_task = None
        self._progress_task = None
        self._refresh_lock = asyncio.Lock()
        self._action_lock = asyncio.Lock()
        self._uploaded = None
        self._mission_started = None
        self._failsafe_sent = False
        self._interrupted = False
        self._manual_return = False

    async def _read(self, factory):
        stream = factory()
        try:
            return await asyncio.wait_for(stream.__anext__(), self.config.safety['telemetry_timeout_s'])
        finally:
            await stream.aclose()

    async def _command(self, awaitable):
        return await asyncio.wait_for(awaitable, self.config.safety['command_timeout_s'])

    def _connected(self):
        if self.system is None or not self.telemetry.connected:
            raise ConnectionError('Connect to the UAV first')

    async def connect(self) -> None:
        if self.system is not None:
            raise RuntimeError('Already connected or connecting; restart the app to change endpoint')
        self.system = System(port=self.config.connection['server_port'])
        try:
            async def establish():
                await self.system.connect(system_address=self.config.connection['system_address'])
                stream = self.system.core.connection_state()
                try:
                    async for state in stream:
                        if state.is_connected:
                            return
                finally:
                    await stream.aclose()
                raise ConnectionError('Connection stream ended')
            await asyncio.wait_for(establish(), self.config.safety['connect_timeout_s'])
            await self.get_status()
            self._progress_task = asyncio.create_task(self._watch_mission_progress())
            self._poll_task = asyncio.create_task(self._poll())
        except BaseException:
            await self._stop_server()
            self.system = None
            self.telemetry.connected = False
            raise
        self.logger.info('Connected to %s; no flight parameters or failsafes changed',
                         self.config.connection['system_address'])

    async def get_status(self) -> UAVTelemetry:
        if self.system is None:
            raise ConnectionError('No MAVSDK connection')
        async with self._refresh_lock:
            factories = (self.system.core.connection_state, self.system.telemetry.position,
                         self.system.telemetry.battery, self.system.telemetry.flight_mode,
                         self.system.telemetry.armed, self.system.telemetry.in_air,
                         self.system.telemetry.gps_info, self.system.telemetry.health)
            values = await asyncio.gather(*(self._read(factory) for factory in factories), return_exceptions=True)
            for value in values:
                if isinstance(value, BaseException):
                    raise RuntimeError(f'Telemetry unavailable or timed out: {value}') from value
            state, position, battery, mode, armed, in_air, gps, health = values
            percent = battery.remaining_percent * 100 / self.config.safety['battery_percent_scale']
            if not math.isfinite(percent) or not 0 <= percent <= 100:
                raise ValueError('Invalid battery reading; verify battery_percent_scale')
            valid_position = all(math.isfinite(value) for value in
                                 (position.latitude_deg, position.longitude_deg, position.relative_altitude_m))
            valid_position = valid_position and -90 <= position.latitude_deg <= 90 and -180 <= position.longitude_deg <= 180
            healthy = valid_position and all((health.is_gyrometer_calibration_ok,
                                              health.is_accelerometer_calibration_ok,
                                              health.is_magnetometer_calibration_ok,
                                              health.is_local_position_ok, health.is_global_position_ok,
                                              health.is_home_position_ok))
            self.telemetry = replace(self.telemetry, connected=state.is_connected, armed=armed,
                                     in_air=in_air, latitude=position.latitude_deg,
                                     longitude=position.longitude_deg,
                                     altitude_relative_m=position.relative_altitude_m,
                                     battery_percent=percent, flight_mode=mode.name,
                                     gps_fix_type=gps.fix_type.name, healthy=healthy, error='')
            if not state.is_connected:
                raise ConnectionError('UAV connection lost')
            return self.telemetry

    async def _preflight(self):
        self._connected()
        status = await self.get_status()
        if not status.healthy or not status.has_healthy_gps_fix():
            raise RuntimeError('Health, calibrated sensors, GPS and home position must be valid')
        if status.battery_percent < self.config.safety['minimum_battery_percent']:
            raise RuntimeError('Battery below minimum_battery_percent')
        if status.flight_mode not in {'READY', 'HOLD', 'TAKEOFF', 'MISSION'}:
            raise RuntimeError(f'Unsupported flight mode: {status.flight_mode}')
        return status

    async def arm(self) -> None:
        async with self._action_lock:
            status = await self._preflight()
            if status.in_air:
                raise RuntimeError('Cannot arm while airborne')
            self._failsafe_sent = False
            self._interrupted = False
            self._manual_return = False
            await self._command(self.system.action.arm())
            await self._wait_for(lambda state: state.armed, self.config.safety['command_timeout_s'])

    async def disarm(self) -> None:
        async with self._action_lock:
            self._connected()
            if (await self.get_status()).in_air:
                raise RuntimeError('Land before disarming')
            await self._command(self.system.action.disarm())
            await self._wait_for(lambda state: not state.armed, self.config.safety['command_timeout_s'])

    async def takeoff(self) -> None:
        async with self._action_lock:
            status = await self._preflight()
            if not status.armed or status.in_air:
                raise RuntimeError('Arm explicitly on the ground before takeoff')
            altitude = self._uploaded.items[0].altitude if self._uploaded else self.config.planning['altitude_m']
            self._interrupted = False
            self._manual_return = False
            try:
                await self._command(self.system.action.set_takeoff_altitude(altitude))
                await self._command(self.system.action.takeoff())
                await self._wait_for(lambda state: state.in_air and state.flight_mode in {'TAKEOFF', 'HOLD'}
                                     and state.altitude_relative_m >= altitude * 0.9,
                                     self.config.safety['takeoff_timeout_s'], check_interrupted=True)
            except (Exception, asyncio.CancelledError):
                if not self._interrupted:
                    await self._failsafe('Takeoff failed or was cancelled')
                raise

    async def _wait_for(self, predicate, timeout, check_interrupted=False):
        async def wait():
            while True:
                if check_interrupted and self._interrupted:
                    raise RuntimeError('Flight action interrupted by Land or RTL')
                status = await self.get_status()
                if predicate(status):
                    return
                await asyncio.sleep(self.config.safety['telemetry_interval_s'])
        await asyncio.wait_for(wait(), timeout)

    async def upload_mission(self, mission: Mission) -> None:
        async with self._action_lock:
            self._connected()
            status = await self.get_status()
            if status.armed or status.in_air:
                raise RuntimeError('Upload only while disarmed and on the ground')
            mission = Mission(items=list(mission.items), name=mission.name)
            settings = self.config.planning
            if not 2 <= len(mission) <= settings['max_waypoints']:
                raise ValueError('Mission must contain 2..max_waypoints entries')
            if not status.healthy or not status.has_healthy_gps_fix():
                raise RuntimeError('Valid GPS/home and health are required before upload')
            position = status.as_position()
            points = [(item.latitude, item.longitude) for item in mission]
            if any(distance_between_points(position, point) > settings['max_radius_m'] for point in points):
                raise ValueError('Mission exceeds max_radius_m from the current UAV position')
            if any(item.altitude > settings['max_altitude_m'] for item in mission):
                raise ValueError('Mission exceeds max_altitude_m')
            distance = sum(distance_between_points(a, b) for a, b in zip([position, *points], [*points, position]))
            if distance > settings['max_distance_m']:
                raise ValueError('Mission exceeds max_distance_m')
            self._uploaded = None
            await self._command(self.system.mission.set_return_to_launch_after_mission(True))
            await self._command(self.system.mission.upload_mission(
                to_mavsdk_mission_plan(mission, settings['speed_m_s'])))
            self._uploaded = Mission(items=list(mission.items), name=mission.name)

    async def start_mission(self, mission: Mission | None = None) -> None:
        async with self._action_lock:
            status = await self._preflight()
            if mission is not None and (self._uploaded is None or mission.items != self._uploaded.items):
                raise RuntimeError('Upload the current route before starting')
            if self._uploaded is None or not status.armed or not status.in_air:
                raise RuntimeError('Upload a mission, Arm, then Takeoff before starting')
            if self._failsafe_sent:
                raise RuntimeError('A failsafe has been triggered; land before restarting')
            self._interrupted = False
            self._manual_return = False
            if self._mission_started is None:
                self._mission_started = time.monotonic()
            try:
                await self._command(self.system.mission.start_mission())
                await self._wait_for(lambda state: state.flight_mode == 'MISSION',
                                     self.config.safety['command_timeout_s'], check_interrupted=True)
            except (Exception, asyncio.CancelledError):
                if not self._interrupted:
                    await self._failsafe('Mission start or mode verification failed')
                raise

    async def pause_mission(self) -> None:
        self._connected()
        self._interrupted = True
        await self._command(self.system.mission.pause_mission())
        await self._wait_for(lambda state: state.flight_mode == 'HOLD', self.config.safety['command_timeout_s'])

    async def land(self) -> None:
        self._connected()
        self._interrupted = True
        self._manual_return = True
        try:
            await self._command(self.system.action.land())
            await self._wait_for(lambda state: state.flight_mode == 'LAND' or not state.in_air,
                                 self.config.safety['command_timeout_s'])
        except BaseException:
            self._manual_return = False
            raise

    async def return_to_launch(self) -> None:
        self._connected()
        self._interrupted = True
        self._manual_return = True
        self.logger.info('RTL requested by explicit control action')
        try:
            await self._command(self.system.action.return_to_launch())
            await self._wait_for(lambda state: state.flight_mode == 'RETURN_TO_LAUNCH' or not state.in_air,
                                 self.config.safety['command_timeout_s'])
        except BaseException:
            self._manual_return = False
            raise

    async def _failsafe(self, reason):
        if self._failsafe_sent or self._manual_return or self.system is None:
            return
        self._failsafe_sent = True
        self._interrupted = True
        self.logger.error('%s; requesting RTL. PX4 failsafes remain enabled.', reason)
        try:
            await self._command(self.system.action.return_to_launch())
        except Exception:
            self.logger.exception('RTL request failed; check the PX4 link and onboard failsafe')

    async def _watch_mission_progress(self):
        # Progress is event-driven: no update while travelling is not link loss.
        while True:
            stream = self.system.mission.mission_progress()
            try:
                async for progress in stream:
                    self.telemetry = replace(self.telemetry, mission_current=progress.current,
                                             mission_total=progress.total)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception('Mission progress unavailable; safety telemetry remains monitored')
            finally:
                await stream.aclose()
            await asyncio.sleep(self.config.safety['telemetry_interval_s'])

    async def _poll(self):
        try:
            while True:
                try:
                    status = await self.get_status()
                    if status.in_air:
                        if (not status.healthy or not status.has_healthy_gps_fix()
                                or status.battery_percent < self.config.safety['return_battery_percent']):
                            await self._failsafe('Unsafe health, GPS or battery during flight')
                        if self._mission_started is not None:
                            if time.monotonic() - self._mission_started > self.config.safety['mission_timeout_s']:
                                await self._failsafe('Mission deadline exceeded')
                    else:
                        self._mission_started = None
                except Exception as exc:
                    was_flying = self.telemetry.in_air or self.telemetry.armed
                    self.telemetry = replace(self.telemetry, connected=False, error=str(exc))
                    self.logger.error('Telemetry monitor: %s: %s', type(exc).__name__, exc)
                    if was_flying:
                        await self._failsafe('Telemetry lost during flight')
                await asyncio.sleep(self.config.safety['telemetry_interval_s'])
        except asyncio.CancelledError:
            return

    async def _stop_server(self):
        if self.system is not None:
            await asyncio.to_thread(self.system._stop_mavsdk_server)

    async def close(self) -> None:
        if self.system is not None:
            await self.get_status()
        if self.telemetry.armed or self.telemetry.in_air:
            raise RuntimeError('Land and disarm before closing the UAV connection')
        if self._poll_task is not None:
            self._poll_task.cancel()
            await asyncio.gather(self._poll_task, return_exceptions=True)
        if self._progress_task is not None:
            self._progress_task.cancel()
            await asyncio.gather(self._progress_task, return_exceptions=True)
        await self._stop_server()
        self.system = None
        self.telemetry.connected = False
