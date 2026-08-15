"""Chibi-proportioned cuboid geometry with per-face Minecraft UVs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .uv_tables import FACE_NAMES, FaceTable, PartTable


@dataclass(frozen=True, slots=True)
class MeshData:
    name: str
    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray
    uv: np.ndarray
    pivot: tuple[float, float, float]
    rotation_degrees: float
    is_overlay: bool

    @property
    def transform(self) -> np.ndarray:
        angle = np.deg2rad(self.rotation_degrees)
        cosine = float(np.cos(angle))
        sine = float(np.sin(angle))
        matrix = np.eye(4, dtype=np.float64)
        matrix[:3, :3] = (
            (cosine, -sine, 0.0),
            (sine, cosine, 0.0),
            (0.0, 0.0, 1.0),
        )
        matrix[:3, 3] = self.pivot
        return matrix


@dataclass(frozen=True, slots=True)
class PartSpec:
    name: str
    size: tuple[float, float, float]
    pivot: tuple[float, float, float]
    local_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_degrees: float = 0.0


# X points toward the character's left, Y points up, Z points forward.
# The 2.4-unit head makes the silhouette deliberately chibi rather than the
# standard Minecraft 8:12:12 proportions.
LEGACY_PARTS = (
    PartSpec("Head", (2.40, 2.40, 2.40), (0.0, 3.05, 0.0)),
    PartSpec("Body", (1.55, 1.55, 0.78), (0.0, 1.08, 0.0)),
    PartSpec("Arm.L", (0.58, 1.45, 0.62), (1.10, 1.12, 0.0)),
    PartSpec("Arm.R", (0.58, 1.45, 0.62), (-1.10, 1.12, 0.0)),
    PartSpec("Leg.L", (0.68, 0.90, 0.70), (0.39, -0.15, 0.0)),
    PartSpec("Leg.R", (0.68, 0.90, 0.70), (-0.39, -0.15, 0.0)),
)


FACE_NORMALS = {
    "top": (0.0, 1.0, 0.0),
    "bottom": (0.0, -1.0, 0.0),
    "right": (-1.0, 0.0, 0.0),
    "front": (0.0, 0.0, 1.0),
    "left": (1.0, 0.0, 0.0),
    "back": (0.0, 0.0, -1.0),
}

REFERENCE_CHIBI = "Reference Chibi"
LEGACY = "Legacy"
ProportionPreset = Literal["Reference Chibi", "Legacy"]
PROPORTION_PRESETS = (REFERENCE_CHIBI, LEGACY)

SHOULDER_OVERLAP = 0.0075
ARM_ANGLE_DEGREES = 5.0
REFERENCE_HEAD_OVERLAY_MARGIN = 0.03125
REFERENCE_PART_OVERLAY_MARGIN = 0.015625
LEGACY_HEAD_OVERLAY_MARGIN = 0.070
LEGACY_PART_OVERLAY_MARGIN = 0.025


def _reference_parts(arm_width: int) -> tuple[PartSpec, ...]:
    arm_size = 0.1875 if arm_width == 3 else 0.25
    body_half_width = 0.5 / 2.0
    arm_half_width = arm_size / 2.0
    arm_center_x = body_half_width + arm_half_width - SHOULDER_OVERLAP
    shoulder_x = arm_center_x - arm_half_width

    return (
        PartSpec("Head", (1.0, 1.0, 1.0), (0.0, 1.5, 0.0)),
        PartSpec("Body", (0.5, 0.5, 0.25), (0.0, 0.75, 0.0)),
        PartSpec(
            "Arm.L",
            (arm_size, 0.5, 0.25),
            (shoulder_x, 1.0, 0.0),
            (arm_half_width, -0.25, 0.0),
            ARM_ANGLE_DEGREES,
        ),
        PartSpec(
            "Arm.R",
            (arm_size, 0.5, 0.25),
            (-shoulder_x, 1.0, 0.0),
            (-arm_half_width, -0.25, 0.0),
            -ARM_ANGLE_DEGREES,
        ),
        PartSpec("Leg.L", (0.25, 0.5, 0.25), (0.125, 0.25, 0.0)),
        PartSpec("Leg.R", (0.25, 0.5, 0.25), (-0.125, 0.25, 0.0)),
    )


def _face_vertices(
    size: tuple[float, float, float],
    local_center: tuple[float, float, float],
) -> dict[str, tuple[tuple[float, float, float], ...]]:
    sx, sy, sz = (dimension / 2.0 for dimension in size)
    cx, cy, cz = local_center

    def point(x: float, y: float, z: float) -> tuple[float, float, float]:
        return (cx + x, cy + y, cz + z)

    # Each tuple is texture TL, TR, BR, BL as seen from outside the cuboid.
    return {
        "front": (
            point(-sx, sy, sz), point(sx, sy, sz),
            point(sx, -sy, sz), point(-sx, -sy, sz),
        ),
        "back": (
            point(sx, sy, -sz), point(-sx, sy, -sz),
            point(-sx, -sy, -sz), point(sx, -sy, -sz),
        ),
        "left": (
            point(sx, sy, sz), point(sx, sy, -sz),
            point(sx, -sy, -sz), point(sx, -sy, sz),
        ),
        "right": (
            point(-sx, sy, -sz), point(-sx, sy, sz),
            point(-sx, -sy, sz), point(-sx, -sy, -sz),
        ),
        "top": (
            point(-sx, sy, -sz), point(sx, sy, -sz),
            point(sx, sy, sz), point(-sx, sy, sz),
        ),
        "bottom": (
            point(-sx, -sy, sz), point(sx, -sy, sz),
            point(sx, -sy, -sz), point(-sx, -sy, -sz),
        ),
    }


def create_box_mesh(
    name: str,
    size: tuple[float, float, float],
    pivot: tuple[float, float, float],
    face_uv: FaceTable,
    *,
    local_center: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation_degrees: float = 0.0,
    is_overlay: bool = False,
) -> MeshData:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    normals: list[tuple[float, float, float]] = []
    uv: list[tuple[float, float]] = []
    by_face = _face_vertices(size, local_center)

    for face_name in FACE_NAMES:
        start = len(vertices)
        vertices.extend(by_face[face_name])
        normals.extend((FACE_NORMALS[face_name],) * 4)
        corners = face_uv[face_name].normalized_corners()
        if face_name == "bottom" and name in ("Head", "Head_Overlay"):
            # Flip only V so the texture's rear edge remains at the back.
            corners = (corners[3], corners[2], corners[1], corners[0])
        uv.extend(corners)
        # Input points run clockwise from an outside view, so reverse each
        # triangle to produce outward glTF normals.
        faces.extend(((start, start + 2, start + 1), (start, start + 3, start + 2)))

    return MeshData(
        name=name,
        vertices=np.asarray(vertices, dtype=np.float32),
        faces=np.asarray(faces, dtype=np.uint32),
        normals=np.asarray(normals, dtype=np.float32),
        uv=np.asarray(uv, dtype=np.float32),
        pivot=pivot,
        rotation_degrees=rotation_degrees,
        is_overlay=is_overlay,
    )


def build_chibi_meshes(
    uv_tables: PartTable,
    arm_width: int,
    proportions: ProportionPreset = REFERENCE_CHIBI,
) -> list[MeshData]:
    if arm_width not in (3, 4):
        raise ValueError("Arm width must be 3 (Alex) or 4 (Steve).")
    if proportions not in PROPORTION_PRESETS:
        raise ValueError(f"Unknown proportions preset: {proportions}")

    if proportions == REFERENCE_CHIBI:
        parts = _reference_parts(arm_width)
        head_overlay_margin = REFERENCE_HEAD_OVERLAY_MARGIN
        part_overlay_margin = REFERENCE_PART_OVERLAY_MARGIN
    else:
        parts = LEGACY_PARTS
        head_overlay_margin = LEGACY_HEAD_OVERLAY_MARGIN
        part_overlay_margin = LEGACY_PART_OVERLAY_MARGIN

    meshes: list[MeshData] = []
    for spec in parts:
        size = spec.size
        if proportions == LEGACY and spec.name.startswith("Arm") and arm_width == 3:
            size = (size[0] * 0.78, size[1], size[2])

        meshes.append(
            create_box_mesh(
                spec.name,
                size,
                spec.pivot,
                uv_tables[spec.name],
                local_center=spec.local_center,
                rotation_degrees=spec.rotation_degrees,
            )
        )

        overlay_name = (
            "Head_Overlay" if spec.name == "Head" else
            "Body_Overlay" if spec.name == "Body" else
            spec.name.replace("Arm.", "Arm_Overlay.").replace("Leg.", "Leg_Overlay.")
        )
        overlay_margin = head_overlay_margin if spec.name == "Head" else part_overlay_margin
        overlay_size = tuple(dimension + 2.0 * overlay_margin for dimension in size)
        meshes.append(
            create_box_mesh(
                overlay_name,
                overlay_size,
                spec.pivot,
                uv_tables[overlay_name],
                local_center=spec.local_center,
                rotation_degrees=spec.rotation_degrees,
                is_overlay=True,
            )
        )
    return meshes
