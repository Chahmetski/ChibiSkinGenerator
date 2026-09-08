"""Create the three deterministic manual-check GLBs requested for version 0.6.0."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chibi_skin_generator.exporter import generate_model


def main() -> None:
    output = PROJECT_ROOT / "verification_output"
    output.mkdir(exist_ok=True)
    modes = (
        ("rig_animation_test.glb", True, True),
        ("rig_idle_only_test.glb", True, False),
        ("rig_walk_only_test.glb", False, True),
    )
    with TemporaryDirectory(prefix="chibi_animation_") as temporary:
        skin_path = Path(temporary) / "animation_verification_skin.png"
        y, x = np.indices((64, 64))
        pixels = np.empty((64, 64, 4), dtype=np.uint8)
        pixels[..., 0] = (x * 4).astype(np.uint8)
        pixels[..., 1] = (y * 4).astype(np.uint8)
        pixels[..., 2] = 180
        pixels[..., 3] = 255
        pixels[0:16, 32:64, 3] = 0
        Image.fromarray(pixels, "RGBA").save(skin_path)

        for filename, include_idle, include_walk in modes:
            result = generate_model(
                skin_path,
                "Steve",
                output,
                include_idle=include_idle,
                include_walk=include_walk,
            )
            target = output / filename
            result.output_path.replace(target)
            print(f"{target}: {', '.join(result.animations)}")


if __name__ == "__main__":
    main()
