"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from .ui import MainWindow


def main() -> int:
    application = QApplication(sys.argv)
    application.setOrganizationName("ChibiSkinGenerator")
    application.setApplicationName("ChibiSkinGenerator")
    application.setApplicationVersion(__version__)
    window = MainWindow()
    window.show()
    return application.exec()
