"""Deterministic in-place clips and FK evaluation for the stable chibi skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np

from .geometry import MeshData
from .rig import MESH_JOINTS, Skeleton, world_matrices_from_locals


@dataclass(frozen=True, slots=True)
class AnimationTrack:
    joint_name: str
    times: np.ndarray
    values: np.ndarray
    path: str = "rotation"

    @property
    def rotations(self) -> np.ndarray:
        if self.path != "rotation":
            raise AttributeError("This animation track does not contain rotations.")
        return self.values


@dataclass(frozen=True, slots=True)
class AnimationClip:
    name: str
    duration: float
    tracks: tuple[AnimationTrack, ...]
    extras: Mapping[str, object]


def normalize_quaternion(quaternion: np.ndarray) -> np.ndarray:
    value = np.asarray(quaternion, dtype=np.float64)
    length = float(np.linalg.norm(value))
    if length == 0.0:
        raise ValueError("A rotation quaternion cannot have zero length.")
    return value / length


def quaternion_multiply(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Compose glTF XYZW quaternions as left rotation followed by local right."""
    left = normalize_quaternion(left)
    right = normalize_quaternion(right)
    left_xyz, left_w = left[:3], left[3]
    right_xyz, right_w = right[:3], right[3]
    xyz = (
        left_w * right_xyz
        + right_w * left_xyz
        + np.cross(left_xyz, right_xyz)
    )
    w = left_w * right_w - float(np.dot(left_xyz, right_xyz))
    return normalize_quaternion(np.append(xyz, w))


def axis_angle_quaternion(axis: str, degrees: float) -> np.ndarray:
    half_angle = np.deg2rad(degrees) / 2.0
    sine = float(np.sin(half_angle))
    cosine = float(np.cos(half_angle))
    if axis == "x":
        return np.asarray((sine, 0.0, 0.0, cosine), dtype=np.float64)
    if axis == "y":
        return np.asarray((0.0, sine, 0.0, cosine), dtype=np.float64)
    if axis == "z":
        return np.asarray((0.0, 0.0, sine, cosine), dtype=np.float64)
    raise ValueError(f"Unknown quaternion axis: {axis}")


def matrix_quaternion(matrix: np.ndarray) -> np.ndarray:
    """Convert a rigid 3x3/4x4 matrix to a normalized glTF XYZW quaternion."""
    rotation = np.asarray(matrix, dtype=np.float64)[:3, :3]
    trace = float(np.trace(rotation))
    if trace > 0.0:
        scale = np.sqrt(trace + 1.0) * 2.0
        quaternion = np.asarray(
            (
                (rotation[2, 1] - rotation[1, 2]) / scale,
                (rotation[0, 2] - rotation[2, 0]) / scale,
                (rotation[1, 0] - rotation[0, 1]) / scale,
                0.25 * scale,
            )
        )
    else:
        diagonal = np.diag(rotation)
        largest = int(np.argmax(diagonal))
        if largest == 0:
            scale = np.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2.0
            quaternion = np.asarray(
                (
                    0.25 * scale,
                    (rotation[0, 1] + rotation[1, 0]) / scale,
                    (rotation[0, 2] + rotation[2, 0]) / scale,
                    (rotation[2, 1] - rotation[1, 2]) / scale,
                )
            )
        elif largest == 1:
            scale = np.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2.0
            quaternion = np.asarray(
                (
                    (rotation[0, 1] + rotation[1, 0]) / scale,
                    0.25 * scale,
                    (rotation[1, 2] + rotation[2, 1]) / scale,
                    (rotation[0, 2] - rotation[2, 0]) / scale,
                )
            )
        else:
            scale = np.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2.0
            quaternion = np.asarray(
                (
                    (rotation[0, 2] + rotation[2, 0]) / scale,
                    (rotation[1, 2] + rotation[2, 1]) / scale,
                    0.25 * scale,
                    (rotation[1, 0] - rotation[0, 1]) / scale,
                )
            )
    return normalize_quaternion(quaternion)


def _delta_quaternion(rotations: tuple[tuple[str, float], ...]) -> np.ndarray:
    result = np.asarray((0.0, 0.0, 0.0, 1.0), dtype=np.float64)
    for axis, degrees in rotations:
        result = quaternion_multiply(result, axis_angle_quaternion(axis, degrees))
    return result


