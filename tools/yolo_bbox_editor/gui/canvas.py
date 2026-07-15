"""Canvas — QGraphicsView-based image viewer with draggable YOLO bounding boxes."""

from __future__ import annotations
from typing import Callable
import math

import cv2
from PySide6.QtCore import (
    Qt, QRectF, QPointF, QSizeF, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QPen, QPixmap, QImage, QPainter,
    QCursor, QTransform, QFont,
)
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsItem, QGraphicsPixmapItem, QApplication,
    QGraphicsSimpleTextItem, QSizePolicy,
)

from core.yolo_io import YOLOLabel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASS_COLORS = [
    QColor(255, 80, 80),
    QColor(80, 255, 80),
    QColor(80, 80, 255),
    QColor(255, 255, 80),
    QColor(255, 80, 255),
    QColor(80, 255, 255),
    QColor(255, 160, 80),
    QColor(160, 80, 255),
    QColor(80, 255, 160),
    QColor(255, 200, 80),
]

SELECTED_PEN = QPen(QColor(0, 200, 255), 2.5, Qt.SolidLine)
HOVER_PEN = QPen(QColor(255, 255, 255, 180), 2.5, Qt.SolidLine)
EDGE_MARGIN = 8.0  # scene pixels from edge to trigger resize cursor


