"""Stable twelve-joint skeleton derived entirely from proportion settings."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .proportions import ProportionSettings, calculate_proportions

JOINT_ORDER = (
    "Root",
    "Hips",
    "Spine",
    "Head",
    "Arm.L",
    "Hand.L",
    "Arm.R",
    "Hand.R",
    "Leg.L",
    "Foot.L",
    "Leg.R",
    "Foot.R",
)

JOINT_PARENTS = (
    None,
    0,
    1,
    2,
    2,
    4,
    2,
    6,
    1,
    8,
    1,
    10,
)

MESH_JOINTS = {
    "Head": "Head",
    "Head_Overlay": "Head",
    "Body": "Spine",
    "Body_Overlay": "Spine",
    "Arm.L": "Arm.L",
    "Arm_Overlay.L": "Arm.L",
    "Arm.R": "Arm.R",
    "Arm_Overlay.R": "Arm.R",
    "Leg.L": "Leg.L",
    "Leg_Overlay.L": "Leg.L",
    "Leg.R": "Leg.R",
    "Leg_Overlay.R": "Leg.R",
}


@dataclass(frozen=True, slots=True)
class Joint:
    name: str
    parent: int | None
    local_matrix: np.ndarray
    world_matrix: np.ndarray


@dataclass(frozen=True, slots=True)
class Skeleton:
    joints: tuple[Joint, ...]

    @property
    def inverse_bind_matrices(self) -> np.ndarray:
        return np.asarray(
            [np.linalg.inv(joint.world_matrix) for joint in self.joints], dtype=np.float32
        )

    def index(self, name: str) -> int:
        return JOINT_ORDER.index(name)


def translation(x: float, y: float, z: float) -> np.ndarray:
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, 3] = (x, y, z)
    return matrix


def rotation_x(degrees: float) -> np.ndarray:
    angle = np.deg2rad(degrees)
    cosine, sine = float(np.cos(angle)), float(np.sin(angle))
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = ((1.0, 0.0, 0.0), (0.0, cosine, -sine), (0.0, sine, cosine))
    return matrix


def rotation_y(degrees: float) -> np.ndarray:
    angle = np.deg2rad(degrees)
    cosine, sine = float(np.cos(angle)), float(np.sin(angle))
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = ((cosine, 0.0, sine), (0.0, 1.0, 0.0), (-sine, 0.0, cosine))
    return matrix


def rotation_z(degrees: float) -> np.ndarray:
    angle = np.deg2rad(degrees)
    cosine, sine = float(np.cos(angle)), float(np.sin(angle))
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = ((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0))
    return matrix


def build_skeleton(settings: ProportionSettings, arm_pixels: int) -> Skeleton:
    layout = calculate_proportions(settings, arm_pixels)
    parts = layout.by_name()
    left_arm = parts["Arm.L"]
    right_arm = parts["Arm.R"]
    left_leg = parts["Leg.L"]
    right_leg = parts["Leg.R"]

    leg_top = left_leg.pivot[1] + left_leg.size[1] / 2.0
    body_top = parts["Body"].pivot[1] + parts["Body"].size[1] / 2.0

    world: list[np.ndarray] = [np.eye(4, dtype=np.float64) for _ in JOINT_ORDER]
    world[0] = np.eye(4, dtype=np.float64)
    world[1] = translation(0.0, leg_top, 0.0)
    world[2] = translation(0.0, leg_top, 0.0)
    world[3] = translation(0.0, body_top, 0.0)
    # glTF/Blender draw a bone from its origin along local +Y.  The geometry
    # extends downward from the shoulder, so turn the joint basis around while
    # retaining the configured outward arm angle in the rest transform.
    limb_basis_flip = rotation_z(180.0)
    world[4] = left_arm_transform = _part_transform(left_arm) @ limb_basis_flip
    world[5] = left_arm_transform @ translation(
        -left_arm.local_center[0], left_arm.size[1], 0.0
    )
    world[6] = right_arm_transform = _part_transform(right_arm) @ limb_basis_flip
    world[7] = right_arm_transform @ translation(
        -right_arm.local_center[0], right_arm.size[1], 0.0
    )
    leg_basis_flip = rotation_x(180.0)
    world[8] = left_leg_transform = (
        translation(left_leg.pivot[0], leg_top, 0.0) @ leg_basis_flip
    )
    world[9] = left_leg_transform @ translation(0.0, left_leg.size[1], 0.0)
    world[10] = right_leg_transform = (
        translation(right_leg.pivot[0], leg_top, 0.0) @ leg_basis_flip
    )
    world[11] = right_leg_transform @ translation(0.0, right_leg.size[1], 0.0)

    joints = []
    for index, name in enumerate(JOINT_ORDER):
        parent = JOINT_PARENTS[index]
        local = world[index] if parent is None else np.linalg.inv(world[parent]) @ world[index]
        joints.append(Joint(name, parent, local, world[index]))
    return Skeleton(tuple(joints))


def _part_transform(part) -> np.ndarray:  # type: ignore[no-untyped-def]
    return translation(*part.pivot) @ rotation_z(part.rotation_degrees)


def diagnostic_local_matrices(skeleton: Skeleton) -> tuple[np.ndarray, ...]:
    """Return a non-animated diagnostic pose used only by tests and test GLBs."""
    matrices = [joint.local_matrix.copy() for joint in skeleton.joints]
    matrices[skeleton.index("Arm.L")] = matrices[skeleton.index("Arm.L")] @ rotation_z(35.0)
    matrices[skeleton.index("Arm.R")] = matrices[skeleton.index("Arm.R")] @ rotation_z(-35.0)
    matrices[skeleton.index("Leg.L")] = matrices[skeleton.index("Leg.L")] @ rotation_x(20.0)
    matrices[skeleton.index("Head")] = matrices[skeleton.index("Head")] @ rotation_y(15.0)
    return tuple(matrices)


def world_matrices_from_locals(
    local_matrices: tuple[np.ndarray, ...],
) -> tuple[np.ndarray, ...]:
    if len(local_matrices) != len(JOINT_ORDER):
        raise ValueError("Joint matrix count does not match the stable skeleton.")
    world: list[np.ndarray] = []
    for index, local in enumerate(local_matrices):
        parent = JOINT_PARENTS[index]
        world.append(local.copy() if parent is None else world[parent] @ local)
    return tuple(world)