def _track(
    skeleton: Skeleton,
    joint_name: str,
    times: np.ndarray,
    deltas: tuple[tuple[tuple[str, float], ...], ...],
    *,
    loop: bool = True,
) -> AnimationTrack:
    rest = matrix_quaternion(skeleton.joints[skeleton.index(joint_name)].local_matrix)
    rotations = np.asarray(
        [quaternion_multiply(rest, _delta_quaternion(delta)) for delta in deltas],
        dtype=np.float64,
    )
    for index in range(1, len(rotations)):
        if float(np.dot(rotations[index - 1], rotations[index])) < 0.0:
            rotations[index] *= -1.0
    if loop:
        rotations[-1] = rotations[0]
    return AnimationTrack(
        joint_name,
        np.asarray(times, dtype=np.float32),
        rotations.astype(np.float32),
    )


def _translation_track(
    joint_name: str,
    times: np.ndarray,
    translations: np.ndarray,
) -> AnimationTrack:
    values = np.asarray(translations, dtype=np.float32)
    if values.shape != (len(times), 3):
        raise ValueError("Translation tracks must contain one VEC3 per keyframe.")
    return AnimationTrack(
        joint_name,
        np.asarray(times, dtype=np.float32),
        values,
        "translation",
    )


def _quaternion_matrix(quaternion: np.ndarray) -> np.ndarray:
    x, y, z, w = normalize_quaternion(quaternion)
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    )
    return matrix


def sample_track(track: AnimationTrack, time: float) -> np.ndarray:
    """Evaluate a LINEAR glTF track at ``time`` using normalized quaternion lerp."""
    times = np.asarray(track.times, dtype=np.float64)
    if time <= float(times[0]):
        return np.asarray(track.values[0], dtype=np.float64)
    if time >= float(times[-1]):
        return np.asarray(track.values[-1], dtype=np.float64)
    upper = int(np.searchsorted(times, time, side="right"))
    lower = upper - 1
    fraction = (time - float(times[lower])) / float(times[upper] - times[lower])
    first = np.asarray(track.values[lower], dtype=np.float64)
    second = np.asarray(track.values[upper], dtype=np.float64)
    value = first * (1.0 - fraction) + second * fraction
    return normalize_quaternion(value) if track.path == "rotation" else value


def evaluate_tracks(
    skeleton: Skeleton,
    tracks: Sequence[AnimationTrack],
    time: float,
) -> tuple[np.ndarray, ...]:
    """Return world joint matrices for a pose sampled from animation tracks."""
    local_matrices = [joint.local_matrix.copy() for joint in skeleton.joints]
    for track in tracks:
        joint_index = skeleton.index(track.joint_name)
        value = sample_track(track, time)
        if track.path == "rotation":
            local_matrices[joint_index][:3, :3] = _quaternion_matrix(value)[:3, :3]
        elif track.path == "translation":
            local_matrices[joint_index][:3, 3] = value
        else:
            raise ValueError(f"Unsupported pose track path: {track.path}")
    return world_matrices_from_locals(tuple(local_matrices))


def evaluate_clip(
    skeleton: Skeleton,
    clip: AnimationClip,
    time: float,
) -> tuple[np.ndarray, ...]:
    """Evaluate a complete clip in the same local-to-world order as glTF."""
    return evaluate_tracks(skeleton, clip.tracks, time)


def posed_mesh_vertices(
    skeleton: Skeleton,
    meshes: Sequence[MeshData],
    world_matrices: Sequence[np.ndarray],
    *,
    include_overlay: bool = False,
) -> dict[str, np.ndarray]:
    """Apply the project's hard skin weights and return world-space vertices."""
    inverse_bind = skeleton.inverse_bind_matrices.astype(np.float64)
    result: dict[str, np.ndarray] = {}
    for mesh in meshes:
        if mesh.is_overlay and not include_overlay:
            continue
        rest_vertices = np.column_stack((mesh.vertices, np.ones(len(mesh.vertices))))
        rest_world = (mesh.transform @ rest_vertices.T).T
        joint_index = skeleton.index(MESH_JOINTS[mesh.name])
        posed = (
            np.asarray(world_matrices[joint_index], dtype=np.float64)
            @ inverse_bind[joint_index]
            @ rest_world.T
        ).T
        result[mesh.name] = posed[:, :3]
    return result


