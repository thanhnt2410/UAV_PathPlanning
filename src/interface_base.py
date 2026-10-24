"""A deliberately small GUI example, written directly in Python."""
from PyQt5 import QtCore, QtWidgets

from interface_map import Map


class Interface(QtWidgets.QMainWindow):
    close_requested = QtCore.pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self._allow_close = False
        self.setWindowTitle('SW-UAV basic — one UAV')
        self.resize(1150, 760)
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.addWidget(QtWidgets.QLabel('Polygon: latitude,longitude per line'))
        self.vertices = QtWidgets.QPlainTextEdit()
        self.vertices.setMaximumHeight(150)
        layout.addWidget(self.vertices)
        form = QtWidgets.QFormLayout()
        self.spacing = QtWidgets.QDoubleSpinBox()
        self.spacing.setRange(1, config.planning['max_radius_m'])
        self.spacing.setValue(config.planning['spacing_m'])
        self.altitude = QtWidgets.QDoubleSpinBox()
        self.altitude.setRange(1, config.planning['max_altitude_m'])
        self.altitude.setValue(config.planning['altitude_m'])
        form.addRow('Spacing (m)', self.spacing)
        form.addRow('Altitude AGL (m)', self.altitude)
        self.footprint = QtWidgets.QDoubleSpinBox()
        self.footprint.setRange(0.1, config.planning['max_radius_m'] * 2)
        self.footprint.setValue(config.analysis['footprint_width_m'])
        self.footprint.setToolTip('Full sensor swath width at the selected altitude; configure for your camera.')
        form.addRow('Footprint width (m)', self.footprint)
        layout.addLayout(form)
        self.buttons = {}
        buttons = QtWidgets.QGridLayout()
        labels = ('Connect', 'Plan', 'Clear polygon', 'Load CSV', 'Save CSV', 'Upload',
                  'Arm', 'Disarm', 'Takeoff', 'Start / Resume', 'Pause', 'RTL', 'Land')
        for index, label in enumerate(labels):
            button = QtWidgets.QPushButton(label)
            buttons.addWidget(button, index // 2, index % 2)
            self.buttons[label] = button
        layout.addLayout(buttons)
        layout.addWidget(QtWidgets.QLabel('Flight: Upload → Arm → Takeoff → Start'))
        self.telemetry = QtWidgets.QLabel('Disconnected')
        self.telemetry.setWordWrap(True)
        layout.addWidget(self.telemetry)
        self.messages = QtWidgets.QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumBlockCount(200)
        layout.addWidget(self.messages)
        self.map = Map(html_path=config.map_html)
        self.result_columns = [
            ('Algorithm', None, 0), ('Distance (m)', 'distance_m', 1),
            ('Turns', 'turns', 0), ('Cost', 'cost', 1),
            ('Time est. (s)', 'predicted_time_s', 1), ('Energy est. (Wh)', 'predicted_energy_wh', 3),
            ('Score', 'score', 1), ('Waypoints', 'waypoint_count', 0),
            ('Coverage (%)', 'coverage_percent', 1), ('Overlap (%)', 'overlap_percent', 1),
            ('Swept (m²)', 'swept_area_m2', 1), ('Plan (ms)', 'planning_time_ms', 2),
        ]
        self.results = QtWidgets.QTableWidget(0, len(self.result_columns))
        self.results.setHorizontalHeaderLabels([name for name, _, _ in self.result_columns])
        self.results.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.results.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.results.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.results.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.addWidget(QtWidgets.QLabel('Bản đồ GPS · Ảnh vệ tinh'))
        comparison = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        comparison.addWidget(self.map)
        comparison.addWidget(self.results)
        comparison.setSizes([520, 180])
        right_layout.addWidget(comparison)
        note = QtWidgets.QLabel('Select a result row to preview/use its route. Energy/time are regression estimates, not measurements.')
        note.setWordWrap(True)
        right_layout.addWidget(note)
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(panel)
        splitter.addWidget(right)
        splitter.setSizes([350, 800])
        self.setCentralWidget(splitter)

    def show_results(self, results):
        self.results.blockSignals(True)
        try:
            self.results.clearSelection()
            self.results.setRowCount(len(results))
            for row, result in enumerate(results):
                for column, (_, key, decimals) in enumerate(self.result_columns):
                    value = result.algorithm if key is None else result.metrics.get(key)
                    text = value if isinstance(value, str) else ('N/A' if value is None else f'{value:.{decimals}f}')
                    item = QtWidgets.QTableWidgetItem(text)
                    item.setToolTip(result.error or result.energy_error)
                    self.results.setItem(row, column, item)
        finally:
            self.results.blockSignals(False)

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        else:
            event.ignore()
            self.close_requested.emit()
