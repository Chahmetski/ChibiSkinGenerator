from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from chibi_skin_generator.geometry import MeshData, build_chibi_meshes
from chibi_skin_generator.proportions import (
    COMPACT_CHIBI,
    LEGACY,
    PARAMETER_SPECS,
    ProportionError,
    ProportionSettings,
    builtin_presets,
    calculate_proportions,
    get_builtin_preset,
)
from chibi_skin_generator.uv_tables import uv_table


def _world_vertices(mesh: MeshData) -> np.ndarray:
    homogeneous = np.column_stack((mesh.vertices, np.ones(len(mesh.vertices))))
    return (mesh.transform @ homogeneous.T).T[:, :3]


def _sorted_unique(points: np.ndarray) -> np.ndarray:
    rounded = np.unique(np.round(points, decimals=7), axis=0)
    order = np.lexsort((rounded[:, 2], rounded[:, 1], rounded[:, 0]))
    return rounded[order]


def _meshes(settings: ProportionSettings | None = None, arm_pixels: int = 4) -> dict[str, MeshData]:
    current = settings or get_builtin_preset(COMPACT_CHIBI)
    return {
        mesh.name: mesh
        for mesh in build_chibi_meshes(uv_table(arm_pixels), arm_pixels, current)
    }


@pytest.mark.parametrize("field_name", tuple(PARAMETER_SPECS))
def test_settings_enforce_safe_ranges(field_name: str) -> None:
    spec = PARAMETER_SPECS[field_name]
    with pytest.raises(ProportionError):
        ProportionSettings().changed(**{field_name: spec.minimum - max(spec.step, 0.001)})
    with pytest.raises(ProportionError):
        ProportionSettings().changed(**{field_name: spec.maximum + max(spec.step, 0.001)})


def test_builtin_presets_are_not_mutable_through_shared_objects() -> None:
    presets = builtin_presets()
    with pytest.raises(FrozenInstanceError):
        presets[COMPACT_CHIBI].head_size = 1.4  # type: ignore[misc]
    presets.pop(COMPACT_CHIBI)
    assert get_builtin_preset(COMPACT_CHIBI).head_size == pytest.approx(1.0)


def test_automatic_vertical_connections_and_ground() -> None:
    settings = ProportionSettings(
        overall_scale=1.7,
        head_size=0.8,
        body_height=0.7,
        leg_length=0.65,
    )
    meshes = _meshes(settings)
    head = _world_vertices(meshes["Head"])
    body = _world_vertices(meshes["Body"])
    left_leg = _world_vertices(meshes["Leg.L"])
    right_leg = _world_vertices(meshes["Leg.R"])

    assert left_leg[:, 1].min() == pytest.approx(0.0, abs=1e-7)
    assert right_leg[:, 1].min() == pytest.approx(0.0, abs=1e-7)
    assert body[:, 1].min() == pytest.approx(left_leg[:, 1].max())
    assert head[:, 1].min() == pytest.approx(body[:, 1].max())
    assert head[:, 1].max() == pytest.approx(
        settings.overall_scale
        * (settings.leg_length + settings.body_height + settings.head_size)
    )


@pytest.mark.parametrize("arm_pixels", (4, 3))
def test_arms_connect_at_shoulder_and_rotate_about_inner_top_edge(arm_pixels: int) -> None:
    settings = ProportionSettings(
        body_width=0.63,
        arm_thickness=1.2,
        shoulder_overlap=0.02,
        arm_angle=11.0,
    )
    meshes = _meshes(settings, arm_pixels)
    left = meshes["Arm.L"]
    right = meshes["Arm.R"]
    body_half_world = settings.body_width * settings.overall_scale / 2.0

    assert left.pivot[0] - body_half_world == pytest.approx(
        -settings.shoulder_overlap * settings.overall_scale
    )
    assert -body_half_world - right.pivot[0] == pytest.approx(
        -settings.shoulder_overlap * settings.overall_scale
    )
    assert left.rotation_degrees == pytest.approx(settings.arm_angle)
    assert right.rotation_degrees == pytest.approx(-settings.arm_angle)

    # Local (0, 0) is the upper inner edge; rotation cannot move the pivot.
    assert left.vertices[:, 0].min() == pytest.approx(0.0)
    assert left.vertices[:, 1].max() == pytest.approx(0.0)
    assert right.vertices[:, 0].max() == pytest.approx(0.0)
    assert right.vertices[:, 1].max() == pytest.approx(0.0)

    mirrored_right = _world_vertices(right).copy()
    mirrored_right[:, 0] *= -1.0
    assert np.allclose(_sorted_unique(_world_vertices(left)), _sorted_unique(mirrored_right))


