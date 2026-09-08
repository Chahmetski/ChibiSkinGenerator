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
from chibi_skin_generator.ui import MainWindow


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


def test_animation_checkboxes_default_on_and_restore_qsettings(
    application: QApplication, tmp_path: Path
) -> None:
    assert QApplication.instance() is application
    qsettings = QSettings(str(tmp_path / "animations.ini"), QSettings.Format.IniFormat)
    qsettings.setValue("animations/include_attack_overhead2_h", True)
    window = MainWindow(qsettings)
    assert window.include_idle_checkbox.isChecked()
    assert window.include_walk_checkbox.isChecked()
    assert len(window.animation_checkboxes) == 15
    assert {"WeaponIdle", "Aim", "AttackHeavySide", "Death"} <= set(
        window.animation_checkboxes
    )
    assert "AttackOverhead2H" not in window.animation_checkboxes
    assert not qsettings.contains("animations/include_attack_overhead2_h")
    assert all(checkbox.isChecked() for checkbox in window.animation_checkboxes.values())
    assert window.material_combo.currentText() == "Pixel Unlit"
    window.clear_animations_button.click()
    assert not any(checkbox.isChecked() for checkbox in window.animation_checkboxes.values())
    window.include_walk_checkbox.setChecked(True)
    window.material_combo.setCurrentText("PBR Lit")
    qsettings.sync()
    window.deleteLater()

    restored = MainWindow(qsettings)
    assert not restored.include_idle_checkbox.isChecked()
    assert restored.include_walk_checkbox.isChecked()
    assert not restored.animation_checkboxes["AttackOneHand"].isChecked()
    assert restored.material_combo.currentText() == "PBR Lit"
    restored.core_combat_pack_button.click()
    assert all(checkbox.isChecked() for checkbox in restored.animation_checkboxes.values())
    restored.deleteLater()