def _grounded_hips_translation(
    skeleton: Skeleton,
    meshes: Sequence[MeshData],
    rotation_tracks: tuple[AnimationTrack, ...],
    time: float,
    *,
    horizontal_offset: tuple[float, float] = (0.0, 0.0),
) -> np.ndarray:
    world = evaluate_tracks(skeleton, rotation_tracks, time)
    posed = posed_mesh_vertices(skeleton, meshes, world)
    if not posed:
        raise ValueError("Grounded animation requires base mesh vertices.")
    lowest = min(float(vertices[:, 1].min()) for vertices in posed.values())
    bind_translation = skeleton.joints[skeleton.index("Hips")].local_matrix[:3, 3]
    x_offset, z_offset = horizontal_offset
    return np.asarray(
        bind_translation + (x_offset, -lowest, z_offset), dtype=np.float32
    )


def _lowered_hips_values(
    skeleton: Skeleton,
    times: np.ndarray,
    fractions: Sequence[float],
) -> np.ndarray:
    """Create proportion-derived absolute Hips translations for crouched clips."""
    bind = skeleton.joints[skeleton.index("Hips")].local_matrix[:3, 3]
    leg_height = float(bind[1])
    return np.asarray(
        [bind + (0.0, -leg_height * fraction, 0.0) for fraction in fractions],
        dtype=np.float32,
    )


def idle_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.6, 1.2, 1.8, 2.4), dtype=np.float32)
    wave = (0.0, 1.0, 0.0, -1.0, 0.0)
    tracks = (
        _track(skeleton, "Head", times, tuple((("y", 1.25 * phase),) for phase in wave)),
        _track(skeleton, "Spine", times, tuple((("z", 0.5 * phase),) for phase in wave)),
        _track(
            skeleton,
            "Arm.L",
            times,
            tuple((("x", 1.75 * phase), ("z", 1.0 * phase)) for phase in wave),
        ),
        _track(
            skeleton,
            "Arm.R",
            times,
            tuple((("x", -1.75 * phase), ("z", -1.0 * phase)) for phase in wave),
        ),
    )
    return AnimationClip("Idle", 2.4, tracks, MappingProxyType({"loop": True}))


def walk_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.25, 0.5, 0.75, 1.0), dtype=np.float32)
    phase = (1.0, 0.0, -1.0, 0.0, 1.0)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("z", 1.5 * value),) for value in phase)),
        _track(skeleton, "Arm.L", times, tuple((("x", -25.0 * value),) for value in phase)),
        _track(skeleton, "Arm.R", times, tuple((("x", 25.0 * value),) for value in phase)),
        _track(skeleton, "Leg.L", times, tuple((("x", 30.0 * value),) for value in phase)),
        _track(skeleton, "Leg.R", times, tuple((("x", -30.0 * value),) for value in phase)),
    )
    return AnimationClip(
        "Walk",
        1.0,
        tracks,
        MappingProxyType({"loop": True, "suggestedSpeed": 1.0, "inPlace": True}),
    )


def run_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.15, 0.3, 0.45, 0.6), dtype=np.float32)
    phase = (1.0, 0.0, -1.0, 0.0, 1.0)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", 10.0), ("z", 2.0 * value)) for value in phase)),
        _track(skeleton, "Head", times, tuple((("x", -10.0), ("z", -1.0 * value)) for value in phase)),
        _track(skeleton, "Arm.L", times, tuple((("x", -38.0 * value),) for value in phase)),
        _track(skeleton, "Arm.R", times, tuple((("x", 38.0 * value),) for value in phase)),
        _track(skeleton, "Leg.L", times, tuple((("x", 45.0 * value),) for value in phase)),
        _track(skeleton, "Leg.R", times, tuple((("x", -45.0 * value),) for value in phase)),
    )
    return AnimationClip(
        "Run",
        0.6,
        tracks,
        MappingProxyType({"loop": True, "inPlace": True}),
    )


