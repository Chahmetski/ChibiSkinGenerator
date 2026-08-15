"""Minecraft 64x64 skin loading and arm-model selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, UnidentifiedImageError

ArmChoice = Literal["Steve", "Alex", "Auto"]
ArmModel = Literal["Steve", "Alex"]


class SkinError(ValueError):
    """Raised when the input is not a supported Minecraft skin."""


@dataclass(slots=True)
class SkinData:
    path: Path
    image: Image.Image
    pixels: np.ndarray
    arm_model: ArmModel

    @property
    def arm_width(self) -> int:
        return 3 if self.arm_model == "Alex" else 4


def detect_arm_model(pixels: np.ndarray) -> ArmModel:
    """Infer Alex from transparent columns unused by the slim arm layout.

    PNG skins contain no formal Steve/Alex metadata, so Auto is necessarily a
    conservative heuristic. It checks the extra base-layer columns that a
    correctly authored Alex skin leaves transparent; ambiguous files become
    Steve.
    """
    alpha = pixels[:, :, 3]
    alex_only_gaps = (
        alpha[20:32, 54:56],  # right arm base
        alpha[52:64, 46:48],  # left arm base
    )
    return "Alex" if all(np.all(area == 0) for area in alex_only_gaps) else "Steve"


def load_skin(path: str | Path, arm_choice: ArmChoice = "Auto") -> SkinData:
    skin_path = Path(path)
    if arm_choice not in ("Steve", "Alex", "Auto"):
        raise SkinError(f"Неизвестный тип рук: {arm_choice}")
    if not skin_path.is_file():
        raise SkinError(f"Файл не найден: {skin_path}")
    if skin_path.suffix.lower() != ".png":
        raise SkinError("Выберите PNG-файл.")

    try:
        with Image.open(skin_path) as opened:
            opened.load()
            if opened.size != (64, 64):
                raise SkinError(
                    f"Ожидался Minecraft-скин 64×64, получен {opened.width}×{opened.height}."
                )
            image = opened.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise SkinError(f"Не удалось прочитать PNG: {exc}") from exc

    pixels = np.asarray(image, dtype=np.uint8).copy()
    model: ArmModel = detect_arm_model(pixels) if arm_choice == "Auto" else arm_choice
    return SkinData(skin_path, image, pixels, model)
