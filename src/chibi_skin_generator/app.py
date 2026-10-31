"""Application entry point."""

from __future__ import annotations

import sys
import os

from PySide6.QtWidgets import QApplication

from . import __version__
from .ui import MainWindow


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from .diagnostics import run
        return run(sys.argv[2])
    application = QApplication(sys.argv)
    application.setOrganizationName("ChibiSkinGenerator")
    application.setApplicationName("ChibiSkinGenerator")
    application.setApplicationVersion(__version__)
    window = MainWindow()
    window.show()
    return application.exec()