def jump_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.12, 0.25, 0.35, 0.45), dtype=np.float32)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", value),) for value in (0.0, 12.0, 5.0, -5.0, -5.0)), loop=False),
        _track(skeleton, "Head", times, tuple((("x", value),) for value in (0.0, -8.0, -3.0, 5.0, 5.0)), loop=False),
        _track(skeleton, "Arm.L", times, tuple((("x", value),) for value in (0.0, -30.0, 55.0, 70.0, 55.0)), loop=False),
        _track(skeleton, "Arm.R", times, tuple((("x", value),) for value in (0.0, -30.0, 55.0, 70.0, 55.0)), loop=False),
        _track(skeleton, "Leg.L", times, tuple((("x", value),) for value in (0.0, 15.0, -20.0, -30.0, -25.0)), loop=False),
        _track(skeleton, "Leg.R", times, tuple((("x", value),) for value in (0.0, 15.0, -20.0, -30.0, -25.0)), loop=False),
    )
    return AnimationClip("Jump", 0.45, tracks, MappingProxyType({"loop": False, "inPlace": True}))


def fall_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.25, 0.5, 0.75, 1.0), dtype=np.float32)
    wave = (0.0, 1.0, 0.0, -1.0, 0.0)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", -4.0), ("z", 2.0 * value)) for value in wave)),
        _track(skeleton, "Head", times, tuple((("x", 4.0), ("z", -1.0 * value)) for value in wave)),
        _track(skeleton, "Arm.L", times, tuple((("x", 45.0 + 3.0 * value), ("z", -6.0)) for value in wave)),
        _track(skeleton, "Arm.R", times, tuple((("x", 45.0 - 3.0 * value), ("z", 6.0)) for value in wave)),
        _track(skeleton, "Leg.L", times, tuple((("x", 16.0 + 3.0 * value), ("z", -7.0)) for value in wave)),
        _track(skeleton, "Leg.R", times, tuple((("x", 13.0 - 3.0 * value), ("z", 7.0)) for value in wave)),
    )
    return AnimationClip("Fall", 1.0, tracks, MappingProxyType({"loop": True, "inPlace": True}))


def land_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.08, 0.18, 0.28, 0.35), dtype=np.float32)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", value),) for value in (-4.0, 18.0, 14.0, 5.0, 0.0)), loop=False),
        _track(skeleton, "Head", times, tuple((("x", value),) for value in (4.0, -10.0, -7.0, -2.0, 0.0)), loop=False),
        _track(skeleton, "Arm.L", times, tuple((("x", value),) for value in (35.0, -20.0, -12.0, -5.0, 0.0)), loop=False),
        _track(skeleton, "Arm.R", times, tuple((("x", value),) for value in (35.0, -20.0, -12.0, -5.0, 0.0)), loop=False),
        _track(skeleton, "Leg.L", times, tuple((("x", value),) for value in (-15.0, 22.0, 16.0, 6.0, 0.0)), loop=False),
        _track(skeleton, "Leg.R", times, tuple((("x", value),) for value in (-15.0, 22.0, 16.0, 6.0, 0.0)), loop=False),
    )
    return AnimationClip("Land", 0.35, tracks, MappingProxyType({"loop": False, "inPlace": True}))


