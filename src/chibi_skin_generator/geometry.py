"""Chibi-proportioned cuboid geometry with per-face Minecraft UVs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .proportions import ProportionSettings, calculate_proportions
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


FACE_NORMALS = {
    "top": (0.0, 1.0, 0.0),
    "bottom": (0.0, -1.0, 0.0),
    "right": (-1.0, 0.0, 0.0),
    "front": (0.0, 0.0, 1.0),
    "left": (1.0, 0.0, 0.0),
    "back": (0.0, 0.0, -1.0),
}


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
    settings: ProportionSettings,
) -> list[MeshData]:
    layout = calculate_proportions(settings, arm_width)

    meshes: list[MeshData] = []
    for part in layout.parts:
        meshes.append(
            create_box_mesh(
                part.name,
                part.size,
                part.pivot,
                uv_tables[part.name],
                local_center=part.local_center,
                rotation_degrees=part.rotation_degrees,
            )
        )

        overlay_name = (
            "Head_Overlay" if part.name == "Head" else
            "Body_Overlay" if part.name == "Body" else
            part.name.replace("Arm.", "Arm_Overlay.").replace("Leg.", "Leg_Overlay.")
        )
        overlay_size = tuple(
            dimension + 2.0 * part.overlay_offset for dimension in part.size
        )
        meshes.append(
            create_box_mesh(
                overlay_name,
                overlay_size,
                part.pivot,
                uv_tables[overlay_name],
                local_center=part.local_center,
                rotation_degrees=part.rotation_degrees,
                is_overlay=True,
            )
        )
    return meshes
