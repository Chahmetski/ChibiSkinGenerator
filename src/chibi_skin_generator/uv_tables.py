"""Canonical 64x64 Minecraft skin UV rectangles.

Coordinates use the PNG convention: origin at the image's top-left, X to the
right, Y down. Geometry converts these rectangles to glTF UV coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Mapping

TEXTURE_SIZE = 64
FACE_NAMES = ("top", "bottom", "right", "front", "left", "back")


@dataclass(frozen=True, slots=True)
class UVRect:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def normalized_corners(self) -> tuple[tuple[float, float], ...]:
        """Return inset TL, TR, BR, BL corners for trimesh/glTF UVs.

        Coordinates point at the centers of the boundary texels. This avoids
        sampling a neighbouring Minecraft face even with nearest filtering.
        The PNG Y axis is inverted because trimesh UV V points upward.
        """
        left = (self.x0 + 0.5) / TEXTURE_SIZE
        right = (self.x1 - 0.5) / TEXTURE_SIZE
        top = 1.0 - (self.y0 + 0.5) / TEXTURE_SIZE
        bottom = 1.0 - (self.y1 - 0.5) / TEXTURE_SIZE
        return (
            (left, top),
            (right, top),
            (right, bottom),
            (left, bottom),
        )


FaceTable = Mapping[str, UVRect]
PartTable = Mapping[str, FaceTable]


def cuboid_uv(u: int, v: int, width: int, height: int, depth: int) -> FaceTable:
    """Build the standard Minecraft cuboid net rooted at ``(u, v)``."""
    faces = {
        "top": UVRect(u + depth, v, u + depth + width, v + depth),
        "bottom": UVRect(u + depth + width, v, u + depth + 2 * width, v + depth),
        "right": UVRect(u, v + depth, u + depth, v + depth + height),
        "front": UVRect(u + depth, v + depth, u + depth + width, v + depth + height),
        "left": UVRect(
            u + depth + width,
            v + depth,
            u + 2 * depth + width,
            v + depth + height,
        ),
        "back": UVRect(
            u + 2 * depth + width,
            v + depth,
            u + 2 * depth + 2 * width,
            v + depth + height,
        ),
    }
    for rect in faces.values():
        if not (0 <= rect.x0 < rect.x1 <= TEXTURE_SIZE):
            raise ValueError(f"UV X coordinates are outside 64x64: {rect}")
        if not (0 <= rect.y0 < rect.y1 <= TEXTURE_SIZE):
            raise ValueError(f"UV Y coordinates are outside 64x64: {rect}")
    return MappingProxyType(faces)


@lru_cache(maxsize=2)
def uv_table(arm_width: int) -> PartTable:
    """Return UV rectangles for Steve (4) or Alex (3) arm width."""
    if arm_width not in (3, 4):
        raise ValueError("Arm width must be 3 (Alex) or 4 (Steve).")

    table = {
        "Head": cuboid_uv(0, 0, 8, 8, 8),
        "Head_Overlay": cuboid_uv(32, 0, 8, 8, 8),
        "Body": cuboid_uv(16, 16, 8, 12, 4),
        "Body_Overlay": cuboid_uv(16, 32, 8, 12, 4),
        "Arm.R": cuboid_uv(40, 16, arm_width, 12, 4),
        "Arm_Overlay.R": cuboid_uv(40, 32, arm_width, 12, 4),
        "Arm.L": cuboid_uv(32, 48, arm_width, 12, 4),
        "Arm_Overlay.L": cuboid_uv(48, 48, arm_width, 12, 4),
        "Leg.R": cuboid_uv(0, 16, 4, 12, 4),
        "Leg_Overlay.R": cuboid_uv(0, 32, 4, 12, 4),
        "Leg.L": cuboid_uv(16, 48, 4, 12, 4),
        "Leg_Overlay.L": cuboid_uv(0, 48, 4, 12, 4),
    }
    return MappingProxyType(table)
