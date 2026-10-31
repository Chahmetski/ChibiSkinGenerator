from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from chibi_skin_generator import __version__
from chibi_skin_generator.animations import (
    ANIMATION_NAMES,
    CLIP_DURATIONS,
    HIPS_TRANSLATION_CLIPS,
    LOOP_CLIP_NAMES,
    build_animation_clips,
    evaluate_clip,
    posed_mesh_vertices,
)
from chibi_skin_generator.exporter import BIN_CHUNK, JSON_CHUNK, generate_model
from chibi_skin_generator.geometry import build_chibi_meshes
from chibi_skin_generator.proportions import get_builtin_preset
from chibi_skin_generator.rig import build_skeleton
from chibi_skin_generator.uv_tables import uv_table


def _write_skin(path: Path) -> None:
    y, x = np.indices((64, 64))
    pixels = np.empty((64, 64, 4), dtype=np.uint8)
    pixels[..., 0] = (x * 4).astype(np.uint8)
    pixels[..., 1] = (y * 4).astype(np.uint8)
    pixels[..., 2] = 160
    pixels[..., 3] = 255
    pixels[0:16, 32:64, 3] = 0
    Image.fromarray(pixels, "RGBA").save(path)


def _read_glb(path: Path) -> tuple[dict, bytes]:
    blob = path.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", blob, 0)
    assert (magic, version, total) == (b"glTF", 2, len(blob))
    document = None
    binary = None
    offset = 12
    while offset < len(blob):
        length, chunk_type = struct.unpack_from("<II", blob, offset)
        offset += 8
        chunk = blob[offset : offset + length]
        offset += length
        if chunk_type == JSON_CHUNK:
            document = json.loads(chunk.rstrip(b" \x00").decode("utf-8"))
        elif chunk_type == BIN_CHUNK:
            binary = chunk
    assert document is not None and binary is not None
    return document, binary


