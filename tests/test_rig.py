from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from chibi_skin_generator.exporter import (
    BIN_CHUNK,
    JSON_CHUNK,
    generate_diagnostic_model,
    generate_model,
)
from chibi_skin_generator.proportions import (
    DEFAULT_PRESET,
    builtin_preset_names,
    calculate_proportions,
    get_builtin_preset,
)
from chibi_skin_generator.rig import (
    JOINT_ORDER,
    JOINT_PARENTS,
    MESH_JOINTS,
    build_skeleton,
)


def _write_skin(path: Path) -> None:
    y, x = np.indices((64, 64))
    pixels = np.empty((64, 64, 4), dtype=np.uint8)
    pixels[..., 0] = (x * 3) % 256
    pixels[..., 1] = (y * 5) % 256
    pixels[..., 2] = 170
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


def _matrices(values: np.ndarray) -> np.ndarray:
    return values.reshape(-1, 4, 4).transpose(0, 2, 1)


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    matrix = np.eye(4)
    matrix[:3, 3] = node.get("translation", (0.0, 0.0, 0.0))
    return matrix


def _joint_world_matrices(document: dict) -> tuple[np.ndarray, ...]:
    nodes = document["nodes"]
    joint_nodes = document["skins"][0]["joints"]
    world: list[np.ndarray] = []
    for index, node_index in enumerate(joint_nodes):
        local = _node_matrix(nodes[node_index])
        parent = JOINT_PARENTS[index]
        world.append(local if parent is None else world[parent] @ local)
    return tuple(world)


def _mesh_parts(document: dict, binary: bytes) -> dict[str, dict[str, np.ndarray]]:
    result = {}
    for node in document["nodes"]:
        if "mesh" not in node:
            continue
        primitive = document["meshes"][node["mesh"]]["primitives"][0]
        result[node["name"]] = {
            semantic: _accessor(document, binary, accessor_index)
            for semantic, accessor_index in primitive["attributes"].items()
        }
    return result


def _skinned_parts(document: dict, binary: bytes) -> dict[str, np.ndarray]:
    skin = document["skins"][0]
    inverse_bind = _matrices(
        _accessor(document, binary, skin["inverseBindMatrices"])
    )
    joint_world = _joint_world_matrices(document)
    output = {}
    for name, attributes in _mesh_parts(document, binary).items():
        positions = attributes["POSITION"]
        joints = attributes["JOINTS_0"].astype(int)
        weights = attributes["WEIGHTS_0"]
        homogeneous = np.column_stack((positions, np.ones(len(positions))))
        transformed = np.zeros((len(positions), 4), dtype=np.float64)
        for vertex in range(len(positions)):
            for influence in range(4):
                weight = weights[vertex, influence]
                if weight:
                    joint = joints[vertex, influence]
                    transformed[vertex] += (
                        weight * (joint_world[joint] @ inverse_bind[joint] @ homogeneous[vertex])
                    )
        output[name] = transformed[:, :3]
    return output


@pytest.fixture()
def rigged_glb(tmp_path: Path) -> tuple[dict, bytes, Path]:
    skin_path = tmp_path / "rig_skin.png"
    _write_skin(skin_path)
    result = generate_model(skin_path, "Steve", tmp_path)
    document, binary = _read_glb(result.output_path)
    return document, binary, result.output_path


def test_single_skin_has_stable_joint_order_and_hierarchy(rigged_glb) -> None:
    document, _, _ = rigged_glb
    assert len(document["skins"]) == 1
    skin = document["skins"][0]
    nodes = document["nodes"]
    assert [nodes[index]["name"] for index in skin["joints"]] == list(JOINT_ORDER)
    assert nodes[skin["skeleton"]]["name"] == "Root"
    assert {nodes[index]["name"] for index in nodes[skin["skeleton"]].get("children", [])} == {
        "Hips"
    }
    for index, parent in enumerate(JOINT_PARENTS):
        if parent is None:
            continue
        parent_node = nodes[skin["joints"][parent]]
        assert skin["joints"][index] in parent_node.get("children", [])
    assert any(
        node.get("name") == "Skeleton" and skin["skeleton"] in node.get("children", [])
        for node in nodes
    )