def sit_idle_clip(
    skeleton: Skeleton,
    meshes: Sequence[MeshData],
) -> AnimationClip:
    times = np.asarray((0.0, 0.5, 1.0, 1.5, 2.0), dtype=np.float32)
    wave = (0.0, 1.0, 0.0, -1.0, 0.0)
    # The rig faces +Z. Local +X bends a down-pointing limb toward +Z,
    # while -X tilts the upright torso backward. These deltas deliberately
    # preserve one coherent facing direction for head, torso and legs.
    rotation_tracks = (
        _track(skeleton, "Spine", times, tuple((("x", -15.0 + 0.6 * value),) for value in wave)),
        _track(skeleton, "Head", times, tuple((("x", 15.0 - 0.45 * value),) for value in wave)),
        _track(skeleton, "Arm.L", times, tuple((("x", -30.0 + 0.7 * value), ("z", -10.0)) for value in wave)),
        _track(skeleton, "Arm.R", times, tuple((("x", -30.0 - 0.7 * value), ("z", 10.0)) for value in wave)),
        _track(skeleton, "Leg.L", times, tuple((("x", -92.0), ("z", -4.0)) for _ in wave)),
        _track(skeleton, "Leg.R", times, tuple((("x", -92.0), ("z", 4.0)) for _ in wave)),
    )
    hips_values = np.asarray(
        [
            _grounded_hips_translation(skeleton, meshes, rotation_tracks, float(time))
            for time in times
        ],
        dtype=np.float32,
    )
    hips_values[-1] = hips_values[0]
    tracks = rotation_tracks + (_translation_track("Hips", times, hips_values),)
    return AnimationClip("SitIdle", 2.0, tracks, MappingProxyType({"loop": True, "inPlace": True}))


def zombie_walk_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.3, 0.6, 0.9, 1.2), dtype=np.float32)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", pitch), ("z", sway)) for pitch, sway in ((6.0, 7.0), (8.0, -3.0), (5.0, -7.0), (7.0, 4.0), (6.0, 7.0)))),
        _track(skeleton, "Head", times, tuple((("x", pitch), ("y", yaw), ("z", roll)) for pitch, yaw, roll in ((-3.0, -3.0, -4.0), (-5.0, 2.0, 1.0), (-2.0, 4.0, 4.0), (-4.0, -2.0, -2.0), (-3.0, -3.0, -4.0)))),
        _track(skeleton, "Arm.L", times, tuple((("x", value), ("z", side)) for value, side in ((82.0, -4.0), (86.0, -3.0), (80.0, -5.0), (84.0, -2.0), (82.0, -4.0)))),
        _track(skeleton, "Arm.R", times, tuple((("x", value), ("z", side)) for value, side in ((78.0, 4.0), (81.0, 2.0), (85.0, 5.0), (79.0, 3.0), (78.0, 4.0)))),
        _track(skeleton, "Leg.L", times, tuple((("x", value),) for value in (22.0, -4.0, -18.0, 3.0, 22.0))),
        _track(skeleton, "Leg.R", times, tuple((("x", value),) for value in (-13.0, 5.0, 20.0, -6.0, -13.0))),
    )
    return AnimationClip("ZombieWalk", 1.2, tracks, MappingProxyType({"loop": True, "inPlace": True}))


def hit_react_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.06, 0.14, 0.24, 0.35), dtype=np.float32)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", value),) for value in (0.0, -18.0, -25.0, -10.0, 0.0)), loop=False),
        _track(skeleton, "Head", times, tuple((("x", value),) for value in (0.0, 8.0, 15.0, 5.0, 0.0)), loop=False),
        _track(skeleton, "Arm.L", times, tuple((("x", value), ("z", side)) for value, side in ((0.0, 0.0), (-25.0, -12.0), (-40.0, -20.0), (-12.0, -6.0), (0.0, 0.0))), loop=False),
        _track(skeleton, "Arm.R", times, tuple((("x", value), ("z", side)) for value, side in ((0.0, 0.0), (-25.0, 12.0), (-40.0, 20.0), (-12.0, 6.0), (0.0, 0.0))), loop=False),
    )
    return AnimationClip("HitReact", 0.35, tracks, MappingProxyType({"loop": False, "inPlace": True}))


def aim_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.375, 0.75, 1.125, 1.5), dtype=np.float32)
    wave = (0.0, 1.0, 0.0, -1.0, 0.0)
    rotations = (
        _track(skeleton, "Spine", times, tuple((("x", 6.0 + 0.35 * value), ("y", 12.0)) for value in wave)),
        _track(skeleton, "Head", times, tuple((("x", -6.0 - 0.25 * value), ("y", -12.0 + 0.25 * value)) for value in wave)),
        _track(skeleton, "Arm.R", times, tuple((("x", 56.0 + 0.45 * value), ("z", 7.0)) for value in wave)),
        _track(skeleton, "Arm.L", times, tuple((("x", 90.0 + 0.35 * value), ("z", -18.0)) for value in wave)),
        _track(skeleton, "Leg.L", times, tuple((("x", 4.0), ("z", -8.0)) for _ in wave)),
        _track(skeleton, "Leg.R", times, tuple((("x", 4.0), ("z", 8.0)) for _ in wave)),
    )
    hips = _lowered_hips_values(skeleton, times, (0.08, 0.085, 0.08, 0.075, 0.08))
    tracks = rotations + (_translation_track("Hips", times, hips),)
    return AnimationClip("Aim", 1.5, tracks, MappingProxyType({"loop": True, "inPlace": True}))