def _accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = {
        5121: np.dtype("u1"),
        5123: np.dtype("<u2"),
        5125: np.dtype("<u4"),
        5126: np.dtype("<f4"),
    }[accessor["componentType"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[
        accessor["type"]
    ]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return np.frombuffer(
        binary, dtype=dtype, count=accessor["count"] * width, offset=offset
    ).reshape(accessor["count"], width)


def _normalize(quaternion: np.ndarray) -> np.ndarray:
    return quaternion / np.linalg.norm(quaternion)


def _multiply(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    left, right = _normalize(left), _normalize(right)
    xyz = (
        left[3] * right[:3]
        + right[3] * left[:3]
        + np.cross(left[:3], right[:3])
    )
    return _normalize(np.append(xyz, left[3] * right[3] - np.dot(left[:3], right[:3])))


def _inverse(quaternion: np.ndarray) -> np.ndarray:
    quaternion = _normalize(quaternion)
    return np.asarray((-quaternion[0], -quaternion[1], -quaternion[2], quaternion[3]))


def _axis_quaternion(axis: int, degrees: float) -> np.ndarray:
    result = np.zeros(4)
    result[axis] = np.sin(np.deg2rad(degrees) / 2.0)
    result[3] = np.cos(np.deg2rad(degrees) / 2.0)
    return result


def _equivalent(left: np.ndarray, right: np.ndarray, atol: float = 2e-6) -> bool:
    left, right = _normalize(left), _normalize(right)
    return bool(abs(float(np.dot(left, right))) >= 1.0 - atol)


def _signed_axis_degrees(delta: np.ndarray, axis: int) -> float:
    value = _normalize(delta)
    if value[3] < 0.0:
        value = -value
    return float(np.rad2deg(2.0 * np.arctan2(value[axis], value[3])))


def _clips(document: dict, binary: bytes) -> dict[str, dict[str, tuple[np.ndarray, np.ndarray]]]:
    nodes = document["nodes"]
    result = {}
    for animation in document.get("animations", []):
        tracks = {}
        for channel in animation["channels"]:
            sampler = animation["samplers"][channel["sampler"]]
            times = _accessor(document, binary, sampler["input"]).reshape(-1)
            rotations = _accessor(document, binary, sampler["output"])
            tracks[nodes[channel["target"]["node"]]["name"]] = (times, rotations)
        result[animation["name"]] = tracks
    return result


def _pose_pack(preset_name: str, names: tuple[str, ...]):
    settings = get_builtin_preset(preset_name)
    skeleton = build_skeleton(settings, 4)
    meshes = build_chibi_meshes(uv_table(4), 4, settings)
    clips = {
        clip.name: clip
        for clip in build_animation_clips(
            skeleton,
            animation_names=names,
            meshes=meshes,
        )
    }
    return skeleton, meshes, clips


def _joint_position(skeleton, world, name: str) -> np.ndarray:
    return world[skeleton.index(name)][:3, 3]


@pytest.fixture(scope="module")
def animation_exports(tmp_path_factory):
    root = tmp_path_factory.mktemp("animation_exports")
    skin_path = root / "animation_skin.png"
    _write_skin(skin_path)
    modes = {
        "both": (True, True),
        "idle": (True, False),
        "walk": (False, True),
        "none": (False, False),
    }
    exports = {}
    for name, (include_idle, include_walk) in modes.items():
        result = generate_model(
            skin_path,
            "Steve",
            root / name,
            include_idle=include_idle,
            include_walk=include_walk,
        )
        document, binary = _read_glb(result.output_path)
        exports[name] = (document, binary, result)
    return exports


@pytest.fixture(scope="module")
def combat_exports(tmp_path_factory):
    root = tmp_path_factory.mktemp("combat_exports")
    skin_path = root / "combat_skin.png"
    _write_skin(skin_path)
    full_result = generate_model(
        skin_path,
        "Steve",
        root / "full",
        animation_names=ANIMATION_NAMES,
    )
    full_document, full_binary = _read_glb(full_result.output_path)
    singles = {}
    for animation_name in ANIMATION_NAMES:
        result = generate_model(
            skin_path,
            "Steve",
            root / animation_name,
            animation_names=(animation_name,),
        )
        document, binary = _read_glb(result.output_path)
        singles[animation_name] = (document, binary, result)
    return (full_document, full_binary, full_result), singles


def test_animation_modes_names_and_metadata(animation_exports) -> None:
    assert __version__ == "0.8.0"
    both_document, _, both_result = animation_exports["both"]
    assert [animation["name"] for animation in both_document["animations"]] == [
        "Idle",
        "Walk",
    ]
    assert both_result.animations == ("Idle", "Walk")
    assert both_document["animations"][0]["extras"] == {"loop": True}
    assert both_document["animations"][1]["extras"] == {
        "loop": True,
        "suggestedSpeed": 1.0,
        "inPlace": True,
    }
    assert [item["name"] for item in animation_exports["idle"][0]["animations"]] == [
        "Idle"
    ]
    assert [item["name"] for item in animation_exports["walk"][0]["animations"]] == [
        "Walk"
    ]
    assert "animations" not in animation_exports["none"][0]
    assert animation_exports["none"][2].animations == ()


def test_animation_accessors_channels_loops_and_durations(animation_exports) -> None:
    document, binary, _ = animation_exports["both"]
    durations = {"Idle": 2.4, "Walk": 1.0}
    joint_nodes = set(document["skins"][0]["joints"])
    for animation in document["animations"]:
        assert animation["samplers"]
        assert animation["channels"]
        input_accessors = {sampler["input"] for sampler in animation["samplers"]}
        assert len(input_accessors) == 1
        for sampler in animation["samplers"]:
            assert sampler["interpolation"] == "LINEAR"
            input_accessor = document["accessors"][sampler["input"]]
            output_accessor = document["accessors"][sampler["output"]]
            assert input_accessor["type"] == "SCALAR"
            assert input_accessor["componentType"] == 5126
            assert output_accessor["type"] == "VEC4"
            assert output_accessor["componentType"] == 5126
            times = _accessor(document, binary, sampler["input"]).reshape(-1)
            rotations = _accessor(document, binary, sampler["output"])
            assert times[0] == pytest.approx(0.0)
            assert times[-1] == pytest.approx(durations[animation["name"]])
            assert np.all(np.diff(times) > 0.0)
            assert np.allclose(np.linalg.norm(rotations, axis=1), 1.0, atol=2e-6)
            assert np.all(np.sum(rotations[:-1] * rotations[1:], axis=1) >= 0.0)
            assert np.allclose(rotations[0], rotations[-1])
        for channel in animation["channels"]:
            assert channel["target"]["node"] in joint_nodes
            assert channel["target"]["path"] == "rotation"
        assert all(channel["target"]["path"] not in {"translation", "scale"} for channel in animation["channels"])
    assert document["animations"][0]["samplers"][0]["input"] != document["animations"][1]["samplers"][0]["input"]


def test_only_expected_joints_are_animated(animation_exports) -> None:
    document, binary, _ = animation_exports["both"]
    clips = _clips(document, binary)
    assert set(clips["Idle"]) == {"Head", "Spine", "Arm.L", "Arm.R"}
    assert set(clips["Walk"]) == {"Spine", "Arm.L", "Arm.R", "Leg.L", "Leg.R"}
    for clip in clips.values():
        assert not ({"Root", "Hips", "Hand.L", "Hand.R", "Foot.L", "Foot.R"} & set(clip))


def test_walk_symmetry_opposition_and_half_cycle_phase_swap(animation_exports) -> None:
    document, binary, _ = animation_exports["both"]
    walk = _clips(document, binary)["Walk"]
    joint_nodes = {
        document["nodes"][index]["name"]: document["nodes"][index]
        for index in document["skins"][0]["joints"]
    }

    def x_deltas(name: str) -> np.ndarray:
        rest = np.asarray(joint_nodes[name]["rotation"])
        rotations = walk[name][1]
        return np.asarray(
            [_signed_axis_degrees(_multiply(_inverse(rest), value), 0) for value in rotations]
        )

    arm_left = x_deltas("Arm.L")
    arm_right = x_deltas("Arm.R")
    leg_left = x_deltas("Leg.L")
    leg_right = x_deltas("Leg.R")
    assert np.allclose(arm_left, -arm_right, atol=2e-4)
    assert np.allclose(leg_left, -leg_right, atol=2e-4)
    assert np.sign(arm_left[0]) == -np.sign(leg_left[0])
    assert np.sign(arm_right[0]) == -np.sign(leg_right[0])
    assert arm_left[0] == pytest.approx(-arm_left[2], abs=2e-4)
    assert arm_right[0] == pytest.approx(-arm_right[2], abs=2e-4)
    assert leg_left[0] == pytest.approx(-leg_left[2], abs=2e-4)
    assert leg_right[0] == pytest.approx(-leg_right[2], abs=2e-4)
    assert np.allclose(arm_left[[1, 3]], 0.0, atol=2e-4)
    assert np.allclose(leg_left[[1, 3]], 0.0, atol=2e-4)


def test_idle_is_subtle_and_much_smaller_than_walk(animation_exports) -> None:
    document, binary, _ = animation_exports["both"]
    clips = _clips(document, binary)
    joint_nodes = {
        document["nodes"][index]["name"]: document["nodes"][index]
        for index in document["skins"][0]["joints"]
    }

    def max_delta_angle(clip_name: str, joint_name: str) -> float:
        rest = np.asarray(joint_nodes[joint_name]["rotation"])
        angles = []
        for rotation in clips[clip_name][joint_name][1]:
            delta = _multiply(_inverse(rest), rotation)
            angles.append(np.rad2deg(2.0 * np.arccos(np.clip(abs(delta[3]), 0.0, 1.0))))
        return float(max(angles))

    idle_arm = max_delta_angle("Idle", "Arm.L")
    walk_arm = max_delta_angle("Walk", "Arm.L")
    assert 1.5 <= idle_arm <= 2.5
    assert walk_arm == pytest.approx(25.0, abs=2e-4)
    assert idle_arm * 8.0 < walk_arm
    assert max_delta_angle("Idle", "Head") <= 1.5
    assert max_delta_angle("Idle", "Spine") <= 0.6


def test_rest_rotation_is_composed_before_local_animation_delta(animation_exports) -> None:
    document, binary, _ = animation_exports["both"]
    clips = _clips(document, binary)
    joint_nodes = {
        document["nodes"][index]["name"]: document["nodes"][index]
        for index in document["skins"][0]["joints"]
    }
    rest = np.asarray(joint_nodes["Arm.L"]["rotation"])
    walk_rotations = clips["Walk"]["Arm.L"][1]
    expected = _multiply(rest, _axis_quaternion(0, -25.0))
    wrong_order = _multiply(_axis_quaternion(0, -25.0), rest)
    assert _equivalent(walk_rotations[0], expected)
    assert not _equivalent(walk_rotations[0], wrong_order)
    assert _equivalent(walk_rotations[1], rest)
    assert _equivalent(clips["Idle"]["Arm.L"][1][0], rest)


def test_animations_do_not_change_skin_bind_pose_or_mesh_data(animation_exports) -> None:
    animated_document, animated_binary, _ = animation_exports["both"]
    plain_document, plain_binary, _ = animation_exports["none"]
    assert animated_document["skins"] == plain_document["skins"]
    for joint_index in plain_document["skins"][0]["joints"]:
        assert animated_document["nodes"][joint_index] == plain_document["nodes"][joint_index]
    for animated_mesh, plain_mesh in zip(
        animated_document["meshes"], plain_document["meshes"], strict=True
    ):
        animated_primitive = animated_mesh["primitives"][0]
        plain_primitive = plain_mesh["primitives"][0]
        assert animated_primitive == plain_primitive
        for semantic in ("POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"):
            assert np.array_equal(
                _accessor(animated_document, animated_binary, animated_primitive["attributes"][semantic]),
                _accessor(plain_document, plain_binary, plain_primitive["attributes"][semantic]),
            )
    assert animated_document["materials"] == plain_document["materials"]
    assert animated_document["samplers"] == plain_document["samplers"]
    assert animated_document["images"] == plain_document["images"]

    positions = []
    for mesh in animated_document["meshes"]:
        primitive = mesh["primitives"][0]
        positions.append(
            _accessor(animated_document, animated_binary, primitive["attributes"]["POSITION"])
        )
    all_positions = np.concatenate(positions)
    baseline = json.loads(
        Path(__file__).with_name("rest_pose_baselines.json").read_text(encoding="utf-8")
    )["Compact Chibi|4"]
    assert np.allclose(all_positions.min(axis=0), baseline["min"], atol=2e-6)
    assert np.allclose(all_positions.max(axis=0), baseline["max"], atol=2e-6)


@pytest.mark.parametrize("mode", ("both", "idle", "walk", "none"))
def test_every_animation_mode_is_readable_without_required_extensions(
    animation_exports, mode: str
) -> None:
    document, _, result = animation_exports[mode]
    assert not document.get("extensionsRequired")
    loaded = trimesh.load(result.output_path, force="scene")
    assert isinstance(loaded, trimesh.Scene)
    assert len(loaded.geometry) == 12


def test_core_combat_pack_has_exact_unique_clip_names(combat_exports) -> None:
    (document, _, result), _ = combat_exports
    names = [animation["name"] for animation in document["animations"]]
    assert names == list(ANIMATION_NAMES)
    assert len(names) == len(set(names)) == 15
    assert "AttackOverhead2H" not in names
    assert {"WeaponIdle", "AttackHeavySide", "Death"} <= set(names)
    assert result.animations == ANIMATION_NAMES


@pytest.mark.parametrize("animation_name", ANIMATION_NAMES)
def test_every_combat_clip_exports_individually(
    combat_exports, animation_name: str
) -> None:
    _, singles = combat_exports
    document, _, result = singles[animation_name]
    assert [animation["name"] for animation in document["animations"]] == [
        animation_name
    ]
    assert result.animations == (animation_name,)


def test_all_combat_clips_have_valid_channels_and_expected_duration(
    combat_exports,
) -> None:
    (document, binary, _), _ = combat_exports
    joint_nodes = set(document["skins"][0]["joints"])
    nodes = document["nodes"]
    for animation in document["animations"]:
        name = animation["name"]
        assert animation["extras"]["loop"] == (name in LOOP_CLIP_NAMES)
        assert len(animation["channels"]) == len(animation["samplers"])
        for channel in animation["channels"]:
            path = channel["target"]["path"]
            target_name = nodes[channel["target"]["node"]]["name"]
            assert path == "rotation" or (
                name in HIPS_TRANSLATION_CLIPS
                and target_name == "Hips"
                and path == "translation"
            )
            assert channel["target"]["node"] in joint_nodes
            assert target_name != "Root"
            if path == "translation":
                assert target_name == "Hips"
                assert name in HIPS_TRANSLATION_CLIPS
            sampler = animation["samplers"][channel["sampler"]]
            assert sampler["interpolation"] == "LINEAR"
            times = _accessor(document, binary, sampler["input"]).reshape(-1)
            rotations = _accessor(document, binary, sampler["output"])
            assert times[0] == pytest.approx(0.0)
            assert times[-1] == pytest.approx(CLIP_DURATIONS[name], abs=2e-6)
            assert np.all(np.diff(times) > 0.0)
            assert np.all(np.isfinite(rotations))
            if path == "rotation":
                assert np.allclose(np.linalg.norm(rotations, axis=1), 1.0, atol=2e-6)
                assert np.all(np.sum(rotations[:-1] * rotations[1:], axis=1) >= 0.0)
            if name in LOOP_CLIP_NAMES:
                assert np.allclose(rotations[0], rotations[-1])
        assert all(channel["target"]["path"] not in {"scale", "weights"} for channel in animation["channels"])


def test_full_pack_preserves_idle_walk_key_data(animation_exports, combat_exports) -> None:
    legacy_document, legacy_binary, _ = animation_exports["both"]
    (full_document, full_binary, _), _ = combat_exports
    legacy_clips = _clips(legacy_document, legacy_binary)
    full_clips = _clips(full_document, full_binary)
    for clip_name in ("Idle", "Walk"):
        assert set(full_clips[clip_name]) == set(legacy_clips[clip_name])
        for joint_name in legacy_clips[clip_name]:
            legacy_times, legacy_rotations = legacy_clips[clip_name][joint_name]
            full_times, full_rotations = full_clips[clip_name][joint_name]
            assert np.array_equal(full_times, legacy_times)
            assert np.array_equal(full_rotations, legacy_rotations)


def test_protected_clips_match_their_individual_exports_byte_for_byte(
    combat_exports,
) -> None:
    protected = {
        "Idle",
        "Walk",
        "Run",
        "Jump",
        "Fall",
        "Land",
        "ZombieWalk",
        "HitReact",
        "AttackOneHand",
        "AttackDualDaggers",
    }
    (full_document, full_binary, _), singles = combat_exports
    full = _clips(full_document, full_binary)
    for clip_name in protected:
        single_document, single_binary, _ = singles[clip_name]
        single = _clips(single_document, single_binary)[clip_name]
        assert set(full[clip_name]) == set(single)
        for joint_name in single:
            assert np.array_equal(full[clip_name][joint_name][0], single[joint_name][0])
            assert np.array_equal(full[clip_name][joint_name][1], single[joint_name][1])


def test_combat_clip_motion_and_attack_phase_semantics(combat_exports) -> None:
    (document, binary, _), _ = combat_exports
    clips = _clips(document, binary)
    joint_nodes = {
        document["nodes"][index]["name"]: document["nodes"][index]
        for index in document["skins"][0]["joints"]
    }

    def x_deltas(clip_name: str, joint_name: str) -> np.ndarray:
        rest = np.asarray(joint_nodes[joint_name]["rotation"])
        return np.asarray(
            [
                _signed_axis_degrees(_multiply(_inverse(rest), rotation), 0)
                for rotation in clips[clip_name][joint_name][1]
            ]
        )

    assert np.max(np.abs(x_deltas("Run", "Arm.L"))) > np.max(
        np.abs(x_deltas("Walk", "Arm.L"))
    )
    assert np.max(np.abs(x_deltas("Run", "Leg.L"))) > np.max(
        np.abs(x_deltas("Walk", "Leg.L"))
    )
    zombie_left = x_deltas("ZombieWalk", "Leg.L")
    zombie_right = x_deltas("ZombieWalk", "Leg.R")
    assert not np.allclose(zombie_left, -zombie_right)

    one_hand_times = clips["AttackOneHand"]["Arm.R"][0]
    assert np.min(np.abs(one_hand_times - 0.31)) < 1e-6
    dual_times = clips["AttackDualDaggers"]["Arm.R"][0]
    assert np.min(np.abs(dual_times - 0.27)) < 1e-6
    assert np.min(np.abs(dual_times - 0.612)) < 1e-6
    dual_right = x_deltas("AttackDualDaggers", "Arm.R")
    dual_left = x_deltas("AttackDualDaggers", "Arm.L")
    assert dual_right[2] > dual_left[2] + 80.0
    assert dual_left[5] > dual_right[5] + 70.0

    heavy_times = clips["AttackHeavySide"]["Arm.R"][0]
    assert np.min(np.abs(heavy_times - 0.51)) < 1e-6
    assert heavy_times[-1] == pytest.approx(0.85)


def test_zombie_walk_arms_stay_forward_and_loop_seamlessly(combat_exports) -> None:
    (document, binary, _), _ = combat_exports
    zombie = next(
        animation for animation in document["animations"] if animation["name"] == "ZombieWalk"
    )
    skeleton, _, clips = _pose_pack("Compact Chibi", ("ZombieWalk",))
    clip = clips["ZombieWalk"]
    arm_hand_pairs = (("Arm.L", "Hand.L"), ("Arm.R", "Hand.R"))
    for time in clip.tracks[0].times:
        world = evaluate_clip(skeleton, clip, float(time))
        for arm_name, hand_name in arm_hand_pairs:
            arm = _joint_position(skeleton, world, arm_name)
            hand = _joint_position(skeleton, world, hand_name)
            direction = hand - arm
            assert direction[2] > 0.4
            assert abs(direction[1]) < 0.18
    for channel in zombie["channels"]:
        sampler = zombie["samplers"][channel["sampler"]]
        values = _accessor(document, binary, sampler["output"])
        assert np.array_equal(values[0], values[-1])


def test_translation_whitelist_scale_ban_and_fixed_root(
    combat_exports,
) -> None:
    (document, binary, _), _ = combat_exports
    nodes = document["nodes"]
    translations: dict[str, tuple[dict, dict]] = {}
    for animation in document["animations"]:
        for channel in animation["channels"]:
            path = channel["target"]["path"]
            target_name = nodes[channel["target"]["node"]]["name"]
            assert path not in {"scale", "weights"}
            assert target_name != "Root"
            if path == "translation":
                assert target_name == "Hips"
                assert animation["name"] not in translations
                translations[animation["name"]] = (animation, channel)
    assert set(translations) == HIPS_TRANSLATION_CLIPS
    for name in ("SitIdle", "WeaponIdle", "Aim"):
        animation, channel = translations[name]
        sampler = animation["samplers"][channel["sampler"]]
        values = _accessor(document, binary, sampler["output"])
        assert np.array_equal(values[0], values[-1])


@pytest.mark.parametrize("preset_name", ("Compact Chibi", "Balanced Chibi", "Big Head"))
def test_sit_idle_ground_hands_and_head_for_multiple_proportions(
    preset_name: str,
) -> None:
    skeleton, meshes, clips = _pose_pack(preset_name, ("SitIdle",))
    clip = clips["SitIdle"]
    for time in clip.tracks[0].times:
        world = evaluate_clip(skeleton, clip, float(time))
        posed = posed_mesh_vertices(skeleton, meshes, world)
        minima = [float(vertices[:, 1].min()) for vertices in posed.values()]
        assert min(minima) == pytest.approx(0.0, abs=4e-6)
        assert min(minima) >= -4e-6

        hips = _joint_position(skeleton, world, "Hips")
        head = world[skeleton.index("Head")]
        spine = world[skeleton.index("Spine")]
        assert head[2, 2] > 0.99
        assert spine[2, 2] > 0.94
        assert spine[2, 1] < -0.20
        for foot_name in ("Foot.L", "Foot.R"):
            assert _joint_position(skeleton, world, foot_name)[2] > hips[2] + 0.4
        for hand_name in ("Hand.L", "Hand.R"):
            hand = _joint_position(skeleton, world, hand_name)
            assert -0.02 <= hand[1] <= 0.18
            assert hand[2] < hips[2] - 0.18


@pytest.mark.parametrize("clip_name", ("WeaponIdle", "Aim"))
def test_rifle_poses_keep_both_hands_forward_and_head_clear(clip_name: str) -> None:
    skeleton, _, clips = _pose_pack("Compact Chibi", (clip_name,))
    clip = clips[clip_name]
    for time in clip.tracks[0].times:
        world = evaluate_clip(skeleton, clip, float(time))
        spine = _joint_position(skeleton, world, "Spine")
        head = _joint_position(skeleton, world, "Head")
        left = _joint_position(skeleton, world, "Hand.L")
        right = _joint_position(skeleton, world, "Hand.R")
        assert left[2] > spine[2] + 0.4
        assert right[2] > spine[2] + 0.4
        assert left[2] > right[2]
        assert left[1] < head[1]
        assert right[1] < head[1]
        assert world[skeleton.index("Head")][2, 2] > 0.98


def test_weapon_idle_to_aim_is_a_coherent_raise() -> None:
    skeleton, _, clips = _pose_pack("Compact Chibi", ("WeaponIdle", "Aim"))
    idle_world = evaluate_clip(skeleton, clips["WeaponIdle"], 0.0)
    aim_world = evaluate_clip(skeleton, clips["Aim"], 0.0)
    for hand_name in ("Hand.L", "Hand.R"):
        assert _joint_position(skeleton, aim_world, hand_name)[1] > _joint_position(
            skeleton, idle_world, hand_name
        )[1]


@pytest.mark.parametrize("preset_name", ("Compact Chibi", "Balanced Chibi", "Big Head", "Legacy"))
@pytest.mark.parametrize("arm_width", (3, 4))
def test_heavy_attack_ground_clearance_and_ready_pose(preset_name: str, arm_width: int) -> None:
    settings = get_builtin_preset(preset_name)
    meshes = build_chibi_meshes(uv_table(arm_width), arm_width, settings)
    skeleton = build_skeleton(settings, arm_width)
    clip = build_animation_clips(skeleton, animation_names=("AttackHeavySide",), meshes=meshes)[0]
    # Check between exported samples too, where ground correction may drift.
    for time in np.linspace(0, clip.duration, 241):
        world = evaluate_clip(skeleton, clip, float(time))
        ready_world = evaluate_clip(skeleton, clip, 0.0)
        for name in ("Foot.L", "Foot.R"):
            assert world[skeleton.index(name)][0,3] == pytest.approx(ready_world[skeleton.index(name)][0,3],abs=2e-6)
        parts = posed_mesh_vertices(skeleton, meshes, evaluate_clip(skeleton, clip, float(time)))
        lowest = min(float(vertices[:, 1].min()) for vertices in parts.values())
        assert abs(lowest) < 0.001 * settings.overall_scale
    for track in clip.tracks:
        assert np.allclose(track.values[0], track.values[-1], atol=2e-6)


@pytest.mark.parametrize("preset_name", ("Compact Chibi", "Balanced Chibi", "Big Head", "Legacy"))
def test_attack_heavy_side_raises_then_strikes_down(preset_name: str) -> None:
    skeleton, _, clips = _pose_pack(preset_name, ("AttackHeavySide",))
    clip = clips["AttackHeavySide"]
    ready = evaluate_clip(skeleton, clip, 0.0)
    raised = evaluate_clip(skeleton, clip, 0.43)
    hit = evaluate_clip(skeleton, clip, 0.51)
    follow = evaluate_clip(skeleton, clip, 0.535)
    for hand in ("Hand.L", "Hand.R"):
        shoulder = hand.replace("Hand", "Arm")
        assert _joint_position(skeleton, raised, hand)[1] > _joint_position(skeleton, raised, shoulder)[1]
        assert _joint_position(skeleton, raised, hand)[1] > _joint_position(skeleton, ready, hand)[1] + 0.2
        assert _joint_position(skeleton, hit, hand)[1] < _joint_position(skeleton, raised, hand)[1] - 0.2
        assert _joint_position(skeleton, follow, hand)[1] < _joint_position(skeleton, hit, hand)[1]
        heights = [_joint_position(skeleton, evaluate_clip(skeleton, clip, float(t)), hand)[1]
                   for t in np.linspace(.43, .535, 40)]
        assert np.max(np.diff(heights)) < 0.001
    assert clip.extras["hitTime"] == 0.51


def test_heavy_legs_hold_still_after_impact() -> None:
    skeleton, _, clips = _pose_pack("Compact Chibi", ("AttackHeavySide",))
    clip = clips["AttackHeavySide"]
    impact = evaluate_clip(skeleton, clip, .51)
    for time in np.linspace(.51, .85, 80):
        world = evaluate_clip(skeleton, clip, float(time))
        for name in ("Leg.L", "Leg.R", "Foot.L", "Foot.R"):
            assert np.allclose(world[skeleton.index(name)], impact[skeleton.index(name)], atol=2e-6)


def test_heavy_hands_swing_together_and_recovery_has_no_bounce() -> None:
    skeleton, _, clips = _pose_pack("Compact Chibi", ("AttackHeavySide",))
    clip = clips["AttackHeavySide"]
    for start, end in ((.43, .48), (.48, .51), (.51, .535)):
        before = evaluate_clip(skeleton, clip, start)
        after = evaluate_clip(skeleton, clip, end)
        motions = [_joint_position(skeleton, after, hand) - _joint_position(skeleton, before, hand)
                   for hand in ("Hand.L", "Hand.R")]
        cosine = np.dot(*motions) / (np.linalg.norm(motions[0]) * np.linalg.norm(motions[1]))
        assert cosine > 0.9
    from chibi_skin_generator.animations import sample_track
    for track in clip.tracks:
        if track.path != "rotation":
            continue
        ready = track.values[0]
        distances = [2 * np.arccos(np.clip(abs(np.dot(sample_track(track, float(t)), ready)), 0, 1))
                     for t in np.linspace(.535, .85, 100)]
        assert np.max(np.diff(distances)) < 1e-5


@pytest.mark.parametrize("preset_name", ("Compact Chibi", "Balanced Chibi", "Big Head"))
def test_death_finishes_on_ground_without_recovery(preset_name: str) -> None:
    skeleton, meshes, clips = _pose_pack(preset_name, ("Death",))
    clip = clips["Death"]
    final_world = evaluate_clip(skeleton, clip, clip.duration)
    posed = posed_mesh_vertices(skeleton, meshes, final_world)
    all_vertices = np.concatenate(tuple(posed.values()))
    rest = posed_mesh_vertices(
        skeleton, meshes, tuple(joint.world_matrix for joint in skeleton.joints)
    )
    rest_height = float(np.concatenate(tuple(rest.values()))[:, 1].max())
    assert all_vertices[:, 1].min() == pytest.approx(0.0, abs=5e-6)
    assert all_vertices[:, 1].min() >= -5e-6
    assert all_vertices[:, 1].max() < rest_height * 0.8
    for track in clip.tracks:
        assert np.array_equal(track.values[-2], track.values[-1])


@pytest.mark.parametrize("clip_name", ("SitIdle", "WeaponIdle", "Aim"))
def test_new_loop_clips_are_exactly_seamless(clip_name: str) -> None:
    skeleton, _, clips = _pose_pack("Compact Chibi", (clip_name,))
    for track in clips[clip_name].tracks:
        assert np.array_equal(track.values[0], track.values[-1])


def test_full_pack_does_not_change_bind_mesh_uv_materials_or_bounds(
    animation_exports, combat_exports
) -> None:
    plain_document, plain_binary, _ = animation_exports["none"]
    (full_document, full_binary, _), _ = combat_exports
    assert full_document["skins"] == plain_document["skins"]
    assert full_document["materials"] == plain_document["materials"]
    assert full_document["textures"] == plain_document["textures"]
    assert full_document["samplers"] == plain_document["samplers"]
    positions = []
    for full_mesh, plain_mesh in zip(
        full_document["meshes"], plain_document["meshes"], strict=True
    ):
        full_primitive = full_mesh["primitives"][0]
        plain_primitive = plain_mesh["primitives"][0]
        assert full_primitive == plain_primitive
        for semantic in ("POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"):
            full_values = _accessor(
                full_document, full_binary, full_primitive["attributes"][semantic]
            )
            plain_values = _accessor(
                plain_document, plain_binary, plain_primitive["attributes"][semantic]
            )
            assert np.array_equal(full_values, plain_values)
        positions.append(
            _accessor(
                full_document,
                full_binary,
                full_primitive["attributes"]["POSITION"],
            )
        )
    all_positions = np.concatenate(positions)
    baseline = json.loads(
        Path(__file__).with_name("rest_pose_baselines.json").read_text(encoding="utf-8")
    )["Compact Chibi|4"]
    assert np.allclose(all_positions.min(axis=0), baseline["min"], atol=2e-6)
    assert np.allclose(all_positions.max(axis=0), baseline["max"], atol=2e-6)


def test_full_combat_pack_is_readable_by_gltf_parser(combat_exports) -> None:
    (_, _, result), _ = combat_exports
    loaded = trimesh.load(result.output_path, force="scene")
    assert isinstance(loaded, trimesh.Scene)
    assert len(loaded.geometry) == 12