class BBoxItem(QGraphicsRectItem):
    """A single YOLO bounding box on the scene. Resize via edge dragging."""

    def __init__(self, class_id: int, class_names: dict[int, str] | None = None):
        super().__init__()
        self._class_id = class_id
        self._class_names = class_names or {}
        self._active_edge: str | None = None  # 'L','R','T','B','TL','TR','BL','BR'
        self._resize_start_rect: QRectF | None = None
        self._resize_start_pos: QPointF | None = None
        self._change_callback: Callable[[], None] | None = None
        self._dragging = False  # True while being moved (not resized)

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        self._label = QGraphicsSimpleTextItem(self)
        self._label.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self._label.setAcceptedMouseButtons(Qt.NoButton)
        self._label.setBrush(QColor(255, 255, 255))
        font = QFont("Segoe UI", 10, QFont.Bold)
        self._label.setFont(font)
        self._label_bg = QGraphicsRectItem(self)
        self._label_bg.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self._label_bg.setAcceptedMouseButtons(Qt.NoButton)
        self._label_bg.setPen(Qt.NoPen)
        self._label_bg.setBrush(QBrush(QColor(0, 0, 0, 160)))
        self._label_bg.setZValue(self._label.zValue() - 0.1)

        self._update_pen()

    # ---- pen / label ----

    def _update_pen(self):
        base_color = CLASS_COLORS[self._class_id % len(CLASS_COLORS)]
        pen = QPen(base_color, 2.0, Qt.SolidLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(base_color.red(), base_color.green(),
                                    base_color.blue(), 30)))
        self._update_label()

    def _update_label(self):
        name = self._class_names.get(self._class_id, f"cls {self._class_id}")
        self._label.setText(name)
        r = self.rect()
        br = self._label.boundingRect()
        self._label.setPos(r.left() + 2, r.top() - br.height() - 2)
        self._label_bg.setRect(br.adjusted(-3, -2, 3, 2))
        self._label_bg.setPos(self._label.pos())

    # ---- properties ----

    @property
    def class_id(self) -> int:
        return self._class_id

    @class_id.setter
    def class_id(self, val: int):
        self._class_id = val
        self._update_pen()

    def yolo_label(self, img_w: int, img_h: int) -> YOLOLabel:
        r = self.rect()
        return YOLOLabel(
            class_id=self._class_id,
            x_center=r.center().x() / img_w,
            y_center=r.center().y() / img_h,
            width=r.width() / img_w,
            height=r.height() / img_h,
        )

    @classmethod
    def from_yolo(cls, label: YOLOLabel, img_w: int, img_h: int,
                  class_names: dict[int, str] | None = None) -> BBoxItem:
        w = label.width * img_w
        h = label.height * img_h
        x = label.x_center * img_w - w / 2
        y = label.y_center * img_h - h / 2
        item = cls(label.class_id, class_names)
        item.setRect(x, y, w, h)
        return item

    # ---- edge detection ----

    def _edge_at(self, scene_pos: QPointF) -> str | None:
        """Return which edge/corner the position is near, or None if inside center area."""
        r = self.rect()
        m = EDGE_MARGIN
        on_l = abs(scene_pos.x() - r.left()) < m
        on_r = abs(scene_pos.x() - r.right()) < m
        on_t = abs(scene_pos.y() - r.top()) < m
        on_b = abs(scene_pos.y() - r.bottom()) < m
        if on_t and on_l: return "TL"
        if on_t and on_r: return "TR"
        if on_b and on_l: return "BL"
        if on_b and on_r: return "BR"
        if on_l: return "L"
        if on_r: return "R"
        if on_t: return "T"
        if on_b: return "B"
        return None

    _EDGE_CURSORS = {
        "L": Qt.SizeHorCursor, "R": Qt.SizeHorCursor,
        "T": Qt.SizeVerCursor, "B": Qt.SizeVerCursor,
        "TL": Qt.SizeFDiagCursor, "BR": Qt.SizeFDiagCursor,
        "TR": Qt.SizeBDiagCursor, "BL": Qt.SizeBDiagCursor,
    }

    # ---- mouse events (edge resize + move) ----

    def hoverMoveEvent(self, event):
        if self.isSelected():
            edge = self._edge_at(event.scenePos())
            cursor = self._EDGE_CURSORS.get(edge, Qt.ArrowCursor)
            self.setCursor(QCursor(cursor))
        super().hoverMoveEvent(event)

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            pen = QPen(HOVER_PEN)
            pen.setCosmetic(True)
            self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self._update_pen()
        self.setCursor(QCursor(Qt.ArrowCursor))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        edge = self._edge_at(event.scenePos())
        if edge and self.isSelected():
            # Start resize
            self._active_edge = edge
            self._resize_start_rect = QRectF(self.rect())
            self._resize_start_pos = event.scenePos()
            # Temporarily disable built-in move
            self.setFlag(QGraphicsItem.ItemIsMovable, False)
            event.accept()
        else:
            # Normal move/select — single selection (no Ctrl = deselect others)
            scene = self.scene()
            if scene and not (event.modifiers() & Qt.ControlModifier):
                for other in scene.selectedItems():
                    if other is not self:
                        other.setSelected(False)
            self.setSelected(True)
            self._dragging = True
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._active_edge and self._resize_start_rect and self._resize_start_pos:
            delta = event.scenePos() - self._resize_start_pos
            self._apply_edge_resize(delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._active_edge:
                self._active_edge = None
                self._resize_start_rect = None
                self._resize_start_pos = None
                self.setFlag(QGraphicsItem.ItemIsMovable, True)
                self._notify_change()
                event.accept()
                return
            if self._dragging:
                self._dragging = False
                self._notify_change()
        super().mouseReleaseEvent(event)

    def _apply_edge_resize(self, delta: QPointF):
        r = QRectF(self._resize_start_rect)
        dx, dy = delta.x(), delta.y()
        edge = self._active_edge

        if "L" in edge:
            r.setLeft(min(r.left() + dx, r.right() - 5))
        if "R" in edge:
            r.setRight(max(r.right() + dx, r.left() + 5))
        if "T" in edge:
            r.setTop(min(r.top() + dy, r.bottom() - 5))
        if "B" in edge:
            r.setBottom(max(r.bottom() + dy, r.top() + 5))

        self.setRect(r.normalized())
        self._update_label()

    # ---- paint handles ----

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.save()
            # Draw handle squares at corners/edges (in device coords for constant size)
            r = self.rect()
            s = 6  # handle half-size in device pixels
            # Convert scene points to view coords for drawing
            painter.setBrush(QBrush(QColor(0, 200, 255)))
            painter.setPen(Qt.NoPen)
            # Disable cosmetic pen for fill
            corners = [
                r.topLeft(), QPointF(r.center().x(), r.top()),
                r.topRight(), QPointF(r.right(), r.center().y()),
                r.bottomRight(), QPointF(r.center().x(), r.bottom()),
                r.bottomLeft(), QPointF(r.left(), r.center().y()),
            ]
            for pt in corners:
                painter.drawRect(QRectF(pt.x() - s, pt.y() - s, s * 2, s * 2))
            painter.restore()

    # ---- selection ----

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedChange:
            if value:
                pen = QPen(SELECTED_PEN)
                pen.setCosmetic(True)
                self.setPen(pen)
            else:
                self._active_edge = None
                self._update_pen()
        elif change == QGraphicsItem.ItemPositionChange:
            scene = self.scene()
            if scene:
                sr = scene.sceneRect()
                r = self.rect()
                x = max(0.0, min(value.x(), sr.width() - r.width()))
                y = max(0.0, min(value.y(), sr.height() - r.height()))
                return QPointF(x, y)
        return super().itemChange(change, value)

    def _notify_change(self):
        self._update_label()
        if self._change_callback:
            self._change_callback()


# ---------------------------------------------------------------------------
# Canvas (QGraphicsView)
# ---------------------------------------------------------------------------

class Canvas(QGraphicsView):
    """Zoomable, pannable image canvas with bounding box editing."""

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    bbox_added = Signal(int)  # class_id — ask user for class after drawing
    changes_made = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # Rendering
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)

        # State
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._image_path: str = ""
        self._panning = False
        self._last_pan_pos = QPointF()
        self._drawing_bbox = False
        self._draw_start = QPointF()
        self._draw_rect_item: QGraphicsRectItem | None = None
        self._bboxes: list[BBoxItem] = []
        self._class_names: dict[int, str] = {}
        self._zoom_level = 1.0
        self._is_space_held = False

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(100, 100)

    def sizeHint(self):
        """Prevent QGraphicsView from reporting scene size as preferred size."""
        return QSizeF(640, 480).toSize()

    # ===================================================================
    # Public API
    # ===================================================================

    def set_class_names(self, names: dict[int, str]):
        self._class_names = names

    def load_image(self, path: str, labels: list[YOLOLabel]) -> None:
        """Load an image and populate the scene with bounding boxes."""
        # Disconnect old items first
        for b in self._bboxes:
            b._change_callback = None
        self._bboxes.clear()
        self._scene.clear()
        self._pixmap_item = None

        # Load via OpenCV, convert to QPixmap
        mat = cv2.imread(path, cv2.IMREAD_COLOR)
        if mat is None:
            raise FileNotFoundError(f"Cannot read image: {path}")
        mat = cv2.cvtColor(mat, cv2.COLOR_BGR2RGB)
        h, w, _ = mat.shape
        qimg = QImage(mat.data, w, h, w * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(0, 0, w, h)
        self._image_path = path

        # Create bbox items
        for lbl in labels:
            item = BBoxItem.from_yolo(lbl, w, h, self._class_names)
            item._change_callback = self._on_bbox_changed
            self._scene.addItem(item)
            self._bboxes.append(item)

        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_level = self._calc_zoom()

    def bboxes_as_labels(self) -> list[YOLOLabel]:
        """Export current bounding boxes as YOLO labels (normalized)."""
        sr = self._scene.sceneRect()
        w, h = sr.width(), sr.height()
        return [b.yolo_label(w, h) for b in self._bboxes]

    def delete_selected(self) -> None:
        for item in list(self._scene.selectedItems()):
            if isinstance(item, BBoxItem):
                self._bboxes.remove(item)
                self._scene.removeItem(item)
        self.changes_made.emit()

    def delete_all(self) -> None:
        """Remove all bounding boxes from the current image."""
        for b in list(self._bboxes):
            self._scene.removeItem(b)
        self._bboxes.clear()
        self.changes_made.emit()

    def set_class_for_selected(self, class_id: int) -> None:
        for item in self._scene.selectedItems():
            if isinstance(item, BBoxItem):
                item.class_id = class_id
        self.changes_made.emit()

    def fit_to_window(self):
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_level = self._calc_zoom()

    def zoom_100(self):
        self.resetTransform()
        self._zoom_level = 1.0

    def zoom_in(self):
        self.scale(1.15, 1.15)
        self._zoom_level = self._calc_zoom()

    def zoom_out(self):
        self.scale(1 / 1.15, 1 / 1.15)
        self._zoom_level = self._calc_zoom()

    @property
    def zoom_level(self) -> float:
        return self._zoom_level

    # ===================================================================
    # Internal
    # ===================================================================

    def _calc_zoom(self) -> float:
        t = self.transform()
        return math.sqrt(abs(t.m11() * t.m22()))

    def _on_bbox_changed(self):
        self.changes_made.emit()

    def _current_class_id(self) -> int:
        """Default class for new boxes — copy from selected, else 0."""
        for item in self._scene.selectedItems():
            if isinstance(item, BBoxItem):
                return item.class_id
        return 0

    # ===================================================================
    # Mouse events (zoom, pan, draw, select)
    # ===================================================================

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            self.scale(factor, factor)
            self._zoom_level = self._calc_zoom()
        else:
            # Scroll vertically for pan
            pass
        event.accept()

    def mousePressEvent(self, event):
        # Panning: middle button anywhere, or Space+LMB anywhere
        space_pan = (
            event.button() == Qt.LeftButton
            and QApplication.keyboardModifiers() == Qt.NoModifier
            and self._is_space_held
        )
        if event.button() == Qt.MiddleButton or space_pan:
            self._panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        # Drawing: left button on empty area (no bbox underneath)
        if event.button() == Qt.LeftButton and not self._panning:
            item = self._scene.itemAt(self.mapToScene(event.pos()), QTransform())
            # Walk up to see if this is part of a BBoxItem
            while item is not None and not isinstance(item, (BBoxItem, QGraphicsPixmapItem)):
                item = item.parentItem()
            if item is None or isinstance(item, QGraphicsPixmapItem):
                self._scene.clearSelection()
                self._drawing_bbox = True
                self._draw_start = self.mapToScene(event.pos())
                self._draw_rect_item = self._scene.addRect(
                    QRectF(self._draw_start, QSizeF(0, 0)),
                    QPen(QColor(0, 200, 255), 2, Qt.DashLine),
                )
                self._draw_rect_item.setZValue(1000)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return

        if self._drawing_bbox and self._draw_rect_item:
            end = self.mapToScene(event.pos())
            rect = QRectF(self._draw_start, end).normalized()
            self._draw_rect_item.setRect(rect)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._drawing_bbox:
            self._drawing_bbox = False
            if self._draw_rect_item:
                r = self._draw_rect_item.rect()
                self._scene.removeItem(self._draw_rect_item)
                self._draw_rect_item = None
                # Only create bbox if it has meaningful size
                if r.width() > 5 and r.height() > 5:
                    cid = self._current_class_id()
                    item = BBoxItem(cid, self._class_names)
                    item.setRect(r)
                    item._change_callback = self._on_bbox_changed
                    self._scene.addItem(item)
                    self._bboxes.append(item)
                    item.setSelected(True)
                    self.changes_made.emit()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            self.delete_selected()
            event.accept()
            return

        if event.key() == Qt.Key_Escape:
            self._scene.clearSelection()
            event.accept()
            return

        # Space for panning
        if event.key() == Qt.Key_Space:
            self._is_space_held = True
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return

        # Digit keys for class change
        key_text = event.text()
        if key_text.isdigit():
            cid = int(key_text)
            self.set_class_for_selected(cid)
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._is_space_held = False
            if not self._panning:
                self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    # contextMenuEvent intentionally not overridden — right-click does nothing
