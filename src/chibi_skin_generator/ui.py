"""PySide6 desktop interface."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QStandardPaths, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .animations import ANIMATION_NAMES
from .exporter import MATERIAL_MODES, PIXEL_UNLIT, generate_model
from .proportion_editor import ProportionEditor
from .proportions import ProportionSettings
from .skin_parser import SkinError, load_skin


class GenerationWorker(QObject):
    succeeded = Signal(str, str, str)
    failed = Signal(str)

    def __init__(
        self,
        skin_path: str,
        arm_choice: str,
        output_directory: str,
        proportions: ProportionSettings,
        animation_names: tuple[str, ...],
        material_mode: str,
    ) -> None:
        super().__init__()
        self.skin_path = skin_path
        self.arm_choice = arm_choice
        self.output_directory = output_directory
        self.proportions = proportions
        self.animation_names = animation_names
        self.material_mode = material_mode

    @Slot()
    def run(self) -> None:
        try:
            result = generate_model(
                self.skin_path,
                self.arm_choice,  # type: ignore[arg-type]
                self.output_directory,
                self.proportions,
                animation_names=self.animation_names,
                material_mode=self.material_mode,
            )
        except Exception as exc:  # Display parser, filesystem and exporter errors uniformly.
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(
                str(result.output_path), result.arm_model, ", ".join(result.animations)
            )


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"Minecraft Skin → Chibi GLB — v{__version__}")
        self.setMinimumSize(820, 620)
        self.resize(1040, 760)
        self._thread: QThread | None = None
        self._worker: GenerationWorker | None = None
        self._settings = settings or QSettings()
        self._settings.remove(self._animation_setting_key("AttackOverhead2H"))

        self.skin_edit = QLineEdit()
        self.skin_edit.setPlaceholderText("Выберите skin.png размером 64×64")
        skin_button = QPushButton("Обзор…")
        skin_button.clicked.connect(self._choose_skin)

        self.arm_combo = QComboBox()
        self.arm_combo.addItems(("Auto", "Steve", "Alex"))
        self.material_combo = QComboBox()
        self.material_combo.addItems(MATERIAL_MODES)
        saved_material = self._settings.value("materials/mode", PIXEL_UNLIT, type=str)
        if saved_material not in MATERIAL_MODES:
            saved_material = PIXEL_UNLIT
        self.material_combo.setCurrentText(saved_material)
        self.material_combo.currentTextChanged.connect(
            lambda value: self._settings.setValue("materials/mode", value)
        )
        self.proportion_editor = ProportionEditor(self._settings)
        self.arm_combo.currentTextChanged.connect(self._sync_preview_arm_width)
        self.skin_edit.editingFinished.connect(self._sync_preview_arm_width)

        default_output = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        ) or str(Path.cwd())
        self.output_edit = QLineEdit(default_output)
        output_button = QPushButton("Обзор…")
        output_button.clicked.connect(self._choose_output)

        self.generate_button = QPushButton("Generate")
        self.generate_button.setDefault(True)
        self.generate_button.clicked.connect(self._generate)
        self.status_label = QLabel("Готово к генерации.")
        pose_hint = QLabel(
            "В Blender: выберите Skeleton → Pose Mode → Head, Spine, Arm.L/R "
            "или Leg.L/R. Hand и Foot пока вспомогательные и не двигают меши."
        )
        pose_hint.setWordWrap(True)

        self.animation_checkboxes: dict[str, QCheckBox] = {}
        animation_list = QWidget()
        animation_list_layout = QVBoxLayout(animation_list)
        animation_list_layout.setContentsMargins(4, 4, 4, 4)
        for animation_name in ANIMATION_NAMES:
            checkbox = QCheckBox(f"Include {animation_name}")
            setting_key = self._animation_setting_key(animation_name)
            checkbox.setChecked(self._settings.value(setting_key, True, type=bool))
            checkbox.toggled.connect(
                lambda checked, key=setting_key: self._settings.setValue(key, checked)
            )
            animation_list_layout.addWidget(checkbox)
            self.animation_checkboxes[animation_name] = checkbox
        animation_list_layout.addStretch(1)
        self.include_idle_checkbox = self.animation_checkboxes["Idle"]
        self.include_walk_checkbox = self.animation_checkboxes["Walk"]

        self.select_all_animations_button = QPushButton("Select All Animations")
        self.clear_animations_button = QPushButton("Clear Animations")
        self.core_combat_pack_button = QPushButton("Core Combat Pack")
        self.select_all_animations_button.clicked.connect(
            lambda: self._set_all_animations(True)
        )
        self.clear_animations_button.clicked.connect(
            lambda: self._set_all_animations(False)
        )
        self.core_combat_pack_button.clicked.connect(
            lambda: self._set_all_animations(True)
        )
        animation_buttons = QHBoxLayout()
        animation_buttons.addWidget(self.select_all_animations_button)
        animation_buttons.addWidget(self.clear_animations_button)
        animation_buttons.addWidget(self.core_combat_pack_button)

        animation_scroll = QScrollArea()
        animation_scroll.setWidgetResizable(True)
        animation_scroll.setMaximumHeight(250)
        animation_scroll.setWidget(animation_list)
        animation_group = QGroupBox("Animations")
        animation_layout = QVBoxLayout(animation_group)
        animation_layout.addLayout(animation_buttons)
        animation_layout.addWidget(animation_scroll)

        form = QFormLayout()
        form.addRow("Skin PNG:", self._path_row(self.skin_edit, skin_button))
        form.addRow("Тип рук:", self.arm_combo)
        form.addRow("Материал:", self.material_combo)
        form.addRow("Папка сохранения:", self._path_row(self.output_edit, output_button))
        form.addRow("Формат:", QLabel("GLB 2.0 · Rigged GLB"))

        intro = QLabel(
            "Создаёт редактируемую chibi-модель GLB из стандартного Minecraft-скина. "
            "Текстура будет встроена в файл."
        )
        intro.setWordWrap(True)

        generator_layout = QVBoxLayout()
        generator_layout.addWidget(intro)
        generator_layout.addLayout(form)
        generator_layout.addWidget(animation_group)
        generator_layout.addWidget(self.generate_button)
        generator_layout.addWidget(self.status_label)
        generator_layout.addWidget(pose_hint)
        generator_layout.addStretch(1)

        generator_tab = QWidget()
        generator_tab.setLayout(generator_layout)
        tabs = QTabWidget()
        tabs.addTab(generator_tab, "Generator")
        tabs.addTab(self.proportion_editor, "Proportions")
        self.setCentralWidget(tabs)

    @staticmethod
    def _path_row(edit: QLineEdit, button: QPushButton) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return widget

    @staticmethod
    def _animation_setting_key(animation_name: str) -> str:
        snake_case = "".join(
            f"_{character.lower()}" if character.isupper() else character
            for character in animation_name
        ).lstrip("_")
        return f"animations/include_{snake_case}"

    def _set_all_animations(self, checked: bool) -> None:
        for checkbox in self.animation_checkboxes.values():
            checkbox.setChecked(checked)

    @Slot()
    def _choose_skin(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите Minecraft skin", self.skin_edit.text(), "PNG (*.png)"
        )
        if path:
            self.skin_edit.setText(path)
            self._sync_preview_arm_width()

    @Slot()
    def _sync_preview_arm_width(self, *_args) -> None:  # type: ignore[no-untyped-def]
        choice = self.arm_combo.currentText()
        if choice == "Alex":
            arm_pixels = 3
        elif choice == "Steve":
            arm_pixels = 4
        else:
            try:
                arm_pixels = load_skin(self.skin_edit.text().strip(), "Auto").arm_width
            except SkinError:
                arm_pixels = 4
        self.proportion_editor.set_arm_pixels(arm_pixels)

    @Slot()
    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Выберите папку сохранения", self.output_edit.text()
        )
        if path:
            self.output_edit.setText(path)

    @Slot()
    def _generate(self) -> None:
        skin_path = self.skin_edit.text().strip()
        output_directory = self.output_edit.text().strip()
        if not skin_path:
            QMessageBox.warning(self, "Нет файла", "Выберите skin.png.")
            return
        if not output_directory:
            QMessageBox.warning(self, "Нет папки", "Выберите папку сохранения.")
            return

        self.generate_button.setEnabled(False)
        self.status_label.setText("Генерация…")
        thread = QThread(self)
        worker = GenerationWorker(
            skin_path,
            self.arm_combo.currentText(),
            output_directory,
            self.proportion_editor.settings,
            tuple(
                name
                for name, checkbox in self.animation_checkboxes.items()
                if checkbox.isChecked()
            ),
            self.material_combo.currentText(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._generation_succeeded)
        worker.failed.connect(self._generation_failed)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(str, str, str)
    def _generation_succeeded(
        self, output_path: str, arm_model: str, animations: str
    ) -> None:
        animation_list = animations or "None"
        self.status_label.setText(
            f"Rigged GLB generated · Animations: {animation_list}\n{output_path}"
        )
        QMessageBox.information(
            self,
            "Генерация завершена",
            f"Rigged GLB generated\nAnimations: {animation_list}\n"
            f"Тип рук: {arm_model}\n\n{output_path}",
        )

    @Slot(str)
    def _generation_failed(self, message: str) -> None:
        self.status_label.setText("Ошибка генерации.")
        QMessageBox.critical(self, "Ошибка", message)

    @Slot()
    def _thread_finished(self) -> None:
        self.generate_button.setEnabled(True)
        self._thread = None
        self._worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(
                self, "Генерация выполняется", "Дождитесь завершения генерации."
            )
            event.ignore()
            return
        super().closeEvent(event)
