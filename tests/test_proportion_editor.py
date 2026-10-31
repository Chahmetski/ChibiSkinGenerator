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


def test_paths_arm_choice_thumbnail_and_skin_validation(application, tmp_path):
    from PIL import Image
    skin = tmp_path / "preview.png"
    Image.new("RGBA", (64, 64), (80, 140, 200, 255)).save(skin)
    settings = QSettings(str(tmp_path / "session.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    window.skin_edit.setText(str(skin))
    window.output_edit.setText(str(tmp_path / "output"))
    window.arm_combo.setCurrentText("Alex")
    assert not window.skin_thumbnail.pixmap().isNull()
    assert "Alex" in window.skin_info.text()
    settings.sync()
    restored = MainWindow(settings)
    assert restored.skin_edit.text() == str(skin)
    assert restored.output_edit.text() == str(tmp_path / "output")
    assert restored.arm_combo.currentText() == "Alex"
    assert not restored.skin_thumbnail.pixmap().isNull()
    Image.new("RGB", (64, 64)).save(skin, format="BMP")
    restored._sync_preview_arm_width()
    assert restored.skin_thumbnail.pixmap().isNull()
    assert "PNG" in restored.skin_info.text()
    window.deleteLater()
    restored.deleteLater()


def test_preset_save_permission_error_is_displayed(application, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    settings = QSettings(str(tmp_path / "error.ini"), QSettings.Format.IniFormat)
    blocked = tmp_path / "blocked"
    storage = PresetStorage(blocked)
    editor = ProportionEditor(settings, storage)
    blocked.write_text("not a directory")
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("Example", True))
    messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(args[-1]))
    editor._save_preset()
    assert messages and "preset" in messages[0]
    editor.deleteLater()


def test_english_interface_and_decimal_separator(application, tmp_path):
    import re
    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QLabel, QPushButton, QGroupBox, QTabWidget, QWidget
    QLocale.setDefault(QLocale(QLocale.Language.Russian))
    settings = QSettings(str(tmp_path / "english.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings)
    assert window.generate_button.text() == "Generate GLB"
    assert window.proportion_editor.controls["head_size"].spin.locale().decimalPoint() == "."
    tabs = window.findChild(QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Generator", "Proportions"]
    for widget in window.findChildren(QWidget):
        strings = [widget.toolTip()]
        if isinstance(widget, (QLabel, QPushButton)):
            strings.append(widget.text())
        if isinstance(widget, QGroupBox):
            strings.append(widget.title())
        assert not any(re.search("[\u0400-\u04ff]", text) for text in strings), strings
    window.deleteLater()


def test_previous_russian_custom_state_migrates_to_english(application, tmp_path):
    import json
    settings = QSettings(str(tmp_path / "migration.ini"), QSettings.Format.IniFormat)
    settings.setValue("proportions/selected_preset", "\u0421\u0432\u043e\u0438 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b")
    settings.setValue("proportions/values", json.dumps({"head_size": 1.2}))
    editor = ProportionEditor(settings, PresetStorage(tmp_path / "presets"))
    assert editor.preset_combo.currentText() == "Custom"
    assert editor.settings.head_size == pytest.approx(1.2)
    editor.deleteLater()
