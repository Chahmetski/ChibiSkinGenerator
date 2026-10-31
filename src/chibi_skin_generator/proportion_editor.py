"""PySide6 controls for live editing and persistence of proportions."""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings, QSignalBlocker, Qt, Signal, QLocale
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .preset_storage import PresetError, PresetStorage
from .proportion_preview import ProportionPreview
from .i18n import tr, set_text
from .proportions import (
    COMPACT_CHIBI,
    DEFAULT_PRESET,
    PARAMETER_SPECS,
    ProportionError,
    ProportionSettings,
    builtin_preset_names,
    get_builtin_preset,
)

CUSTOM = "Custom"


class ParameterControl(QWidget):
    valueChanged = Signal(float)

    def __init__(self, field_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = PARAMETER_SPECS[field_name]
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.spin = QDoubleSpinBox()
        self.spin.setLocale(QLocale("en_US"))
        self.spin.setRange(self.spec.minimum, self.spec.maximum)
        self.spin.setSingleStep(self.spec.step)
        self.spin.setDecimals(self.spec.decimals)
        self.spin.setMinimumWidth(95)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        self.slider.valueChanged.connect(self._slider_changed)
        self.spin.valueChanged.connect(self._spin_changed)

    def value(self) -> float:
        return self.spin.value()

    def set_value(self, value: float) -> None:
        with QSignalBlocker(self.spin), QSignalBlocker(self.slider):
            self.spin.setValue(value)
            self.slider.setValue(self._to_slider(value))

    def _to_slider(self, value: float) -> int:
        span = self.spec.maximum - self.spec.minimum
        return round((value - self.spec.minimum) / span * 1000)

    def _from_slider(self, value: int) -> float:
        span = self.spec.maximum - self.spec.minimum
        return self.spec.minimum + span * value / 1000.0

    def _slider_changed(self, value: int) -> None:
        converted = self._from_slider(value)
        with QSignalBlocker(self.spin):
            self.spin.setValue(converted)
        self.valueChanged.emit(self.spin.value())

    def _spin_changed(self, value: float) -> None:
        with QSignalBlocker(self.slider):
            self.slider.setValue(self._to_slider(value))
        self.valueChanged.emit(value)


class ProportionEditor(QWidget):
    settingsChanged = Signal(object)

    def __init__(
        self,
        qsettings: QSettings,
        storage: PresetStorage | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.qsettings = qsettings
        self.storage = storage or PresetStorage()
        self._settings = get_builtin_preset(DEFAULT_PRESET)
        self._loading = False
        self._arm_pixels = 4
        self.controls: dict[str, ParameterControl] = {}

        self.preset_combo = QComboBox()
        self.load_button = QPushButton("Load Preset")
        self.save_button = QPushButton("Save Preset")
        self.delete_button = QPushButton("Delete Preset")
        self.reset_button = QPushButton("Reset")
        self.preview = ProportionPreview()

        preset_box = QGroupBox("Presets")
        preset_layout = QVBoxLayout(preset_box)
        preset_layout.addWidget(self.preset_combo)
        preset_buttons = QHBoxLayout()
        preset_buttons.addWidget(self.load_button)
        preset_buttons.addWidget(self.save_button)
        preset_layout.addLayout(preset_buttons)
        preset_buttons2 = QHBoxLayout()
        preset_buttons2.addWidget(self.reset_button)
        preset_buttons2.addWidget(self.delete_button)
        preset_layout.addLayout(preset_buttons2)

        groups: dict[str, tuple[QGroupBox, QVBoxLayout]] = {}
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        for field_name, spec in PARAMETER_SPECS.items():
            if spec.group not in groups:
                box = QGroupBox(spec.group)
                box_layout = QVBoxLayout(box)
                groups[spec.group] = (box, box_layout)
                settings_layout.addWidget(box)
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.addWidget(QLabel(spec.label))
            control = ParameterControl(field_name)
            control.setToolTip(f"{spec.label}: {spec.minimum}–{spec.maximum}. Values before overall scaling.")
            control.valueChanged.connect(
                lambda value, name=field_name: self._parameter_changed(name, value)
            )
            row_layout.addWidget(control)
            groups[spec.group][1].addWidget(row)
            self.controls[field_name] = control
        settings_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(settings_widget)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(preset_box)
        left_layout.addWidget(scroll, 1)
        left.setMinimumWidth(390)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(left, 1)
        main_layout.addWidget(self.preview, 1)

        self.load_button.clicked.connect(self._load_selected)
        self.save_button.clicked.connect(self._save_preset)
        self.delete_button.clicked.connect(self._delete_preset)
        self.reset_button.clicked.connect(self._reset)
        self.preset_combo.activated.connect(self._load_selected)

        self._reload_preset_names()
        self._restore_last_state()

    @property
    def settings(self) -> ProportionSettings:
        return self._settings

    @property
    def preset_directory(self):  # type: ignore[no-untyped-def]
        return self.storage.directory

    def set_arm_pixels(self, arm_pixels: int) -> None:
        self._arm_pixels = 3 if arm_pixels == 3 else 4
        self.preview.set_arm_pixels(self._arm_pixels)

    def _reload_preset_names(self, selected: str | None = None) -> None:
        selected = selected or self.preset_combo.currentText() or DEFAULT_PRESET
        with QSignalBlocker(self.preset_combo):
            self.preset_combo.clear()
            for name in builtin_preset_names():
                self.preset_combo.addItem(name, "builtin")
            self.preset_combo.insertSeparator(self.preset_combo.count())
            try:
                user_names = self.storage.list_names()
            except (PresetError, OSError) as exc:
                user_names = []
                QMessageBox.warning(self, tr('Preset Error'), tr(str(exc)))
            for name in user_names:
                self.preset_combo.addItem(name, "user")
            self.preset_combo.insertSeparator(self.preset_combo.count())
            self.preset_combo.addItem(CUSTOM, "custom")
            index = self.preset_combo.findText(selected)
            self.preset_combo.setCurrentIndex(index if index >= 0 else self.preset_combo.findText(CUSTOM))
        self._update_delete_button()

    def _apply_settings(self, settings: ProportionSettings, selected: str) -> None:
        self._loading = True
        try:
            self._settings = settings
            for field_name, control in self.controls.items():
                control.set_value(getattr(settings, field_name))
            index = self.preset_combo.findText(selected)
            self.preset_combo.setCurrentIndex(
                index if index >= 0 else self.preset_combo.findText(CUSTOM)
            )
            self.preview.set_settings(settings)
            self._persist_state()
            self._update_delete_button()
        finally:
            self._loading = False
        self.settingsChanged.emit(settings)

    def _parameter_changed(self, field_name: str, value: float) -> None:
        if self._loading:
            return
        try:
            self._settings = self._settings.changed(**{field_name: value})
        except ProportionError as exc:
            QMessageBox.warning(self, tr('Invalid Value'), tr(str(exc)))
            return
        with QSignalBlocker(self.preset_combo):
            self.preset_combo.setCurrentIndex(self.preset_combo.findText(CUSTOM))
        self.preview.set_settings(self._settings)
        self._update_delete_button()
        self._persist_state()
        self.settingsChanged.emit(self._settings)

    def _load_selected(self, *_args) -> None:  # type: ignore[no-untyped-def]
        name = self.preset_combo.currentText()
        kind = self.preset_combo.currentData()
        try:
            if kind == "builtin":
                settings = get_builtin_preset(name)
            elif kind == "user":
                settings = self.storage.load(name).settings
            else:
                self._update_delete_button()
                return
        except (PresetError, ProportionError, OSError) as exc:
            QMessageBox.critical(self, tr('Preset Error'), tr(str(exc)))
            return
        self._apply_settings(settings, name)

    def _save_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, tr('Save Preset'), tr('Preset name:'))
        if not accepted:
            return
        try:
            preset = self.storage.save(name, self._settings)
        except (PresetError, OSError) as exc:
            QMessageBox.critical(self, tr('Save Error'), tr(str(exc)))
            return
        self._reload_preset_names(preset.name)
        self._apply_settings(preset.settings, preset.name)

    def _delete_preset(self) -> None:
        if self.preset_combo.currentData() != "user":
            return
        name = self.preset_combo.currentText()
        try:
            self.storage.delete(name)
        except (PresetError, OSError) as exc:
            QMessageBox.critical(self, tr('Delete Error'), tr(str(exc)))
            return
        self._reload_preset_names(COMPACT_CHIBI)
        self._apply_settings(get_builtin_preset(COMPACT_CHIBI), COMPACT_CHIBI)

    def _reset(self) -> None:
        name = self.preset_combo.currentText()
        kind = self.preset_combo.currentData()
        if kind == "builtin":
            self._apply_settings(get_builtin_preset(name), name)
        elif kind == "user":
            try:
                preset = self.storage.load(name)
            except (PresetError, OSError) as exc:
                QMessageBox.critical(self, tr('Preset Error'), tr(str(exc)))
                return
            self._apply_settings(preset.settings, preset.name)
        else:
            self._apply_settings(get_builtin_preset(COMPACT_CHIBI), COMPACT_CHIBI)

    def _update_delete_button(self) -> None:
        self.delete_button.setEnabled(self.preset_combo.currentData() == "user")

    def _persist_state(self) -> None:
        self.qsettings.setValue("proportions/selected_preset", self.preset_combo.currentText())
        self.qsettings.setValue(
            "proportions/values",
            json.dumps(self._settings.to_dict(), separators=(",", ":")),
        )

    def _restore_last_state(self) -> None:
        selected = str(self.qsettings.value("proportions/selected_preset", DEFAULT_PRESET))
        if selected in ("Custom", "\u0421\u0432\u043e\u0438 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b"):
            selected = CUSTOM
        raw = self.qsettings.value("proportions/values")
        settings = get_builtin_preset(DEFAULT_PRESET)
        if raw:
            try:
                settings = ProportionSettings.from_mapping(json.loads(str(raw)))
            except (json.JSONDecodeError, ProportionError):
                settings = get_builtin_preset(DEFAULT_PRESET)
                selected = DEFAULT_PRESET
        self._apply_settings(settings, selected)