def test_inverse_bind_matrices_match_rest_world_transforms(rigged_glb) -> None:
    document, binary, _ = rigged_glb
    skin = document["skins"][0]
    accessor = document["accessors"][skin["inverseBindMatrices"]]
    assert accessor["type"] == "MAT4"
    assert accessor["componentType"] == 5126
    assert accessor["count"] == len(JOINT_ORDER)
    inverse_bind = _matrices(_accessor(document, binary, skin["inverseBindMatrices"]))
    world = _joint_world_matrices(document)
    assert any(not np.allclose(matrix, np.eye(4)) for matrix in inverse_bind[1:])
    for matrix, joint_world in zip(inverse_bind, world, strict=True):
        assert np.allclose(joint_world @ matrix, np.eye(4), atol=2e-6)
        assert np.linalg.det(joint_world[:3, :3]) > 0.0


def test_every_mesh_is_skinned_with_valid_hard_weights(rigged_glb) -> None:
    document, binary, _ = rigged_glb
    parts = _mesh_parts(document, binary)
    assert len(parts) == 12
    mesh_nodes = [node for node in document["nodes"] if "mesh" in node]
    assert len(mesh_nodes) == 12
    assert all(node.get("skin") == 0 for node in mesh_nodes)
    for name, attributes in parts.items():
        assert {"POSITION", "NORMAL", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"} <= set(
            attributes
        )
        joints = attributes["JOINTS_0"]
        weights = attributes["WEIGHTS_0"]
        expected_joint = JOINT_ORDER.index(MESH_JOINTS[name])
        assert np.all(joints >= 0)
        assert np.all(joints < len(JOINT_ORDER))
        assert np.all(joints[:, 0] == expected_joint)
        assert np.all(joints[:, 1:] == 0)
        assert np.allclose(weights[:, 0], 1.0)
        assert np.allclose(weights[:, 1:], 0.0)
        assert np.allclose(weights.sum(axis=1), 1.0)
    for base, overlay in (
        ("Head", "Head_Overlay"),
        ("Body", "Body_Overlay"),
        ("Arm.L", "Arm_Overlay.L"),
        ("Arm.R", "Arm_Overlay.R"),
        ("Leg.L", "Leg_Overlay.L"),
        ("Leg.R", "Leg_Overlay.R"),
    ):
        assert np.array_equal(parts[base]["JOINTS_0"], parts[overlay]["JOINTS_0"])


@pytest.mark.parametrize("preset_name", builtin_preset_names())
@pytest.mark.parametrize("arm_pixels,arm_choice", ((3, "Alex"), (4, "Steve")))
def test_joint_names_are_stable_and_rest_bounds_are_preserved(
    tmp_path: Path, preset_name: str, arm_pixels: int, arm_choice: str
) -> None:
    skin_path = tmp_path / f"{preset_name}_{arm_choice}.png"
    _write_skin(skin_path)
    result = generate_model(
        skin_path, arm_choice, tmp_path / "out", get_builtin_preset(preset_name)
    )
    document, binary = _read_glb(result.output_path)
    skin = document["skins"][0]
    assert [document["nodes"][index]["name"] for index in skin["joints"]] == list(
        JOINT_ORDER
    )
    skinned = _skinned_parts(document, binary)
    all_positions = np.concatenate(list(skinned.values()))
    baselines = json.loads(
        (Path(__file__).with_name("rest_pose_baselines.json")).read_text(encoding="utf-8")
    )
    expected = baselines[f"{preset_name}|{arm_pixels}"]
    assert np.allclose(all_positions.min(axis=0), expected["min"], atol=2e-6)
    assert np.allclose(all_positions.max(axis=0), expected["max"], atol=2e-6)


