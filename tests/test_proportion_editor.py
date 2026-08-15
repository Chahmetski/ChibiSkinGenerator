from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from chibi_skin_generator.preset_storage import PresetStorage
from chibi_skin_generator.proportion_editor import CUSTOM, ProportionEditor
from chibi_skin_generator.proportions import COMPACT_CHIBI


@pytest.fixture(scope="module")
def application() -> QApplication:
    existing = QApplication.instance()
    return existing if existing is not None else QApplication([])


def test_editor_links_controls_marks_custom_and_restores_qsettings(
    application: QApplication, tmp_path: Path
) -> None:
    assert QApplication.instance() is application
    qsettings = QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat)
    storage = PresetStorage(tmp_path / "presets")
    editor = ProportionEditor(qsettings, storage)
    assert editor.preset_combo.currentText() == COMPACT_CHIBI

    editor.controls["head_size"].spin.setValue(1.2)
    assert editor.settings.head_size == pytest.approx(1.2)
    assert editor.preset_combo.currentText() == CUSTOM

    editor.controls["arm_angle"].slider.setValue(500)
    assert editor.controls["arm_angle"].spin.value() == pytest.approx(10.0)
    assert editor.settings.arm_angle == pytest.approx(10.0)
    qsettings.sync()

    restored = ProportionEditor(qsettings, storage)
    assert restored.preset_combo.currentText() == CUSTOM
    assert restored.settings.head_size == pytest.approx(1.2)
    assert restored.settings.arm_angle == pytest.approx(10.0)
    editor.deleteLater()
    restored.deleteLater()
