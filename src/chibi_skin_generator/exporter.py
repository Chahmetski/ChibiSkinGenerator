"""Export chibi mesh data to a self-contained binary glTF file."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.exchange.gltf import export_glb as trimesh_export_glb
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from .geometry import MeshData, build_chibi_meshes
from .proportions import DEFAULT_PRESET, ProportionSettings, get_builtin_preset
from .rig import (
    JOINT_ORDER,
    MESH_JOINTS,
    Skeleton,
    build_skeleton,
    diagnostic_local_matrices,
)
from .skin_parser import ArmChoice, load_skin
from .uv_tables import uv_table

GLB_MAGIC = b"glTF"
GLB_VERSION = 2
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
NEAREST = 9728
CLAMP_TO_EDGE = 33071
FLOAT = 5126
UNSIGNED_BYTE = 5121


@dataclass(frozen=True, slots=True)
class ExportResult:
    output_path: Path
    arm_model: str


def _materials(image: Image.Image) -> tuple[PBRMaterial, PBRMaterial]:
    common = {
        "baseColorFactor": (255, 255, 255, 255),
        "metallicFactor": 0.0,
        "roughnessFactor": 1.0,
        "doubleSided": False,
    }
    base = PBRMaterial(
        name="MinecraftSkin_Base",
        baseColorTexture=image.copy(),
        alphaMode="OPAQUE",
        **common,
    )
    overlay = PBRMaterial(
        name="MinecraftSkin_Overlay",
        baseColorTexture=image.copy(),
        alphaMode="MASK",
        alphaCutoff=0.5,
        **common,
    )
    return base, overlay


def _scene(meshes: list[MeshData], image: Image.Image) -> trimesh.Scene:
    scene = trimesh.Scene(base_frame="ChibiSkin")
    base_material, overlay_material = _materials(image)
    for data in meshes:
        transform = data.transform
        vertices = np.column_stack((data.vertices, np.ones(len(data.vertices))))
        world_vertices = (transform @ vertices.T).T[:, :3].astype(np.float32)
        world_normals = (transform[:3, :3] @ data.normals.T).T
        world_normals /= np.linalg.norm(world_normals, axis=1, keepdims=True)
        mesh = trimesh.Trimesh(
            vertices=world_vertices,
            faces=data.faces,
            process=False,
            validate=False,
        )
        mesh.vertex_normals = world_normals.astype(np.float32)
        material = overlay_material if data.is_overlay else base_material
        mesh.visual = TextureVisuals(uv=data.uv, material=material)
        mesh.metadata["overlay"] = data.is_overlay
        scene.add_geometry(
            mesh,
            node_name=data.name,
            geom_name=data.name,
        )
    return scene


def _read_glb(blob: bytes) -> tuple[dict, bytearray]:
    if len(blob) < 20:
        raise ValueError("trimesh returned an invalid GLB file")
    magic, version, total_length = struct.unpack_from("<4sII", blob, 0)
    if magic != GLB_MAGIC or version != GLB_VERSION:
        raise ValueError("trimesh returned an unsupported GLB file")
    if total_length != len(blob):
        raise ValueError("trimesh returned a truncated GLB file")

    document: dict | None = None
    binary: bytes | None = None
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
    if document is None:
        raise ValueError("GLB has no JSON chunk")
    if binary is None:
        raise ValueError("GLB has no BIN chunk")
    logical_length = document["buffers"][0]["byteLength"]
    return document, bytearray(binary[:logical_length])


def _write_glb(document: dict, binary: bytearray) -> bytes:
    document["buffers"][0]["byteLength"] = len(binary)
    json_bytes = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)
    binary_bytes = bytes(binary) + b"\x00" * ((-len(binary)) % 4)
    body = (
        struct.pack("<II", len(json_bytes), JSON_CHUNK)
        + json_bytes
        + struct.pack("<II", len(binary_bytes), BIN_CHUNK)
        + binary_bytes
    )
    return struct.pack("<4sII", GLB_MAGIC, GLB_VERSION, 12 + len(body)) + body


def _pixel_sampler(document: dict) -> None:
    """Force nearest-neighbour sampling for the embedded pixel texture."""
    textures = document.get("textures", [])
    if not textures:
        return
    samplers = document.setdefault("samplers", [])
    if not samplers:
        samplers.append({})
    for sampler in samplers:
        sampler.update(
            {
                "magFilter": NEAREST,
                "minFilter": NEAREST,
                "wrapS": CLAMP_TO_EDGE,
                "wrapT": CLAMP_TO_EDGE,
            }
        )
    for texture in textures:
        texture["sampler"] = texture.get("sampler", 0)


def _append_accessor(
    document: dict,
    binary: bytearray,
    payload: bytes,
    *,
    component_type: int,
    accessor_type: str,
    count: int,
) -> int:
    binary.extend(b"\x00" * ((-len(binary)) % 4))
    byte_offset = len(binary)
    binary.extend(payload)
    view_index = len(document.setdefault("bufferViews", []))
    document["bufferViews"].append(
        {"buffer": 0, "byteOffset": byte_offset, "byteLength": len(payload)}
    )
    accessor_index = len(document.setdefault("accessors", []))
    document["accessors"].append(
        {
            "bufferView": view_index,
            "componentType": component_type,
            "count": count,
            "type": accessor_type,
        }
    )
    return accessor_index


def _matrix_to_gltf(matrix: np.ndarray) -> list[float]:
    """glTF matrices are serialized column-major."""
    return np.asarray(matrix, dtype=np.float64).T.reshape(-1).tolist()


def _add_skinning(
    document: dict,
    binary: bytearray,
    skeleton: Skeleton,
    *,
    diagnostic_pose: bool,
) -> None:
    mesh_nodes = {
        node["name"]: node
        for node in document.get("nodes", [])
        if "mesh" in node and node.get("name") in MESH_JOINTS
    }
    if set(mesh_nodes) != set(MESH_JOINTS):
        missing = sorted(set(MESH_JOINTS) - set(mesh_nodes))
        raise ValueError(f"GLB is missing mesh nodes required by the rig: {missing}")

    for mesh_name, node in mesh_nodes.items():
        primitive = document["meshes"][node["mesh"]]["primitives"][0]
        vertex_count = document["accessors"][primitive["attributes"]["POSITION"]]["count"]
        joint_index = skeleton.index(MESH_JOINTS[mesh_name])
        joints = np.zeros((vertex_count, 4), dtype=np.uint8)
        joints[:, 0] = joint_index
        weights = np.zeros((vertex_count, 4), dtype="<f4")
        weights[:, 0] = 1.0
        primitive["attributes"]["JOINTS_0"] = _append_accessor(
            document,
            binary,
            joints.tobytes(),
            component_type=UNSIGNED_BYTE,
            accessor_type="VEC4",
            count=vertex_count,
        )
        primitive["attributes"]["WEIGHTS_0"] = _append_accessor(
            document,
            binary,
            weights.tobytes(),
            component_type=FLOAT,
            accessor_type="VEC4",
            count=vertex_count,
        )
        node["skin"] = 0

    inverse_bind = skeleton.inverse_bind_matrices
    inverse_bind_accessor = _append_accessor(
        document,
        binary,
        inverse_bind.transpose(0, 2, 1).astype("<f4").tobytes(),
        component_type=FLOAT,
        accessor_type="MAT4",
        count=len(skeleton.joints),
    )

    local_matrices = (
        diagnostic_local_matrices(skeleton)
        if diagnostic_pose
        else tuple(joint.local_matrix for joint in skeleton.joints)
    )
    first_joint_node = len(document["nodes"])
    joint_nodes = []
    for index, joint in enumerate(skeleton.joints):
        node = {"name": joint.name, "matrix": _matrix_to_gltf(local_matrices[index])}
        children = [
            first_joint_node + child_index
            for child_index, candidate in enumerate(skeleton.joints)
            if candidate.parent == index
        ]
        if children:
            node["children"] = children
        joint_nodes.append(node)
    document["nodes"].extend(joint_nodes)

    skeleton_group = len(document["nodes"])
    document["nodes"].append(
        {"name": "Skeleton", "children": [first_joint_node]}
    )
    scene_index = document.get("scene", 0)
    document["scenes"][scene_index].setdefault("nodes", []).append(skeleton_group)
    joint_indices = [first_joint_node + index for index in range(len(JOINT_ORDER))]
    document["skins"] = [
        {
            "name": "ChibiSkinRig",
            "joints": joint_indices,
            "inverseBindMatrices": inverse_bind_accessor,
            "skeleton": first_joint_node,
        }
    ]


def _finalize_glb(blob: bytes, skeleton: Skeleton, *, diagnostic_pose: bool) -> bytes:
    document, binary = _read_glb(blob)
    _pixel_sampler(document)
    _add_skinning(document, binary, skeleton, diagnostic_pose=diagnostic_pose)
    return _write_glb(document, binary)


def export_glb(
    meshes: list[MeshData],
    image: Image.Image,
    output_path: str | Path,
    skeleton: Skeleton,
    *,
    diagnostic_pose: bool = False,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    blob = trimesh_export_glb(_scene(meshes, image), include_normals=True)
    if not isinstance(blob, bytes):
        raise TypeError("GLB exporter did not return binary data")
    blob = _finalize_glb(blob, skeleton, diagnostic_pose=diagnostic_pose)

    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        temporary.write_bytes(blob)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def generate_model(
    skin_path: str | Path,
    arm_choice: ArmChoice,
    output_directory: str | Path,
    proportions: ProportionSettings | None = None,
) -> ExportResult:
    skin = load_skin(skin_path, arm_choice)
    output_dir = Path(output_directory)
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("Путь сохранения должен указывать на папку.")
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = proportions or get_builtin_preset(DEFAULT_PRESET)
    meshes = build_chibi_meshes(
        uv_table(skin.arm_width),
        skin.arm_width,
        settings,
    )
    skeleton = build_skeleton(settings, skin.arm_width)
    output = output_dir / f"{skin.path.stem}_chibi.glb"
    export_glb(meshes, skin.image, output, skeleton)
    return ExportResult(output.resolve(), skin.arm_model)


def generate_diagnostic_model(
    skin_path: str | Path,
    arm_choice: ArmChoice,
    output_directory: str | Path,
    proportions: ProportionSettings | None = None,
) -> ExportResult:
    """Export the internal rig-check pose without adding an animation."""
    skin = load_skin(skin_path, arm_choice)
    output_dir = Path(output_directory)
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("Путь сохранения должен указывать на папку.")
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = proportions or get_builtin_preset(DEFAULT_PRESET)
    meshes = build_chibi_meshes(uv_table(skin.arm_width), skin.arm_width, settings)
    skeleton = build_skeleton(settings, skin.arm_width)
    output = output_dir / f"{skin.path.stem}_chibi_rig_test.glb"
    export_glb(meshes, skin.image, output, skeleton, diagnostic_pose=True)
    return ExportResult(output.resolve(), skin.arm_model)
