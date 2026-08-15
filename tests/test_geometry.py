from __future__ import annotations

import numpy as np
import pytest

from chibi_skin_generator.geometry import (
    LEGACY,
    REFERENCE_CHIBI,
    SHOULDER_OVERLAP,
    MeshData,
    build_chibi_meshes,
)
from chibi_skin_generator.uv_tables import uv_table


def _world_vertices(mesh: MeshData) -> np.ndarray:
    homogeneous = np.column_stack((mesh.vertices, np.ones(len(mesh.vertices))))
    return (mesh.transform @ homogeneous.T).T[:, :3]


def _sorted_unique(points: np.ndarray) -> np.ndarray:
    rounded = np.unique(np.round(points, decimals=7), axis=0)
    order = np.lexsort((rounded[:, 2], rounded[:, 1], rounded[:, 0]))
    return rounded[order]


@pytest.mark.parametrize(("arm_width", "expected_arm_size"), ((4, 0.25), (3, 0.1875)))
def test_reference_chibi_proportions_and_shoulders(
    arm_width: int, expected_arm_size: float
) -> None:
    meshes = build_chibi_meshes(uv_table(arm_width), arm_width, REFERENCE_CHIBI)
    by_name = {mesh.name: mesh for mesh in meshes}

    assert np.ptp(by_name["Head"].vertices, axis=0) == pytest.approx((1.0, 1.0, 1.0))
    assert np.ptp(by_name["Body"].vertices, axis=0) == pytest.approx((0.5, 0.5, 0.25))
    assert np.ptp(by_name["Leg.L"].vertices, axis=0) == pytest.approx((0.25, 0.5, 0.25))
    assert np.ptp(by_name["Arm.L"].vertices, axis=0) == pytest.approx(
        (expected_arm_size, 0.5, 0.25)
    )
    assert _world_vertices(by_name["Head"]).mean(axis=0) == pytest.approx((0.0, 1.5, 0.0))
    assert _world_vertices(by_name["Body"]).mean(axis=0) == pytest.approx((0.0, 0.75, 0.0))
    assert _world_vertices(by_name["Leg.L"]).mean(axis=0) == pytest.approx(
        (0.125, 0.25, 0.0)
    )
    assert _world_vertices(by_name["Leg.R"]).mean(axis=0) == pytest.approx(
        (-0.125, 0.25, 0.0)
    )

    base_world = np.vstack(
        [_world_vertices(by_name[name]) for name in ("Head", "Body", "Leg.L", "Leg.R")]
    )
    assert base_world[:, 1].min() == pytest.approx(0.0)
    assert base_world[:, 1].max() == pytest.approx(2.0)

    left_arm = by_name["Arm.L"]
    right_arm = by_name["Arm.R"]
    assert left_arm.pivot[1] == pytest.approx(1.0)
    assert right_arm.pivot[1] == pytest.approx(1.0)
    assert left_arm.rotation_degrees == pytest.approx(5.0)
    assert right_arm.rotation_degrees == pytest.approx(-5.0)

    body_half_width = 0.25
    arm_half_width = expected_arm_size / 2.0
    expected_center_x = body_half_width + arm_half_width - SHOULDER_OVERLAP
    assert left_arm.pivot[0] + left_arm.vertices[:, 0].mean() == pytest.approx(
        expected_center_x
    )
    assert right_arm.pivot[0] + right_arm.vertices[:, 0].mean() == pytest.approx(
        -expected_center_x
    )

    # The upper inner edge is the rotation pivot and lies slightly inside the body.
    assert left_arm.pivot[0] - body_half_width == pytest.approx(-SHOULDER_OVERLAP)
    assert -body_half_width - right_arm.pivot[0] == pytest.approx(-SHOULDER_OVERLAP)

    mirrored_right = _world_vertices(right_arm).copy()
    mirrored_right[:, 0] *= -1.0
    assert np.allclose(_sorted_unique(_world_vertices(left_arm)), _sorted_unique(mirrored_right))


def test_reference_overlay_centers_pivots_and_rotations_match_base() -> None:
    meshes = build_chibi_meshes(uv_table(4), 4, REFERENCE_CHIBI)
    by_name = {mesh.name: mesh for mesh in meshes}
    pairs = {
        "Head": "Head_Overlay",
        "Body": "Body_Overlay",
        "Arm.L": "Arm_Overlay.L",
        "Arm.R": "Arm_Overlay.R",
        "Leg.L": "Leg_Overlay.L",
        "Leg.R": "Leg_Overlay.R",
    }

    for base_name, overlay_name in pairs.items():
        base = by_name[base_name]
        overlay = by_name[overlay_name]
        assert overlay.pivot == base.pivot
        assert overlay.rotation_degrees == base.rotation_degrees
        assert np.allclose(overlay.vertices.mean(axis=0), base.vertices.mean(axis=0))
        assert np.allclose(_world_vertices(overlay).mean(axis=0), _world_vertices(base).mean(axis=0))

        expected_growth = 0.0625 if base_name == "Head" else 0.03125
        assert np.ptp(overlay.vertices, axis=0) - np.ptp(
            base.vertices, axis=0
        ) == pytest.approx((expected_growth,) * 3)


def test_legacy_profile_keeps_previous_head_dimensions() -> None:
    meshes = build_chibi_meshes(uv_table(4), 4, LEGACY)
    head = next(mesh for mesh in meshes if mesh.name == "Head")
    assert np.ptp(head.vertices, axis=0) == pytest.approx((2.4, 2.4, 2.4))
