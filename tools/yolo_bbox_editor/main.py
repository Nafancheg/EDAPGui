"""YOLO BBox Editor — lightweight desktop tool for correcting YOLO bounding box labels."""

import sys
import logging
import traceback

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)

def excepthook(exc_type, exc_value, exc_tb):
    logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    traceback.print_exception(exc_type, exc_value, exc_tb)
sys.excepthook = excepthook
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtCore import Qt

from gui.main_window import MainWindow


def apply_light_theme(app: QApplication):
    """Clean light palette."""
    p = app.palette()
    p.setColor(QPalette.Window, QColor(245, 245, 245))
    p.setColor(QPalette.WindowText, QColor(30, 30, 30))
    p.setColor(QPalette.Base, QColor(255, 255, 255))
    p.setColor(QPalette.AlternateBase, QColor(240, 240, 240))
    p.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
    p.setColor(QPalette.ToolTipText, QColor(30, 30, 30))
    p.setColor(QPalette.Text, QColor(30, 30, 30))
    p.setColor(QPalette.Button, QColor(235, 235, 235))
    p.setColor(QPalette.ButtonText, QColor(30, 30, 30))
    p.setColor(QPalette.BrightText, QColor(200, 0, 0))
    p.setColor(QPalette.Link, QColor(0, 100, 200))
    p.setColor(QPalette.Highlight, QColor(0, 120, 215))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(p)
    app.setStyle("Fusion")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("YOLO BBox Editor")
    app.setOrganizationName("ED_Autopilot")

    apply_light_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
