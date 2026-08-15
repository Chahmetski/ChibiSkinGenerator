from __future__ import annotations

import numpy as np

from chibi_skin_generator.skin_parser import detect_arm_model
from chibi_skin_generator.uv_tables import FACE_NAMES, UVRect, uv_table


EXPECTED_PARTS = {
    "Head",
    "Head_Overlay",
    "Body",
    "Body_Overlay",
    "Arm.L",
    "Arm.R",
    "Arm_Overlay.L",
    "Arm_Overlay.R",
    "Leg.L",
    "Leg.R",
    "Leg_Overlay.L",
    "Leg_Overlay.R",
}


def test_head_uv_rectangles_match_standard_layout() -> None:
    head = uv_table(4)["Head"]
    assert head == {
        "top": UVRect(8, 0, 16, 8),
        "bottom": UVRect(16, 0, 24, 8),
        "right": UVRect(0, 8, 8, 16),
        "front": UVRect(8, 8, 16, 16),
        "left": UVRect(16, 8, 24, 16),
        "back": UVRect(24, 8, 32, 16),
    }


def test_normalized_uv_uses_half_texel_inset_and_flipped_v() -> None:
    corners = uv_table(4)["Head"]["front"].normalized_corners()
    assert corners == (
        (8.5 / 64, 1.0 - 8.5 / 64),
        (15.5 / 64, 1.0 - 8.5 / 64),
        (15.5 / 64, 1.0 - 15.5 / 64),
        (8.5 / 64, 1.0 - 15.5 / 64),
    )


def test_tables_contain_all_parts_and_faces_with_valid_coordinates() -> None:
    for arm_width in (3, 4):
        table = uv_table(arm_width)
        assert set(table) == EXPECTED_PARTS
        for faces in table.values():
            assert set(faces) == set(FACE_NAMES)
            for rect in faces.values():
                assert 0 <= rect.x0 < rect.x1 <= 64
                assert 0 <= rect.y0 < rect.y1 <= 64


def test_steve_and_alex_arm_widths_use_correct_atlas_width() -> None:
    steve = uv_table(4)["Arm.R"]
    alex = uv_table(3)["Arm.R"]
    assert steve["front"].width == 4
    assert steve["right"].width == 4
    assert alex["front"].width == 3
    assert alex["right"].width == 4  # arm depth remains four pixels
    assert alex["back"] == UVRect(51, 20, 54, 32)


def test_every_overlay_uses_its_own_standard_atlas_region() -> None:
    steve = uv_table(4)
    alex = uv_table(3)
    expected_overlay_fronts = {
        "Head_Overlay": UVRect(40, 8, 48, 16),
        "Body_Overlay": UVRect(20, 36, 28, 48),
        "Arm_Overlay.R": UVRect(44, 36, 48, 48),
        "Arm_Overlay.L": UVRect(52, 52, 56, 64),
        "Leg_Overlay.R": UVRect(4, 36, 8, 48),
        "Leg_Overlay.L": UVRect(4, 52, 8, 64),
    }
    for name, expected in expected_overlay_fronts.items():
        assert steve[name]["front"] == expected

    assert alex["Arm_Overlay.R"]["front"] == UVRect(44, 36, 47, 48)
    assert alex["Arm_Overlay.L"]["front"] == UVRect(52, 52, 55, 64)

    base_for_overlay = {
        "Head_Overlay": "Head",
        "Body_Overlay": "Body",
        "Arm_Overlay.R": "Arm.R",
        "Arm_Overlay.L": "Arm.L",
        "Leg_Overlay.R": "Leg.R",
        "Leg_Overlay.L": "Leg.L",
    }
    for overlay, base in base_for_overlay.items():
        assert steve[overlay]["front"] != steve[base]["front"]


def test_auto_model_detection_uses_slim_transparent_columns() -> None:
    alex_pixels = np.zeros((64, 64, 4), dtype=np.uint8)
    alex_pixels[:, :, 3] = 255
    alex_pixels[20:32, 54:56, 3] = 0
    alex_pixels[52:64, 46:48, 3] = 0
    assert detect_arm_model(alex_pixels) == "Alex"

    steve_pixels = alex_pixels.copy()
    steve_pixels[20, 54, 3] = 255
    assert detect_arm_model(steve_pixels) == "Steve"
