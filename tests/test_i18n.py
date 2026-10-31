import json

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox

from chibi_skin_generator.i18n import set_language, set_text, tr
from chibi_skin_generator.ui import MainWindow


@pytest.fixture(autouse=True)
def english_after_test():
    yield
    set_language("en")


def test_switch_preserves_data_and_translates_live_status(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat))
    window.skin_edit.setText("C:/Skins/Мой скин.png")
    window.output_edit.setText("C:/Models")
    window.proportion_editor.controls["head_size"].spin.setValue(1.2)
    window.clear_animations_button.click()
    window.animation_checkboxes["Aim"].setChecked(True)
    before = window.proportion_editor.settings
    window.language_combo.setCurrentIndex(1)
    assert window.generate_button.text() == "Создать GLB"
    assert window.proportion_editor.save_button.text() == "Сохранить пресет"
    assert window.proportion_editor.settings == before
    assert window.skin_edit.text() == "C:/Skins/Мой скин.png"
    assert sum(c.isChecked() for c in window.animation_checkboxes.values()) == 1
    set_text(window.status_label, "GLB generated · Animations: Aim\nC:/Модели/a.glb")
    assert window.status_label.text().startswith("GLB создан")
    window.language_combo.setCurrentIndex(0)
    assert window.status_label.text() == "GLB generated · Animations: Aim\nC:/Модели/a.glb"
    window.close()


def test_language_selection_survives_restart(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat)
    first = MainWindow(settings)
    first.language_combo.setCurrentIndex(1)
    first.close()
    second = MainWindow(settings)
    assert second.language_combo.currentData() == "ru"
    assert second.generate_button.text() == "Создать GLB"
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    assert box.button(QDialogButtonBox.StandardButton.Cancel).text() == "Отмена"
    second.close()


def test_russian_validation_keeps_user_file_names_intact():
    set_language("ru")
    assert tr("File not found: C:/Skins/Русский.png") == "Файл не найден: C:/Skins/Русский.png"
    assert tr("Invalid preset settings: head_size must be a number.") == "Некорректные параметры пресета: head_size должен быть числом."
    assert tr("User-created preset name") == "User-created preset name"


def test_warning_is_displayed_in_selected_language(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat))
    window.language_combo.setCurrentIndex(1)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[1:]))
    window._generate()
    assert messages == [("Нет файла", "Выберите skin.png.")]
    window.close()
