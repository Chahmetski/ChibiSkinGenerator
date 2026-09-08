from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from chibi_skin_generator.exporter import JSON_CHUNK, PBR_LIT, generate_model
from chibi_skin_generator.proportions import builtin_preset_names, get_builtin_preset


EXPECTED_OBJECTS = {
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
BASE_OBJECTS = {"Head", "Body", "Arm.L", "Arm.R", "Leg.L", "Leg.R"}
BIN_CHUNK = 0x004E4942


def _write_test_skin(path: Path) -> None:
    pixels = np.zeros((64, 64, 4), dtype=np.uint8)
    y, x = np.indices((64, 64))
    pixels[:, :, 0] = (x * 4).astype(np.uint8)
    pixels[:, :, 1] = (y * 4).astype(np.uint8)
    pixels[:, :, 2] = 180
    pixels[:, :, 3] = 255
    # Include genuine alpha data; the exporter must retain it in embedded PNG.
    pixels[0:16, 32:64, 3] = 0
    Image.fromarray(pixels, mode="RGBA").save(path, format="PNG")


def _glb_chunks(blob: bytes) -> tuple[dict, bytes]:
    magic, version, total_length = struct.unpack_from("<4sII", blob, 0)
    assert magic == b"glTF"
    assert version == 2
    assert total_length == len(blob)

    offset = 12
    document = None
    binary = None
    while offset < len(blob):
        chunk_length, chunk_type = struct.unpack_from("<II", blob, offset)
        offset += 8
        chunk = blob[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == JSON_CHUNK:
            document = json.loads(chunk.rstrip(b" \x00").decode("utf-8"))
        elif chunk_type == BIN_CHUNK:
            binary = chunk
    assert document is not None, "JSON chunk not found"
    assert binary is not None, "BIN chunk not found"
    return document, binary


def _accessor(document: dict, binary: bytes, accessor_index: int) -> np.ndarray:
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    component_dtype = {
        5120: np.dtype("i1"),
        5121: np.dtype("u1"),
        5122: np.dtype("<i2"),
        5123: np.dtype("<u2"),
        5125: np.dtype("<u4"),
        5126: np.dtype("<f4"),
    }[accessor["componentType"]]
    component_count = {
        "SCALAR": 1,
        "VEC2": 2,
        "VEC3": 3,
        "VEC4": 4,
    }[accessor["type"]]
    count = accessor["count"]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride")
    if stride is None:
        values = np.frombuffer(
            binary,
            dtype=component_dtype,
            count=count * component_count,
            offset=offset,
        )
        return values.reshape(count, component_count)
    return np.ndarray(
        shape=(count, component_count),
        dtype=component_dtype,
        buffer=binary,
        offset=offset,
        strides=(stride, component_dtype.itemsize),
    ).copy()


def _node_transform_signature(node: dict) -> tuple:
    return (
        tuple(node.get("matrix", ())),
        tuple(node.get("translation", ())),
        tuple(node.get("rotation", ())),
        tuple(node.get("scale", ())),
    )


def test_exported_glb_has_named_meshes_and_embedded_pixel_texture(tmp_path: Path) -> None:
    skin_path = tmp_path / "generated_skin.png"
    output_dir = tmp_path / "output"
    _write_test_skin(skin_path)

    result = generate_model(skin_path, "Steve", output_dir)
    blob = result.output_path.read_bytes()
    document, binary = _glb_chunks(blob)

    assert result.output_path.name == "generated_skin_chibi.glb"
    assert result.arm_model == "Steve"
    assert {mesh.get("name") for mesh in document["meshes"]} == EXPECTED_OBJECTS
    assert EXPECTED_OBJECTS <= {node.get("name") for node in document["nodes"]}
    assert len(document["meshes"]) == 12

    materials = document["materials"]
    assert len(materials) == 2
    material_by_name = {material["name"]: material for material in materials}
    assert set(material_by_name) == {"MinecraftSkin_Base", "MinecraftSkin_Overlay"}

    base_material = material_by_name["MinecraftSkin_Base"]
    overlay_material = material_by_name["MinecraftSkin_Overlay"]
    assert base_material["alphaMode"] == "OPAQUE"
    assert "alphaCutoff" not in base_material
    assert base_material.get("doubleSided", False) is False
    assert overlay_material["alphaMode"] == "MASK"
    assert overlay_material["alphaCutoff"] == 0.5
    assert overlay_material.get("doubleSided", False) is False
    assert all(material.get("alphaMode", "OPAQUE") != "BLEND" for material in materials)
    assert document["extensionsUsed"] == ["KHR_materials_unlit"]
    assert all(
        material["extensions"]["KHR_materials_unlit"] == {}
        for material in materials
    )
    for material in materials:
        pbr = material["pbrMetallicRoughness"]
        assert "baseColorTexture" in pbr
        assert pbr["metallicFactor"] == 0.0

    material_names = {index: material["name"] for index, material in enumerate(materials)}
    mesh_by_name = {mesh["name"]: mesh for mesh in document["meshes"]}
    mesh_extents: dict[str, np.ndarray] = {}
    mesh_attributes: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for name, mesh in mesh_by_name.items():
        assert len(mesh["primitives"]) == 1
        primitive = mesh["primitives"][0]
        assert {"POSITION", "NORMAL", "TEXCOORD_0"} <= set(primitive["attributes"])
        assert "indices" in primitive
        expected_material = (
            "MinecraftSkin_Base" if name in BASE_OBJECTS else "MinecraftSkin_Overlay"
        )
        assert material_names[primitive["material"]] == expected_material

        positions = _accessor(document, binary, primitive["attributes"]["POSITION"])
        normals = _accessor(document, binary, primitive["attributes"]["NORMAL"])
        texture_uv = _accessor(document, binary, primitive["attributes"]["TEXCOORD_0"])
        indices = _accessor(document, binary, primitive["indices"]).reshape(-1, 3)
        assert len(positions) == 24
        assert len(normals) == 24
        assert np.allclose(np.linalg.norm(normals, axis=1), 1.0)
        mesh_extents[name] = np.ptp(positions, axis=0)
        mesh_attributes[name] = (positions, normals, texture_uv)

        mesh_center = positions.mean(axis=0)
        for triangle in indices:
            points = positions[triangle]
            face_normal = np.cross(points[1] - points[0], points[2] - points[0])
            face_normal /= np.linalg.norm(face_normal)
            outward = points.mean(axis=0) - mesh_center
            assert np.dot(face_normal, outward) > 0.0, f"Inward winding in {name}"
            assert np.allclose(normals[triangle], face_normal, atol=1e-6)

    nodes_by_name = {
        node.get("name"): node for node in document["nodes"] if "mesh" in node
    }
    overlay_pairs = {
        "Head_Overlay": "Head",
        "Body_Overlay": "Body",
        "Arm_Overlay.L": "Arm.L",
        "Arm_Overlay.R": "Arm.R",
        "Leg_Overlay.L": "Leg.L",
        "Leg_Overlay.R": "Leg.R",
    }
    for overlay, base in overlay_pairs.items():
        assert _node_transform_signature(nodes_by_name[overlay]) == _node_transform_signature(
            nodes_by_name[base]
        )
        assert np.allclose(
            mesh_attributes[overlay][0].mean(axis=0),
            mesh_attributes[base][0].mean(axis=0),
        )
        expected_growth = 0.0625 if overlay == "Head_Overlay" else 0.03125
        growth = mesh_extents[overlay] - mesh_extents[base]
        if base.startswith("Arm."):
            # Arm transforms are baked before skinning. Rotation projects the
            # uniform local offset onto both world X and Y axes.
            assert np.all(growth > 0.0)
            assert growth[2] == pytest.approx(expected_growth)
        else:
            assert np.allclose(growth, expected_growth)

    for head_name in ("Head", "Head_Overlay"):
        positions, normals, texture_uv = mesh_attributes[head_name]
        bottom = np.all(np.isclose(normals, (0.0, -1.0, 0.0)), axis=1)
        bottom_positions = positions[bottom]
        bottom_uv = texture_uv[bottom]
        assert len(bottom_positions) == 4

        rear = np.isclose(bottom_positions[:, 2], bottom_positions[:, 2].min())
        front = np.isclose(bottom_positions[:, 2], bottom_positions[:, 2].max())
        # trimesh converts its upward V to glTF's image-space V during export.
        # The rear edge must therefore sample the first texel row and the
        # front edge the last texel row of the 8-pixel bottom-face region.
        assert bottom_uv[rear, 1].mean() == pytest.approx(0.5 / 64)
        assert bottom_uv[front, 1].mean() == pytest.approx(7.5 / 64)

        model_left = np.isclose(bottom_positions[:, 0], bottom_positions[:, 0].max())
        model_right = np.isclose(bottom_positions[:, 0], bottom_positions[:, 0].min())
        assert bottom_uv[model_left, 0].mean() > bottom_uv[model_right, 0].mean()

    assert document.get("images")
    assert all("bufferView" in image and "uri" not in image for image in document["images"])
    assert b"\x89PNG\r\n\x1a\n" in blob

    assert document.get("samplers")
    assert all(sampler["magFilter"] == 9728 for sampler in document["samplers"])
    assert all(sampler["minFilter"] == 9728 for sampler in document["samplers"])
    assert all(sampler["wrapS"] == 33071 for sampler in document["samplers"])
    assert all(sampler["wrapT"] == 33071 for sampler in document["samplers"])


def test_pbr_lit_omits_unlit_extension_and_preserves_material_settings(
    tmp_path: Path,
) -> None:
    skin_path = tmp_path / "pbr_skin.png"
    _write_test_skin(skin_path)
    result = generate_model(
        skin_path,
        "Steve",
        tmp_path / "pbr_output",
        material_mode=PBR_LIT,
    )
    document, _ = _glb_chunks(result.output_path.read_bytes())
    assert "KHR_materials_unlit" not in document.get("extensionsUsed", [])
    for material in document["materials"]:
        assert "KHR_materials_unlit" not in material.get("extensions", {})
        pbr = material["pbrMetallicRoughness"]
        assert "baseColorTexture" in pbr
        assert pbr["metallicFactor"] == 0.0
        assert material.get("doubleSided", False) is False
    by_name = {material["name"]: material for material in document["materials"]}
    assert by_name["MinecraftSkin_Base"]["alphaMode"] == "OPAQUE"
    assert by_name["MinecraftSkin_Overlay"]["alphaMode"] == "MASK"
    assert by_name["MinecraftSkin_Overlay"]["alphaCutoff"] == 0.5
    assert all(sampler["magFilter"] == 9728 for sampler in document["samplers"])
    assert all(sampler["minFilter"] == 9728 for sampler in document["samplers"])


@pytest.mark.parametrize("preset_name", builtin_preset_names())
def test_every_builtin_preset_exports_valid_twelve_mesh_glb(
    tmp_path: Path, preset_name: str
) -> None:
    skin_path = tmp_path / f"{preset_name.replace(' ', '_')}.png"
    _write_test_skin(skin_path)
    result = generate_model(
        skin_path,
        "Steve",
        tmp_path / "exports",
        get_builtin_preset(preset_name),
    )
    document, _ = _glb_chunks(result.output_path.read_bytes())
    assert len(document["meshes"]) == 12
    assert {mesh["name"] for mesh in document["meshes"]} == EXPECTED_OBJECTS
    assert {material["name"] for material in document["materials"]} == {
        "MinecraftSkin_Base",
        "MinecraftSkin_Overlay",
    }
    for mesh in document["meshes"]:
        primitive = mesh["primitives"][0]
        assert "NORMAL" in primitive["attributes"]
        assert "indices" in primitive
