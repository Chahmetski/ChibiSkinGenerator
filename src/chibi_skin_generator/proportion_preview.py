"""Lightweight front/side schematic preview for proportion settings."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from .proportions import PartPlacement, ProportionSettings, calculate_proportions


class ProportionPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = ProportionSettings()
        self._arm_pixels = 4
        self.setMinimumSize(420, 440)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_settings(self, settings: ProportionSettings) -> None:
        self._settings = settings
        self.update()

    def set_arm_pixels(self, arm_pixels: int) -> None:
        self._arm_pixels = 3 if arm_pixels == 3 else 4
        self.update()

    @staticmethod
    def _corners(part: PartPlacement, margin: float = 0.0) -> list[tuple[float, float, float]]:
        sx = part.size[0] / 2.0 + margin
        sy = part.size[1] / 2.0 + margin
        sz = part.size[2] / 2.0 + margin
        cx, cy, cz = part.local_center
        angle = math.radians(part.rotation_degrees)
        cosine, sine = math.cos(angle), math.sin(angle)
        points = []
        for x in (-sx, sx):
            for y in (-sy, sy):
                for z in (-sz, sz):
                    local_x, local_y = cx + x, cy + y
                    world_x = cosine * local_x - sine * local_y + part.pivot[0]
                    world_y = sine * local_x + cosine * local_y + part.pivot[1]
                    points.append((world_x, world_y, cz + z + part.pivot[2]))
        return points

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#171b22"))

        layout = calculate_proportions(self._settings, self._arm_pixels)
        all_points = [
            point
            for part in layout.parts
            for point in self._corners(part, part.overlay_offset)
        ]
        max_x = max(abs(point[0]) for point in all_points)
        max_z = max(abs(point[2]) for point in all_points)
        model_height = max(layout.total_height, max(point[1] for point in all_points))

        margin = 32.0
        view_width = (self.width() - margin * 3.0) / 2.0
        usable_height = max(80.0, self.height() - 90.0)
        horizontal_span = max(max_x * 2.0, max_z * 2.0, 0.5)
        scale = min(view_width / (horizontal_span * 1.15), usable_height / (model_height * 1.08))
        ground_y = (self.height() + model_height * scale) / 2.0
        front_center = margin + view_width / 2.0
        side_center = margin * 2.0 + view_width * 1.5

        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#dbe4f0"))
        painter.drawText(QRectF(margin, 8, view_width, 24), Qt.AlignmentFlag.AlignCenter, "Front")
        painter.drawText(
            QRectF(margin * 2 + view_width, 8, view_width, 24),
            Qt.AlignmentFlag.AlignCenter,
            "Side",
        )

        ground_pen = QPen(QColor("#778397"), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(ground_pen)
        painter.drawLine(QPointF(margin, ground_y), QPointF(margin + view_width, ground_y))
        painter.drawLine(
            QPointF(margin * 2 + view_width, ground_y),
            QPointF(margin * 2 + view_width * 2, ground_y),
        )

        colors = {
            "Head": QColor("#72a7ff"),
            "Body": QColor("#65c89b"),
            "Arm": QColor("#f0b25b"),
            "Leg": QColor("#c985e8"),
        }
        for part in layout.parts:
            category = "Arm" if part.name.startswith("Arm") else "Leg" if part.name.startswith("Leg") else part.name
            color = colors[category]
            self._draw_part(painter, part, color, front_center, ground_y, scale, "front")
            self._draw_part(painter, part, color, side_center, ground_y, scale, "side")

        point_pen = QPen(QColor("#ff6b75"), 1.5)
        painter.setPen(point_pen)
        painter.setBrush(QColor("#ff6b75"))
        for x, y in (*layout.shoulder_points, *layout.leg_connections):
            painter.drawEllipse(QPointF(front_center + x * scale, ground_y - y * scale), 3.0, 3.0)

        painter.setPen(QColor("#dbe4f0"))
        painter.drawText(QRectF(0, self.height()-54, self.width(), 22),
                         Qt.AlignmentFlag.AlignCenter, "Head · body · arms · legs; red dots mark joints")
        painter.drawText(
            QRectF(0, self.height() - 30, self.width(), 22),
            Qt.AlignmentFlag.AlignCenter,
            f"Height: {layout.total_height:.3f}",
        )

    def _draw_part(
        self,
        painter: QPainter,
        part: PartPlacement,
        color: QColor,
        center_x: float,
        ground_y: float,
        scale: float,
        view: str,
    ) -> None:
        base = self._corners(part)
        overlay = self._corners(part, part.overlay_offset)

        if view == "front":
            angle = math.radians(part.rotation_degrees)
            cosine, sine = math.cos(angle), math.sin(angle)
            cx, cy, _ = part.local_center
            def front_polygon(margin: float) -> QPolygonF:
                sx = part.size[0] / 2.0 + margin
                sy = part.size[1] / 2.0 + margin
                polygon = QPolygonF()
                for x, y in ((-sx, sy), (sx, sy), (sx, -sy), (-sx, -sy)):
                    local_x, local_y = cx + x, cy + y
                    world_x = cosine * local_x - sine * local_y + part.pivot[0]
                    world_y = sine * local_x + cosine * local_y + part.pivot[1]
                    polygon.append(
                        QPointF(center_x + world_x * scale, ground_y - world_y * scale)
                    )
                return polygon

            painter.setPen(QPen(color.lighter(130), 1.0))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 155))
            painter.drawPolygon(front_polygon(0.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color.lighter(170), 1.0, Qt.PenStyle.DashLine))
            painter.drawPolygon(front_polygon(part.overlay_offset))
            return
        else:
            minimum_z = min(point[2] for point in base)
            maximum_z = max(point[2] for point in base)
            minimum_y = min(point[1] for point in base)
            maximum_y = max(point[1] for point in base)
            rect = QRectF(
                center_x + minimum_z * scale,
                ground_y - maximum_y * scale,
                (maximum_z - minimum_z) * scale,
                (maximum_y - minimum_y) * scale,
            )
            painter.setPen(QPen(color.lighter(130), 1.0))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 155))
            painter.drawRect(rect)
            horizontal = 2

        minimum_h = min(point[horizontal] for point in overlay)
        maximum_h = max(point[horizontal] for point in overlay)
        minimum_y = min(point[1] for point in overlay)
        maximum_y = max(point[1] for point in overlay)
        overlay_rect = QRectF(
            center_x + minimum_h * scale,
            ground_y - maximum_y * scale,
            (maximum_h - minimum_h) * scale,
            (maximum_y - minimum_y) * scale,
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color.lighter(170), 1.0, Qt.PenStyle.DashLine))
        painter.drawRect(overlay_rect)
