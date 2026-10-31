from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from chibi_skin_generator.animations import (
    AnimationTrack, HIPS_TRANSLATION_CLIPS, axis_angle_quaternion,
    build_animation_clips, evaluate_clip, posed_mesh_vertices, sample_track,
)
from chibi_skin_generator.exporter import generate_model
from chibi_skin_generator.geometry import build_chibi_meshes
from chibi_skin_generator.preset_storage import PresetError, PresetStorage, sanitize_preset_name
from chibi_skin_generator.proportions import get_builtin_preset
from chibi_skin_generator.rig import build_skeleton
from chibi_skin_generator.skin_parser import SkinError, load_skin
from chibi_skin_generator.uv_tables import uv_table


@pytest.mark.parametrize("format", ("BMP", "JPEG", "GIF"))
def test_renaming_another_format_to_png_is_rejected(tmp_path, format):
    path = tmp_path / "fake.png"
    Image.new("RGB", (64, 64)).save(path, format=format)
    with pytest.raises(SkinError, match="Содержимое"):
        load_skin(path)


@pytest.mark.parametrize("size", ((64, 32), (128, 128)))
def test_unsupported_skin_dimensions_are_rejected(tmp_path, size):
    path = tmp_path / "size.png"
    Image.new("RGBA", size).save(path)
    with pytest.raises(SkinError, match="64×64"):
        load_skin(path)


def test_preset_filesystem_failure_is_a_user_error(tmp_path):
    blocked = tmp_path / "not_a_directory"
    blocked.write_text("keep me")
    storage = PresetStorage(blocked)
    with pytest.raises(PresetError):
        storage.save("Example", get_builtin_preset("Compact Chibi"))
    assert blocked.read_text() == "keep me"


def test_preset_delete_permission_failure_is_a_user_error(tmp_path, monkeypatch):
    storage = PresetStorage(tmp_path)
    storage.save("Example", get_builtin_preset("Compact Chibi"))
    def deny(*args, **kwargs):
        raise PermissionError("access denied")
    monkeypatch.setattr(Path, "unlink", deny)
    with pytest.raises(PresetError, match="access denied"):
        storage.delete("Example")


@pytest.mark.parametrize("name", ("CON", "nul", "COM1", "LPT9.example"))
def test_reserved_windows_preset_names_are_rejected(name):
    with pytest.raises(PresetError, match="Windows"):
        sanitize_preset_name(name)


def test_concurrent_exports_never_overwrite_existing_file(tmp_path):
    source = tmp_path / "skin.png"
    Image.new("RGBA", (64, 64), (100, 150, 200, 255)).save(source)
    original = tmp_path / "skin_chibi.glb"
    original.write_bytes(b"previous user model")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: generate_model(source, "Steve", tmp_path,
                            animation_names=()), range(2)))
    assert original.read_bytes() == b"previous user model"
    assert len({item.output_path for item in results}) == 2
    assert all(item.output_path.read_bytes()[:4] == b"glTF" for item in results)
    assert not list(tmp_path.glob("*.tmp"))


def test_rotation_interpolation_has_constant_angular_speed():
    track = AnimationTrack("Head", np.array((0., 1.)), np.array((
        axis_angle_quaternion("x", 0), axis_angle_quaternion("x", 160))))
    assert np.allclose(sample_track(track, .25), axis_angle_quaternion("x", 40))
    track.values[1] *= -1
    assert np.allclose(sample_track(track, .25), axis_angle_quaternion("x", 40))


@pytest.mark.parametrize("preset", ("Compact Chibi", "Balanced Chibi", "Big Head", "Legacy"))
@pytest.mark.parametrize("width", (3, 4))
def test_ground_contact_between_keys_in_all_allowed_clips(preset, width):
    settings = get_builtin_preset(preset)
    meshes = build_chibi_meshes(uv_table(width), width, settings)
    rig = build_skeleton(settings, width)
    clips = build_animation_clips(rig, animation_names=HIPS_TRANSLATION_CLIPS, meshes=meshes)
    for clip in clips:
        # Deliberately avoid the baked sample times.
        for time in np.linspace(.001, clip.duration-.001, 93):
            parts = posed_mesh_vertices(rig, meshes, evaluate_clip(rig, clip, float(time)))
            lowest = min(float(vertices[:, 1].min()) for vertices in parts.values())
            assert abs(lowest) < .001 * settings.overall_scale, (preset, width, clip.name, time, lowest)
