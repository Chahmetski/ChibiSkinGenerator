"""Print deterministic pre-rig rest-pose bounds for regression fixtures."""

from __future__ import annotations

import json

import numpy as np

from chibi_skin_generator.geometry import build_chibi_meshes
from chibi_skin_generator.proportions import builtin_preset_names, get_builtin_preset
from chibi_skin_generator.uv_tables import uv_table


def main() -> None:
    snapshots: dict[str, dict[str, list[float]]] = {}
    for preset_name in builtin_preset_names():
        for arm_pixels in (3, 4):
            meshes = build_chibi_meshes(
                uv_table(arm_pixels), arm_pixels, get_builtin_preset(preset_name)
            )
            world_parts = []
            for mesh in meshes:
                homogeneous = np.column_stack((mesh.vertices, np.ones(len(mesh.vertices))))
                world_parts.append((mesh.transform @ homogeneous.T).T[:, :3])
            points = np.vstack(world_parts)
            snapshots[f"{preset_name}|{arm_pixels}"] = {
                "min": [round(float(value), 7) for value in points.min(axis=0)],
                "max": [round(float(value), 7) for value in points.max(axis=0)],
            }
    print(json.dumps(snapshots, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