def weapon_idle_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.5, 1.0, 1.5, 2.0), dtype=np.float32)
    wave = (0.0, 1.0, 0.0, -1.0, 0.0)
    rotations = (
        _track(skeleton, "Spine", times, tuple((("x", 4.0 + 0.4 * value), ("y", 8.0)) for value in wave)),
        _track(skeleton, "Head", times, tuple((("x", -4.0 - 0.3 * value), ("y", -8.0 + 0.2 * value)) for value in wave)),
        _track(skeleton, "Arm.R", times, tuple((("x", 48.0 + 0.6 * value), ("z", 7.0)) for value in wave)),
        _track(skeleton, "Arm.L", times, tuple((("x", 74.0 + 0.5 * value), ("z", -17.0)) for value in wave)),
        _track(skeleton, "Leg.L", times, tuple((("x", 3.0), ("z", -7.0)) for _ in wave)),
        _track(skeleton, "Leg.R", times, tuple((("x", 3.0), ("z", 7.0)) for _ in wave)),
    )
    hips = _lowered_hips_values(skeleton, times, (0.055, 0.06, 0.055, 0.05, 0.055))
    tracks = rotations + (_translation_track("Hips", times, hips),)
    return AnimationClip("WeaponIdle", 2.0, tracks, MappingProxyType({"loop": True, "inPlace": True}))


def attack_one_hand_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.12, 0.24, 0.31, 0.4, 0.5), dtype=np.float32)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", pitch), ("y", yaw)) for pitch, yaw in ((0.0, 0.0), (-3.0, -10.0), (4.0, 12.0), (6.0, 15.0), (2.0, 5.0), (0.0, 0.0))), loop=False),
        _track(skeleton, "Head", times, tuple((("y", value),) for value in (0.0, 5.0, -5.0, -7.0, -2.0, 0.0)), loop=False),
        _track(skeleton, "Arm.R", times, tuple((("x", value),) for value in (0.0, -35.0, 88.0, 100.0, 45.0, 0.0)), loop=False),
        _track(skeleton, "Arm.L", times, tuple((("x", value),) for value in (0.0, 12.0, -10.0, -15.0, -5.0, 0.0)), loop=False),
    )
    return AnimationClip("AttackOneHand", 0.5, tracks, MappingProxyType({"loop": False, "inPlace": True}))


def attack_dual_daggers_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.12, 0.27, 0.42, 0.55, 0.612, 0.75, 0.9), dtype=np.float32)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", pitch), ("y", yaw)) for pitch, yaw in ((0.0, 0.0), (-3.0, -8.0), (5.0, 13.0), (1.0, 4.0), (-3.0, 8.0), (5.0, -13.0), (2.0, -5.0), (0.0, 0.0))), loop=False),
        _track(skeleton, "Arm.R", times, tuple((("x", value),) for value in (0.0, -30.0, 95.0, 35.0, 15.0, 25.0, 10.0, 0.0)), loop=False),
        _track(skeleton, "Arm.L", times, tuple((("x", value),) for value in (0.0, 15.0, -10.0, -25.0, -35.0, 100.0, 35.0, 0.0)), loop=False),
        _track(skeleton, "Head", times, tuple((("y", value),) for value in (0.0, 3.0, -5.0, -2.0, -3.0, 5.0, 2.0, 0.0)), loop=False),
    )
    return AnimationClip("AttackDualDaggers", 0.9, tracks, MappingProxyType({"loop": False, "inPlace": True}))


