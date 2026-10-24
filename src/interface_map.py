"""Adapt the basic GUI to the original, unchanged assets/map.js API."""
import json
from pathlib import Path

from PyQt5 import QtCore
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView

from planning.geometry import validate_point
from utils.logger import get_logger


class _MapBridge(QtCore.QObject):
    def __init__(self, view):
        super().__init__(view)
        self.view = view

    @QtCore.pyqtSlot(float, float)
    def pointClicked(self, latitude, longitude):
        self.view.point_clicked.emit(latitude, longitude)

    @QtCore.pyqtSlot(float, float)
    def mapLeftClicked(self, latitude, longitude):
        self.pointClicked(latitude, longitude)

    @QtCore.pyqtSlot(float, float)
    def mapMoved(self, latitude, longitude):
        self.view.logger.debug('Map moved to %s, %s', latitude, longitude)

    @QtCore.pyqtSlot(float, float)
    def mapRightClicked(self, latitude, longitude):
        self.view.logger.debug('Map right-click at %s, %s', latitude, longitude)

    @QtCore.pyqtSlot(float, float)
    def mapDoubleClicked(self, latitude, longitude):
        self.view.logger.debug('Map double-click at %s, %s', latitude, longitude)

    @QtCore.pyqtSlot(str, float, float, name='markerMoved')
    @QtCore.pyqtSlot(str, float, float, name='markerClicked')
    @QtCore.pyqtSlot(str, float, float, name='markerRightClicked')
    @QtCore.pyqtSlot(str, float, float, name='markerDoubleClicked')
    def marker_event(self, key, latitude, longitude):
        self.view.logger.debug('Map marker %s at %s, %s', key, latitude, longitude)

    @QtCore.pyqtSlot(str)
    def geoJsonHandle(self, payload):
        try:
            geometry = json.loads(payload)['geometry']
            if geometry['type'] != 'Polygon' or len(geometry['coordinates']) != 1:
                raise ValueError('The basic planner accepts a polygon without holes')
            points = [validate_point(tuple(point[:2][::-1])) for point in geometry['coordinates'][0]]
            if points and points[0] == points[-1]:
                points.pop()
            if len(points) < 3:
                raise ValueError('A survey polygon needs at least three vertices')
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            self.view.logger.warning('Map geometry rejected: %s', exc)
            self.view.load_error.emit(f'Map geometry: {exc}')
            return
        self.view.polygon_changed.emit(points)


class Map(QWebEngineView):
    point_clicked = QtCore.pyqtSignal(float, float)
    polygon_changed = QtCore.pyqtSignal(object)
    load_error = QtCore.pyqtSignal(str)

    def __init__(self, parent=None, html_path=None, map_settings=None):
        super().__init__(parent)
        # Keep map_settings for compatibility; assets/map.js owns the original basemap.
        self._ready = False
        self.logger = get_logger()
        self._state = dict(polygon=[], route=[], position=None, fit=False)
        self._last_rendered = None
        self._probe_attempts = 0
        self._ready_timer = QtCore.QTimer(self)
        self._ready_timer.setInterval(100)
        self._ready_timer.timeout.connect(self._check_ready)
        self.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.channel = QWebChannel(self.page())
        self.bridge = _MapBridge(self)
        self.channel.registerObject('qtWidget', self.bridge)
        self.page().setWebChannel(self.channel)
        self.loadStarted.connect(self._loading)
        self.loadFinished.connect(self._loaded)
        html_path = html_path or Path(__file__).resolve().parents[1] / 'assets/map.html'
        self.load(QtCore.QUrl.fromLocalFile(str(html_path)))

    def _loading(self):
        self._ready = False
        self._last_rendered = None
        self._ready_timer.stop()

    def _loaded(self, ok):
        if not ok:
            self.load_error.emit('Map HTML failed to load')
            return
        self._probe_attempts = 0
        self._ready_timer.start()

    def _check_ready(self):
        self._probe_attempts += 1
        if self._probe_attempts > 150:
            self._ready_timer.stop()
            message = 'Map initialization timed out; check Leaflet/CDN access and JavaScript console'
            self.logger.error(message)
            self.load_error.emit(message)
            return
        self.page().runJavaScript(
            "typeof map !== 'undefined' && !!map && !!map._loaded && "
            "typeof qtWidget !== 'undefined' && !!qtWidget && "
            "typeof drawPolyLineJs === 'function'", self._map_ready)

    def _map_ready(self, ready):
        if ready and not self._ready:
            self._ready = True
            self._ready_timer.stop()
            self._render()

    def update_map(self, polygon=None, route=None, position=None, fit=False):
        if polygon is not None:
            self._state['polygon'] = polygon
        if route is not None:
            self._state['route'] = route
        self._state['position'] = position
        self._state['fit'] = fit or self._state['fit']
        self._render()

    def _render(self):
        if not self._ready:
            return
        payload = json.dumps(self._state, allow_nan=False)
        if payload != self._last_rendered:
            self.page().runJavaScript('''(function(state) {
                if (!state.polygon.length) {
                    map.eachLayer(function(group) {
                        if (group instanceof L.FeatureGroup) group.eachLayer(function(layer) {
                            if (layer instanceof L.Polygon) group.removeLayer(layer);
                        });
                    });
                }
                deletePolygonJs('basic-survey');
                if (state.polygon.length >= 3)
                    drawPolygonJs('basic-survey', state.polygon, {color: '#218358'});
                deletePolyLineJs('basic-route');
                if (state.route.length)
                    drawPolyLineJs('basic-route', state.route, {color: '#2563eb'});
                if (state.position) {
                    if (markers['basic-uav'])
                        moveMarkerJs('basic-uav', state.position[0], state.position[1]);
                    else
                        addMarkerJs('basic-uav', state.position[0], state.position[1],
                                    {title: 'UAV', draggable: false});
                } else if (markers['basic-uav']) {
                    deleteMarkerJs('basic-uav');
                }
                if (state.fit) {
                    const points = state.route.length ? state.route : state.polygon;
                    const bounds = L.latLngBounds(points);
                    map.invalidateSize();
                    if (bounds.isValid()) map.fitBounds(bounds.pad(0.15), {animate: false, maxZoom: 19});
                }
            })(''' + payload + ');')
        self._state['fit'] = False
        self._last_rendered = json.dumps(self._state, allow_nan=False)