def test_leg_gap_never_intersects_left_and_right_legs() -> None:
    settings = ProportionSettings(leg_width=0.4, leg_gap=0.12)
    meshes = _meshes(settings)
    left = _world_vertices(meshes["Leg.L"])
    right = _world_vertices(meshes["Leg.R"])
    actual_gap = left[:, 0].min() - right[:, 0].max()
    assert actual_gap == pytest.approx(settings.leg_gap * settings.overall_scale)
    assert actual_gap >= 0.0


def test_base_and_overlay_share_center_transform_and_expand_uniformly() -> None:
    settings = ProportionSettings(
        overall_scale=1.35,
        head_overlay_offset=0.04,
        other_overlay_offset=0.02,
        arm_angle=9.0,
    )
    meshes = _meshes(settings)
    pairs = {
        "Head": "Head_Overlay",
        "Body": "Body_Overlay",
        "Arm.L": "Arm_Overlay.L",
        "Arm.R": "Arm_Overlay.R",
        "Leg.L": "Leg_Overlay.L",
        "Leg.R": "Leg_Overlay.R",
    }
    for base_name, overlay_name in pairs.items():
        base = meshes[base_name]
        overlay = meshes[overlay_name]
        assert np.allclose(base.transform, overlay.transform)
        assert np.allclose(base.vertices.mean(axis=0), overlay.vertices.mean(axis=0))
        expected = (
            settings.head_overlay_offset if base_name == "Head" else settings.other_overlay_offset
        ) * settings.overall_scale * 2.0
        assert np.ptp(overlay.vertices, axis=0) - np.ptp(
            base.vertices, axis=0
        ) == pytest.approx((expected,) * 3)


def test_steve_and_alex_width_follow_pixel_ratio_and_thickness_multiplier() -> None:
    settings = ProportionSettings(overall_scale=1.4, arm_thickness=1.3)
    steve = _meshes(settings, 4)["Arm.L"]
    alex = _meshes(settings, 3)["Arm.L"]
    steve_width = np.ptp(steve.vertices, axis=0)[0]
    alex_width = np.ptp(alex.vertices, axis=0)[0]
    assert steve_width == pytest.approx(0.25 * 1.3 * 1.4)
    assert alex_width == pytest.approx(0.1875 * 1.3 * 1.4)
    assert alex_width / steve_width == pytest.approx(3.0 / 4.0)


def test_changing_proportions_never_changes_uv_tables_or_mesh_uv() -> None:
    original_table = uv_table(4)
    compact = _meshes(get_builtin_preset(COMPACT_CHIBI))
    custom = _meshes(
        ProportionSettings(
            overall_scale=3.0,
            head_size=1.4,
            body_width=0.8,
            arm_thickness=1.45,
            leg_gap=0.2,
        )
    )
    assert uv_table(4) is original_table
    for name in compact:
        assert np.array_equal(compact[name].uv, custom[name].uv)


def test_legacy_preset_preserves_previous_export_dimensions() -> None:
    meshes = _meshes(get_builtin_preset(LEGACY))
    assert np.ptp(meshes["Head"].vertices, axis=0) == pytest.approx((2.4, 2.4, 2.4))
    assert np.ptp(meshes["Body"].vertices, axis=0) == pytest.approx((1.55, 1.55, 0.78))
    assert np.ptp(meshes["Arm.L"].vertices, axis=0) == pytest.approx((0.58, 1.45, 0.62))
    assert np.ptp(meshes["Leg.L"].vertices, axis=0) == pytest.approx((0.68, 0.90, 0.70))