def test_joint_pivots_are_derived_from_proportions() -> None:
    settings = get_builtin_preset(DEFAULT_PRESET)
    layout = calculate_proportions(settings, 4)
    parts = layout.by_name()
    skeleton = build_skeleton(settings, 4)
    positions = {joint.name: joint.world_matrix[:3, 3] for joint in skeleton.joints}
    leg_top = parts["Leg.L"].pivot[1] + parts["Leg.L"].size[1] / 2.0
    body_top = parts["Body"].pivot[1] + parts["Body"].size[1] / 2.0
    assert np.allclose(positions["Root"], (0.0, 0.0, 0.0))
    assert np.allclose(positions["Hips"], (0.0, leg_top, 0.0))
    assert np.allclose(positions["Spine"], (0.0, leg_top, 0.0))
    assert np.allclose(positions["Head"], (0.0, body_top, 0.0))
    for side in ("L", "R"):
        arm = parts[f"Arm.{side}"]
        leg = parts[f"Leg.{side}"]
        assert np.allclose(positions[f"Arm.{side}"], arm.pivot)
        assert np.allclose(positions[f"Leg.{side}"], (leg.pivot[0], leg_top, 0.0))
        angle = np.deg2rad(arm.rotation_degrees)
        local_x, local_y = arm.local_center[0], -arm.size[1]
        expected_hand = np.asarray(arm.pivot) + (
            np.cos(angle) * local_x - np.sin(angle) * local_y,
            np.sin(angle) * local_x + np.cos(angle) * local_y,
            0.0,
        )
        assert np.allclose(positions[f"Hand.{side}"], expected_hand)
        assert np.allclose(positions[f"Foot.{side}"], (leg.pivot[0], 0.0, 0.0))
        arm_axis = skeleton.joints[JOINT_ORDER.index(f"Arm.{side}")].world_matrix[:3, 1]
        leg_axis = skeleton.joints[JOINT_ORDER.index(f"Leg.{side}")].world_matrix[:3, 1]
        assert np.dot(arm_axis, positions[f"Hand.{side}"] - positions[f"Arm.{side}"]) > 0.0
        assert np.dot(leg_axis, positions[f"Foot.{side}"] - positions[f"Leg.{side}"]) > 0.0


def test_diagnostic_pose_moves_required_parts_and_keeps_overlays_together(
    tmp_path: Path,
) -> None:
    skin_path = tmp_path / "pose_skin.png"
    _write_skin(skin_path)
    rest = generate_model(skin_path, "Steve", tmp_path)
    diagnostic = generate_diagnostic_model(skin_path, "Steve", tmp_path)
    rest_document, rest_binary = _read_glb(rest.output_path)
    pose_document, pose_binary = _read_glb(diagnostic.output_path)
    assert "animations" not in pose_document
    rest_parts = _skinned_parts(rest_document, rest_binary)
    pose_parts = _skinned_parts(pose_document, pose_binary)
    for name in ("Head", "Arm.L", "Arm.R", "Leg.L"):
        assert not np.allclose(rest_parts[name], pose_parts[name])
    assert np.allclose(rest_parts["Body"], pose_parts["Body"])
    for base, overlay in (
        ("Head", "Head_Overlay"),
        ("Body", "Body_Overlay"),
        ("Arm.L", "Arm_Overlay.L"),
        ("Arm.R", "Arm_Overlay.R"),
        ("Leg.L", "Leg_Overlay.L"),
        ("Leg.R", "Leg_Overlay.R"),
    ):
        rest_delta = rest_parts[overlay].mean(axis=0) - rest_parts[base].mean(axis=0)
        pose_delta = pose_parts[overlay].mean(axis=0) - pose_parts[base].mean(axis=0)
        assert np.allclose(rest_delta, (0.0, 0.0, 0.0), atol=1e-6)
        assert np.allclose(pose_delta, (0.0, 0.0, 0.0), atol=1e-6)


def test_rigged_glb_keeps_materials_texture_and_is_parser_readable(rigged_glb) -> None:
    document, _, path = rigged_glb
    assert len(document["meshes"]) == 12
    materials = {material["name"]: material for material in document["materials"]}
    assert materials["MinecraftSkin_Base"]["alphaMode"] == "OPAQUE"
    assert materials["MinecraftSkin_Overlay"]["alphaMode"] == "MASK"
    assert materials["MinecraftSkin_Overlay"]["alphaCutoff"] == 0.5
    assert all(not material.get("doubleSided", False) for material in materials.values())
    assert all(material.get("alphaMode") != "BLEND" for material in materials.values())
    assert document.get("images") and all("bufferView" in image for image in document["images"])
    assert all(sampler["magFilter"] == 9728 for sampler in document["samplers"])
    assert all(sampler["minFilter"] == 9728 for sampler in document["samplers"])
    loaded = trimesh.load(path, force="scene")
    assert isinstance(loaded, trimesh.Scene)
    assert len(loaded.geometry) == 12
