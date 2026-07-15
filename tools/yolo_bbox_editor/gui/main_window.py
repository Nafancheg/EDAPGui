"""Main window — toolbar, canvas, status bar, navigation."""

from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QFileDialog,
    QMessageBox, QLabel, QWidget, QVBoxLayout,
)

from core.yolo_io import scan_folder, read_labels, write_labels, ImageRecord
from gui.canvas import Canvas


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YOLO BBox Editor")
        self.resize(1280, 900)
        self.setMinimumSize(800, 500)

        # State
        self._records: list[ImageRecord] = []
        self._current_idx: int = -1

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Canvas
        self._canvas = Canvas()
        self._canvas.changes_made.connect(self._on_changes)
        layout.addWidget(self._canvas)

        # Toolbar
        self._toolbar = QToolBar("Main")
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)
        self._setup_toolbar()

        # Status bar — use QMainWindow's built-in one
        self._statusbar = self.statusBar()
        self._statusbar.setMinimumHeight(24)
        self._statusbar.setStyleSheet(
            "QStatusBar { border-top: 1px solid #aaa; background: #eee; }"
            "QStatusBar::item { border: none; }"
        )
        self._status_label = QLabel("No folder opened")
        self._status_label.setStyleSheet("color: #111; padding: 2px 8px;")
        self._statusbar.addPermanentWidget(self._status_label)

        # Navigation shortcuts
        self._setup_shortcuts()

    # ===================================================================
    # Toolbar
    # ===================================================================

    def _setup_toolbar(self):
        tb = self._toolbar

        self._act_open = QAction("Open Folder", self)
        self._act_open.triggered.connect(self._open_folder)
        tb.addAction(self._act_open)

        tb.addSeparator()

        self._act_prev = QAction("◀ Prev", self)
        self._act_prev.triggered.connect(self._go_prev)
        tb.addAction(self._act_prev)

        self._act_next = QAction("Next ▶", self)
        self._act_next.triggered.connect(self._go_next)
        tb.addAction(self._act_next)

        tb.addSeparator()

        self._act_save = QAction("Save", self)
        self._act_save.triggered.connect(self._save_current)
        tb.addAction(self._act_save)

        tb.addSeparator()

        self._act_del_all = QAction("Del All", self)
        self._act_del_all.triggered.connect(self._canvas.delete_all)
        tb.addAction(self._act_del_all)

        tb.addSeparator()

        self._act_fit = QAction("Fit", self)
        self._act_fit.triggered.connect(self._canvas.fit_to_window)
        tb.addAction(self._act_fit)

        self._act_100 = QAction("100%", self)
        self._act_100.triggered.connect(self._canvas.zoom_100)
        tb.addAction(self._act_100)

        self._act_zoom_in = QAction("Zoom +", self)
        self._act_zoom_in.triggered.connect(self._canvas.zoom_in)
        tb.addAction(self._act_zoom_in)

        self._act_zoom_out = QAction("Zoom -", self)
        self._act_zoom_out.triggered.connect(self._canvas.zoom_out)
        tb.addAction(self._act_zoom_out)

    # ===================================================================
    # Shortcuts
    # ===================================================================

    def _setup_shortcuts(self):
        # Navigation
        QAction("prev_key", self, shortcut=QKeySequence("A"),
                triggered=self._go_prev)
        QAction("next_key", self, shortcut=QKeySequence("D"),
                triggered=self._go_next)
        QAction("save_key", self, shortcut=QKeySequence("Ctrl+S"),
                triggered=self._save_current)

        # Canvas shortcuts (handled in Canvas.keyPressEvent):
        # Delete, Escape, Space, digits 0-9, Ctrl+Wheel

    # ===================================================================
    # File operations
    # ===================================================================

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Dataset Folder")
        if not folder:
            return

        records = scan_folder(Path(folder))
        if not records:
            QMessageBox.information(self, "No Images",
                                    "No supported images found in the folder.")
            return

        # Try to read class names from data.yaml one level up
        class_names = self._read_class_names(Path(folder))

        self._records = records
        self._current_idx = 0
        self._canvas.set_class_names(class_names)
        self._load_current()

    def _read_class_names(self, folder: Path) -> dict[int, str]:
        """Try to read class names from data.yaml (up to 3 levels up)."""
        for candidate in [
            folder / "data.yaml",
            folder.parent / "data.yaml",
            folder.parent.parent / "data.yaml",
        ]:
            if candidate.exists():
                return self._parse_yaml_names(candidate)
        return {}

    @staticmethod
    def _parse_yaml_names(yaml_path: Path) -> dict[int, str]:
        """Parse YOLO data.yaml names section. Handles both:
            names: ['core', 'jetcone']
            names: {0: core, 1: jetcone}
        """
        import re
        text = yaml_path.read_text(encoding="utf-8")
        # Extract names block
        m = re.search(r"names:\s*\[(.+?)\]", text, re.DOTALL)
        if m:
            # List format: ['core', 'jetcone']
            items = re.findall(r"['\"](.+?)['\"]", m.group(1))
            return {i: name for i, name in enumerate(items)}
        m = re.search(r"names:\s*\{(.+?)\}", text, re.DOTALL)
        if m:
            # Dict format: {0: core, 1: jetcone}
            pairs = re.findall(r"(\d+)\s*:\s*['\"]?(\w+)['\"]?", m.group(1))
            return {int(k): v for k, v in pairs}
        return {}

    def _load_current(self):
        if self._current_idx < 0 or self._current_idx >= len(self._records):
            return

        rec = self._records[self._current_idx]
        try:
            labels = read_labels(rec.label_path) if rec.label_path.exists() else []
            rec.labels = labels
            rec.dirty = False

            self._canvas.load_image(str(rec.image_path), labels)
            self._update_status()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Load Error",
                f"Failed to load:\n{rec.image_path}\n\n{e}")

    def _save_current(self):
        if self._current_idx < 0:
            return
        rec = self._records[self._current_idx]
        labels = self._canvas.bboxes_as_labels()
        rec.labels = labels
        write_labels(rec.label_path, labels)
        rec.dirty = False
        self._update_status()

    def _maybe_save_and_go(self, new_idx: int):
        """Save current if dirty, then navigate."""
        rec = self._records[self._current_idx] if 0 <= self._current_idx < len(self._records) else None
        if rec and rec.dirty:
            labels = self._canvas.bboxes_as_labels()
            rec.labels = labels
            write_labels(rec.label_path, labels)
            rec.dirty = False

        self._current_idx = new_idx
        self._load_current()

    # ===================================================================
    # Navigation
    # ===================================================================

    def _go_prev(self):
        if not self._records:
            return
        new_idx = max(0, self._current_idx - 1)
        if new_idx != self._current_idx:
            self._maybe_save_and_go(new_idx)

    def _go_next(self):
        if not self._records:
            return
        new_idx = min(len(self._records) - 1, self._current_idx + 1)
        if new_idx != self._current_idx:
            self._maybe_save_and_go(new_idx)

    # ===================================================================
    # Status
    # ===================================================================

    def _on_changes(self):
        if self._current_idx >= 0 and self._current_idx < len(self._records):
            self._records[self._current_idx].dirty = True
            self._update_status()

    def _update_status(self):
        if self._current_idx < 0 or not self._records:
            self._status_label.setText("No folder opened")
            return

        rec = self._records[self._current_idx]
        dirty_mark = " ●" if rec.dirty else ""
        self._status_label.setText(
            f"{self._current_idx + 1}/{len(self._records)}  "
            f"{rec.image_path.name}{dirty_mark}  "
            f"Zoom: {self._canvas.zoom_level:.0%}"
        )
