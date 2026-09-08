"""Create the two deterministic manual-check GLBs requested for version 0.5.0."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chibi_skin_generator.exporter import generate_diagnostic_model, generate_model


def main() -> None:
    output = PROJECT_ROOT / "verification_output"
    output.mkdir(exist_ok=True)
    skin_path = output / "rig_verification_skin.png"

    y, x = np.indices((64, 64))
    pixels = np.empty((64, 64, 4), dtype=np.uint8)
    pixels[..., 0] = (x * 4).astype(np.uint8)
    pixels[..., 1] = (y * 4).astype(np.uint8)
    pixels[..., 2] = 180
    pixels[..., 3] = 255
    pixels[0:16, 32:64, 3] = 0
    Image.fromarray(pixels, "RGBA").save(skin_path)

    rest = generate_model(
        skin_path, "Steve", output, include_idle=False, include_walk=False
    )
    diagnostic = generate_diagnostic_model(skin_path, "Steve", output)
    print(rest.output_path)
    print(diagnostic.output_path)


if __name__ == "__main__":
    main()