def attack_heavy_side_clip(skeleton: Skeleton) -> AnimationClip:
    times = np.asarray((0.0, 0.16, 0.34, 0.51, 0.68, 0.85), dtype=np.float32)
    tracks = (
        _track(skeleton, "Spine", times, tuple((("x", pitch), ("y", yaw), ("z", roll)) for pitch, yaw, roll in ((2.0, 0.0, 0.0), (3.0, -22.0, 5.0), (5.0, -28.0, 7.0), (10.0, 24.0, -8.0), (6.0, 10.0, -3.0), (1.0, 0.0, 0.0))), loop=False),
        _track(skeleton, "Head", times, tuple((("x", pitch), ("y", yaw)) for pitch, yaw in ((-2.0, 0.0), (-3.0, 16.0), (-4.0, 20.0), (-7.0, -18.0), (-4.0, -7.0), (-1.0, 0.0))), loop=False),
        _track(skeleton, "Arm.R", times, tuple((("x", pitch), ("z", side)) for pitch, side in ((30.0, 24.0), (34.0, 42.0), (42.0, 48.0), (88.0, -30.0), (62.0, -12.0), (12.0, 0.0))), loop=False),
        _track(skeleton, "Arm.L", times, tuple((("x", pitch), ("z", side)) for pitch, side in ((38.0, -18.0), (42.0, -12.0), (50.0, -15.0), (78.0, 28.0), (57.0, 12.0), (12.0, 0.0))), loop=False),
        _track(skeleton, "Leg.L", times, tuple((("x", pitch), ("z", -9.0)) for pitch in (4.0, 7.0, 9.0, 12.0, 8.0, 4.0)), loop=False),
        _track(skeleton, "Leg.R", times, tuple((("x", pitch), ("z", 9.0)) for pitch in (4.0, 7.0, 9.0, 12.0, 8.0, 4.0)), loop=False),
    )
    hips = _lowered_hips_values(skeleton, times, (0.04, 0.07, 0.09, 0.11, 0.07, 0.04))
    return AnimationClip(
        "AttackHeavySide",
        0.85,
        tracks + (_translation_track("Hips", times, hips),),
        MappingProxyType({"loop": False, "inPlace": True, "hitTime": 0.51}),
    )


def death_clip(skeleton: Skeleton, meshes: Sequence[MeshData]) -> AnimationClip:
    times = np.asarray((0.0, 0.12, 0.32, 0.62, 0.95, 1.15, 1.3), dtype=np.float32)
    rotations = (
        _track(skeleton, "Hips", times, tuple((("x", pitch), ("z", roll)) for pitch, roll in ((0.0, 0.0), (-5.0, 2.0), (-20.0, 8.0), (-47.0, 18.0), (-76.0, 27.0), (-82.0, 29.0), (-82.0, 29.0))), loop=False),
        _track(skeleton, "Spine", times, tuple((("x", pitch), ("z", roll)) for pitch, roll in ((0.0, 0.0), (-8.0, 2.0), (-12.0, 5.0), (-9.0, 7.0), (-5.0, 5.0), (-3.0, 3.0), (-3.0, 3.0))), loop=False),
        _track(skeleton, "Head", times, tuple((("x", pitch), ("z", roll)) for pitch, roll in ((0.0, 0.0), (5.0, -1.0), (12.0, -3.0), (15.0, -6.0), (10.0, -8.0), (4.0, -8.0), (4.0, -8.0))), loop=False),
        _track(skeleton, "Arm.L", times, tuple((("x", pitch), ("z", side)) for pitch, side in ((0.0, 0.0), (-8.0, -5.0), (-15.0, -10.0), (-20.0, -14.0), (-18.0, -16.0), (-16.0, -16.0), (-16.0, -16.0))), loop=False),
        _track(skeleton, "Arm.R", times, tuple((("x", pitch), ("z", side)) for pitch, side in ((0.0, 0.0), (-8.0, 5.0), (-15.0, 10.0), (-20.0, 14.0), (-18.0, 16.0), (-16.0, 16.0), (-16.0, 16.0))), loop=False),
        _track(skeleton, "Leg.L", times, tuple((("x", pitch), ("z", side)) for pitch, side in ((0.0, 0.0), (3.0, -2.0), (7.0, -5.0), (10.0, -8.0), (12.0, -10.0), (12.0, -10.0), (12.0, -10.0))), loop=False),
        _track(skeleton, "Leg.R", times, tuple((("x", pitch), ("z", side)) for pitch, side in ((0.0, 0.0), (3.0, 2.0), (7.0, 5.0), (10.0, 8.0), (12.0, 10.0), (12.0, 10.0), (12.0, 10.0))), loop=False),
    )
    leg_height = float(skeleton.joints[skeleton.index("Hips")].local_matrix[1, 3])
    x_offsets = (0.0, 0.0, 0.03, 0.08, 0.14, 0.17, 0.17)
    z_offsets = (0.0, -0.01, -0.05, -0.14, -0.25, -0.30, -0.30)
    hips_values = np.asarray(
        [
            _grounded_hips_translation(
                skeleton,
                meshes,
                rotations,
                float(time),
                horizontal_offset=(leg_height * x, leg_height * z),
            )
            for time, x, z in zip(times, x_offsets, z_offsets, strict=True)
        ],
        dtype=np.float32,
    )
    hips_values[-1] = hips_values[-2]
    return AnimationClip(
        "Death",
        1.3,
        rotations + (_translation_track("Hips", times, hips_values),),
        MappingProxyType({"loop": False, "inPlace": True, "holdFinalPose": True}),
    )


