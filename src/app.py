"""Run the basic example: python src/app.py (no connection or arming on startup)."""
import asyncio
import os
import sys

os.environ.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '1')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')

from PyQt5 import QtCore, QtWidgets
from qasync import QEventLoop

from config_loader import ConfigLoader
from main_controller import MainController


def main():
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)
    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    controller = MainController(ConfigLoader())
    controller.view.show()
    with loop:
        loop.run_forever()


if __name__ == '__main__':
    main()
