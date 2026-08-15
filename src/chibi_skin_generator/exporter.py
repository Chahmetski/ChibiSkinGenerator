"""Export chibi mesh data to a self-contained binary glTF file."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

import trimesh
from PIL import Image
from trimesh.exchange.gltf import export_glb as trimesh_export_glb
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from .geometry import REFERENCE_CHIBI, MeshData, ProportionPreset, build_chibi_meshes
from .skin_parser import ArmChoice, load_skin
from .uv_tables import uv_table

GLB_MAGIC = b"glTF"
GLB_VERSION = 2
JSON_CHUNK = 0x4E4F534A
NEAREST = 9728
CLAMP_TO_EDGE = 33071


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
        mesh = trimesh.Trimesh(
            vertices=data.vertices,
            faces=data.faces,
            process=False,
            validate=False,
        )
        mesh.vertex_normals = data.normals
        material = overlay_material if data.is_overlay else base_material
        mesh.visual = TextureVisuals(uv=data.uv, material=material)
        mesh.metadata["overlay"] = data.is_overlay
        scene.add_geometry(
            mesh,
            node_name=data.name,
            geom_name=data.name,
            transform=data.transform,
        )
    return scene


def _pixel_sampler_glb(blob: bytes) -> bytes:
    """Force nearest-neighbour sampling while preserving trimesh's BIN chunks."""
    if len(blob) < 20:
        raise ValueError("trimesh returned an invalid GLB file")
    magic, version, _ = struct.unpack_from("<4sII", blob, 0)
    if magic != GLB_MAGIC or version != GLB_VERSION:
        raise ValueError("trimesh returned an unsupported GLB file")

    chunks: list[tuple[int, bytes]] = []
    offset = 12
    while offset < len(blob):
        length, chunk_type = struct.unpack_from("<II", blob, offset)
        offset += 8
        chunks.append((chunk_type, blob[offset : offset + length]))
        offset += length

    json_index = next(
        (index for index, (chunk_type, _) in enumerate(chunks) if chunk_type == JSON_CHUNK),
        None,
    )
    if json_index is None:
        raise ValueError("GLB has no JSON chunk")

    document = json.loads(chunks[json_index][1].rstrip(b" \x00").decode("utf-8"))
    textures = document.get("textures", [])
    if textures:
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

    json_bytes = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)
    chunks[json_index] = (JSON_CHUNK, json_bytes)

    body = b"".join(
        struct.pack("<II", len(chunk), chunk_type) + chunk
        for chunk_type, chunk in chunks
    )
    return struct.pack("<4sII", GLB_MAGIC, GLB_VERSION, 12 + len(body)) + body


def export_glb(meshes: list[MeshData], image: Image.Image, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    blob = trimesh_export_glb(_scene(meshes, image), include_normals=True)
    if not isinstance(blob, bytes):
        raise TypeError("GLB exporter did not return binary data")
    blob = _pixel_sampler_glb(blob)

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
    proportions: ProportionPreset = REFERENCE_CHIBI,
) -> ExportResult:
    skin = load_skin(skin_path, arm_choice)
    output_dir = Path(output_directory)
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("Путь сохранения должен указывать на папку.")
    output_dir.mkdir(parents=True, exist_ok=True)

    meshes = build_chibi_meshes(
        uv_table(skin.arm_width),
        skin.arm_width,
        proportions,
    )
    output = output_dir / f"{skin.path.stem}_chibi.glb"
    export_glb(meshes, skin.image, output)
    return ExportResult(output.resolve(), skin.arm_model)
