"""Editable chibi proportion settings, presets, and automatic placement."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields, replace
from types import MappingProxyType
from typing import Mapping

COMPACT_CHIBI = "Compact Chibi"
BALANCED_CHIBI = "Balanced Chibi"
BIG_HEAD = "Big Head"
LEGACY = "Legacy"
DEFAULT_PRESET = COMPACT_CHIBI

STEVE_ARM_BASE_WIDTH = 0.25
ALEX_ARM_BASE_WIDTH = STEVE_ARM_BASE_WIDTH * 3.0 / 4.0


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    label: str
    group: str
    minimum: float
    maximum: float
    step: float
    decimals: int


PARAMETER_SPECS: Mapping[str, ParameterSpec] = MappingProxyType(
    {
        "overall_scale": ParameterSpec("Overall scale", "General", 0.1, 10.0, 0.05, 3),
        "head_size": ParameterSpec("Head size", "General", 0.5, 1.5, 0.01, 3),
        "head_overlay_offset": ParameterSpec(
            "Head overlay offset", "General", 0.005, 0.08, 0.001, 5
        ),
        "other_overlay_offset": ParameterSpec(
            "Other overlay offset", "General", 0.005, 0.05, 0.001, 5
        ),
        "body_width": ParameterSpec("Body width", "Body", 0.3, 0.9, 0.01, 3),
        "body_height": ParameterSpec("Body height", "Body", 0.3, 1.0, 0.01, 3),
        "body_depth": ParameterSpec("Body depth", "Body", 0.15, 0.6, 0.01, 3),
        "arm_length": ParameterSpec("Arm length", "Arms", 0.25, 1.0, 0.01, 3),
        "arm_thickness": ParameterSpec("Arm thickness", "Arms", 0.6, 1.5, 0.01, 3),
        "arm_depth": ParameterSpec("Arm depth", "Arms", 0.15, 0.5, 0.01, 3),
        "shoulder_overlap": ParameterSpec(
            "Shoulder overlap", "Arms", 0.0, 0.05, 0.001, 4
        ),
        "arm_angle": ParameterSpec("Arm angle", "Arms", 0.0, 20.0, 0.25, 2),
        "leg_length": ParameterSpec("Leg length", "Legs", 0.25, 1.2, 0.01, 3),
        "leg_width": ParameterSpec("Leg width", "Legs", 0.15, 0.45, 0.01, 3),
        "leg_depth": ParameterSpec("Leg depth", "Legs", 0.15, 0.5, 0.01, 3),
        "leg_gap": ParameterSpec("Leg gap", "Legs", 0.0, 0.25, 0.005, 3),
    }
)


class ProportionError(ValueError):
    """Raised when editable proportion data is invalid."""


@dataclass(frozen=True, slots=True)
class ProportionSettings:
    overall_scale: float = 1.0
    head_size: float = 1.0
    head_overlay_offset: float = 0.03125
    other_overlay_offset: float = 0.015625
    body_width: float = 0.5
    body_height: float = 0.5
    body_depth: float = 0.25
    arm_length: float = 0.5
    arm_thickness: float = 1.0
    arm_depth: float = 0.25
    shoulder_overlap: float = 0.0075
    arm_angle: float = 5.0
    leg_length: float = 0.5
    leg_width: float = 0.25
    leg_depth: float = 0.25
    leg_gap: float = 0.0

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            spec = PARAMETER_SPECS[field.name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProportionError(f"{field.name} должен быть числом.")
            if not math.isfinite(float(value)):
                raise ProportionError(f"{field.name} должен быть конечным числом.")
            if not spec.minimum <= float(value) <= spec.maximum:
                raise ProportionError(
                    f"{field.name}: допустимый диапазон {spec.minimum}–{spec.maximum}."
                )

    def to_dict(self) -> dict[str, float]:
        return {name: float(value) for name, value in asdict(self).items()}

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "ProportionSettings":
        if not isinstance(data, Mapping):
            raise ProportionError("Настройки пропорций должны быть JSON-объектом.")
        defaults = cls()
        values: dict[str, float] = {}
        for field in fields(cls):
            value = data.get(field.name, getattr(defaults, field.name))
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProportionError(f"{field.name} должен быть числом.")
            values[field.name] = float(value)
        return cls(**values)

    def changed(self, **values: float) -> "ProportionSettings":
        return replace(self, **values)


@dataclass(frozen=True, slots=True)
class PartPlacement:
    name: str
    size: tuple[float, float, float]
    pivot: tuple[float, float, float]
    local_center: tuple[float, float, float]
    rotation_degrees: float
    overlay_offset: float


@dataclass(frozen=True, slots=True)
class CalculatedProportions:
    settings: ProportionSettings
    arm_pixels: int
    parts: tuple[PartPlacement, ...]
    total_height: float
    shoulder_points: tuple[tuple[float, float], tuple[float, float]]
    leg_connections: tuple[tuple[float, float], tuple[float, float]]

    def by_name(self) -> dict[str, PartPlacement]:
        return {part.name: part for part in self.parts}


def calculate_proportions(
    settings: ProportionSettings, arm_pixels: int
) -> CalculatedProportions:
    if not isinstance(settings, ProportionSettings):
        raise TypeError("settings must be a ProportionSettings instance")
    if arm_pixels not in (3, 4):
        raise ProportionError("Ширина рук должна быть 3 (Alex) или 4 (Steve) пикселя.")

    scale = settings.overall_scale
    arm_base = ALEX_ARM_BASE_WIDTH if arm_pixels == 3 else STEVE_ARM_BASE_WIDTH
    arm_width = arm_base * settings.arm_thickness
    leg_top = settings.leg_length
    body_top = leg_top + settings.body_height
    head_top = body_top + settings.head_size
    leg_center_x = settings.leg_gap / 2.0 + settings.leg_width / 2.0
    body_half = settings.body_width / 2.0
    shoulder_x = body_half - settings.shoulder_overlap

    def scaled(values: tuple[float, float, float]) -> tuple[float, float, float]:
        return tuple(float(value * scale) for value in values)  # type: ignore[return-value]

    head_offset = settings.head_overlay_offset * scale
    other_offset = settings.other_overlay_offset * scale
    parts = (
        PartPlacement(
            "Head",
            scaled((settings.head_size,) * 3),
            scaled((0.0, body_top + settings.head_size / 2.0, 0.0)),
            (0.0, 0.0, 0.0),
            0.0,
            head_offset,
        ),
        PartPlacement(
            "Body",
            scaled((settings.body_width, settings.body_height, settings.body_depth)),
            scaled((0.0, leg_top + settings.body_height / 2.0, 0.0)),
            (0.0, 0.0, 0.0),
            0.0,
            other_offset,
        ),
        PartPlacement(
            "Arm.L",
            scaled((arm_width, settings.arm_length, settings.arm_depth)),
            scaled((shoulder_x, body_top, 0.0)),
            scaled((arm_width / 2.0, -settings.arm_length / 2.0, 0.0)),
            settings.arm_angle,
            other_offset,
        ),
        PartPlacement(
            "Arm.R",
            scaled((arm_width, settings.arm_length, settings.arm_depth)),
            scaled((-shoulder_x, body_top, 0.0)),
            scaled((-arm_width / 2.0, -settings.arm_length / 2.0, 0.0)),
            -settings.arm_angle,
            other_offset,
        ),
        PartPlacement(
            "Leg.L",
            scaled((settings.leg_width, settings.leg_length, settings.leg_depth)),
            scaled((leg_center_x, settings.leg_length / 2.0, 0.0)),
            (0.0, 0.0, 0.0),
            0.0,
            other_offset,
        ),
        PartPlacement(
            "Leg.R",
            scaled((settings.leg_width, settings.leg_length, settings.leg_depth)),
            scaled((-leg_center_x, settings.leg_length / 2.0, 0.0)),
            (0.0, 0.0, 0.0),
            0.0,
            other_offset,
        ),
    )
    return CalculatedProportions(
        settings=settings,
        arm_pixels=arm_pixels,
        parts=parts,
        total_height=head_top * scale,
        shoulder_points=((shoulder_x * scale, body_top * scale), (-shoulder_x * scale, body_top * scale)),
        leg_connections=((leg_center_x * scale, leg_top * scale), (-leg_center_x * scale, leg_top * scale)),
    )


_COMPACT = ProportionSettings()
_BUILTIN_PRESETS: Mapping[str, ProportionSettings] = MappingProxyType(
    {
        COMPACT_CHIBI: _COMPACT,
        BALANCED_CHIBI: replace(
            _COMPACT,
            head_size=0.9,
            body_width=0.55,
            body_height=0.6,
            body_depth=0.28,
            arm_length=0.6,
            arm_depth=0.28,
            shoulder_overlap=0.01,
            arm_angle=3.0,
            leg_length=0.65,
            leg_width=0.26,
            leg_depth=0.27,
        ),
        BIG_HEAD: replace(
            _COMPACT,
            head_size=1.1,
            body_width=0.48,
            body_height=0.48,
            body_depth=0.25,
            arm_length=0.48,
            arm_thickness=0.95,
            arm_depth=0.25,
            shoulder_overlap=0.0075,
            arm_angle=6.0,
            leg_length=0.45,
            leg_width=0.23,
            leg_depth=0.24,
        ),
        LEGACY: ProportionSettings(
            overall_scale=2.4,
            head_size=1.0,
            head_overlay_offset=0.07 / 2.4,
            other_overlay_offset=0.025 / 2.4,
            body_width=1.55 / 2.4,
            body_height=1.55 / 2.4,
            body_depth=0.78 / 2.4,
            arm_length=1.45 / 2.4,
            arm_thickness=0.58 / (STEVE_ARM_BASE_WIDTH * 2.4),
            arm_depth=0.62 / 2.4,
            shoulder_overlap=0.0,
            arm_angle=0.0,
            leg_length=0.90 / 2.4,
            leg_width=0.68 / 2.4,
            leg_depth=0.70 / 2.4,
            leg_gap=0.10 / 2.4,
        ),
    }
)


def builtin_preset_names() -> tuple[str, ...]:
    return tuple(_BUILTIN_PRESETS)


def builtin_presets() -> dict[str, ProportionSettings]:
    """Return detached immutable values so callers cannot alter shared presets."""
    return {name: replace(settings) for name, settings in _BUILTIN_PRESETS.items()}


def get_builtin_preset(name: str) -> ProportionSettings:
    try:
        return replace(_BUILTIN_PRESETS[name])
    except KeyError as exc:
        raise ProportionError(f"Неизвестный встроенный пресет: {name}") from exc
