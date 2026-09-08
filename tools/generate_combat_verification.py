"""Create the all-clips manual verification GLB for version 0.8.0."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chibi_skin_generator.animations import ANIMATION_NAMES
from chibi_skin_generator.exporter import generate_model


def main() -> None:
    output = PROJECT_ROOT / "verification_output"
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="chibi_combat_") as temporary:
        skin_path = Path(temporary) / "core_combat_skin.png"
        y, x = np.indices((64, 64))
        pixels = np.empty((64, 64, 4), dtype=np.uint8)
        pixels[..., 0] = (x * 4).astype(np.uint8)
        pixels[..., 1] = (y * 4).astype(np.uint8)
        pixels[..., 2] = 180
        pixels[..., 3] = 255
        pixels[0:16, 32:64, 3] = 0
        Image.fromarray(pixels, "RGBA").save(skin_path)

        result = generate_model(
            skin_path,
            "Steve",
            output,
            animation_names=ANIMATION_NAMES,
        )
        target = output / "rig_core_combat_pack_v0_8_0.glb"
        result.output_path.replace(target)
        print(target)
        print(", ".join(result.animations))


if __name__ == "__main__":
    main()