CLIP_FACTORIES: Mapping[str, Callable[..., AnimationClip]] = MappingProxyType(
    {
        "Idle": idle_clip,
        "Walk": walk_clip,
        "Run": run_clip,
        "Jump": jump_clip,
        "Fall": fall_clip,
        "Land": land_clip,
        "SitIdle": sit_idle_clip,
        "ZombieWalk": zombie_walk_clip,
        "HitReact": hit_react_clip,
        "WeaponIdle": weapon_idle_clip,
        "Aim": aim_clip,
        "AttackOneHand": attack_one_hand_clip,
        "AttackDualDaggers": attack_dual_daggers_clip,
        "AttackHeavySide": attack_heavy_side_clip,
        "Death": death_clip,
    }
)
ANIMATION_NAMES = tuple(CLIP_FACTORIES)
LOOP_CLIP_NAMES = frozenset(
    {"Idle", "Walk", "Run", "Fall", "SitIdle", "ZombieWalk", "WeaponIdle", "Aim"}
)
ONE_SHOT_CLIP_NAMES = frozenset(set(ANIMATION_NAMES) - LOOP_CLIP_NAMES)
HIPS_TRANSLATION_CLIPS = frozenset(
    {"SitIdle", "WeaponIdle", "Aim", "AttackHeavySide", "Death"}
)
CLIP_DURATIONS: Mapping[str, float] = MappingProxyType(
    {
        "Idle": 2.4,
        "Walk": 1.0,
        "Run": 0.6,
        "Jump": 0.45,
        "Fall": 1.0,
        "Land": 0.35,
        "SitIdle": 2.0,
        "ZombieWalk": 1.2,
        "HitReact": 0.35,
        "WeaponIdle": 2.0,
        "Aim": 1.5,
        "AttackOneHand": 0.5,
        "AttackDualDaggers": 0.9,
        "AttackHeavySide": 0.85,
        "Death": 1.3,
    }
)
def build_animation_clips(
    skeleton: Skeleton,
    *,
    include_idle: bool = True,
    include_walk: bool = True,
    animation_names: Iterable[str] | None = None,
    meshes: Sequence[MeshData] | None = None,
) -> tuple[AnimationClip, ...]:
    if animation_names is None:
        selected = {
            name
            for name, included in (("Idle", include_idle), ("Walk", include_walk))
            if included
        }
    else:
        selected = set(animation_names)
        unknown = selected - set(ANIMATION_NAMES)
        if unknown:
            raise ValueError(f"Неизвестные анимации: {', '.join(sorted(unknown))}")
    clips = []
    for name, factory in CLIP_FACTORIES.items():
        if name not in selected:
            continue
        if name in {"SitIdle", "Death"}:
            if meshes is None:
                raise ValueError(f"{name} requires generated meshes for ground contact.")
            clips.append(factory(skeleton, meshes))
        else:
            clips.append(factory(skeleton))
    return tuple(clips)
