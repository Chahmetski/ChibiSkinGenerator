"""Offline frozen-application check, invoked explicitly with --self-test."""
from __future__ import annotations

import json
from pathlib import Path
import traceback


def run(directory: str) -> int:
    output = Path(directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report: dict = {"ok": False}
    try:
        from PIL import Image
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from .animations import ANIMATION_NAMES
        from .exporter import generate_model, _read_glb
        from .ui import MainWindow
        app = QApplication.instance() or QApplication([])
        app.setOrganizationName("ChibiSkinGenerator")
        app.setApplicationName("ChibiSkinGenerator")
        settings = QSettings(str(output / "isolated.ini"), QSettings.Format.IniFormat)
        settings.setValue("session/language", "en")
        window = MainWindow(settings)
        assert window.generate_button.text() == "Generate GLB"
        window.language_combo.setCurrentIndex(1)
        assert window.generate_button.text() == "\u0421\u043e\u0437\u0434\u0430\u0442\u044c GLB"
        window.language_combo.setCurrentIndex(0)
        assert window.generate_button.text() == "Generate GLB"
        skin = output / "generated_skin.png"
        Image.new("RGBA", (64, 64), (90, 150, 210, 255)).save(skin)
        window.skin_edit.setText(str(skin))
        window._sync_preview_arm_width()
        window.show()
        app.processEvents()
        window.grab().save(str(output / "window.png"))
        result = generate_model(skin, "Steve", output, animation_names=ANIMATION_NAMES)
        document, _ = _read_glb(result.output_path.read_bytes())
        assert len(document["meshes"]) == 12
        assert len(document["skins"]) == 1
        assert len(document["skins"][0]["joints"]) == 12
        assert len(document["animations"]) == 15
        assert not window.skin_thumbnail.pixmap().isNull()
        window.close()
        report.update(ok=True, languages=["en", "ru"], meshes=12, skins=1, joints=12, animations=15,
                      output=str(result.output_path))
    except Exception:
        report["error"] = traceback.format_exc()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
