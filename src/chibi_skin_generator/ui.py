"""PySide6 desktop interface."""

from __future__ import annotations

from pathlib import Path
from PIL.ImageQt import ImageQt

from PySide6.QtCore import QObject, QSettings, QStandardPaths, QThread, Signal, Slot, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QGridLayout,
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
from .animations import ANIMATION_NAMES, CLIP_DURATIONS, LOOP_CLIP_NAMES
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
        self._last_output: Path | None = None
        self.setAcceptDrops(True)
        self._settings.remove(self._animation_setting_key("AttackOverhead2H"))

        self.skin_edit = QLineEdit()
        self.skin_edit.setText(self._settings.value("session/skin", "", type=str))
        self.skin_edit.textChanged.connect(lambda value: self._settings.setValue("session/skin", value))
        self.skin_edit.setPlaceholderText("Выберите skin.png размером 64×64")
        skin_button = QPushButton("Обзор…")
        skin_button.clicked.connect(self._choose_skin)

        self.arm_combo = QComboBox()
        self.arm_combo.addItems(("Auto", "Steve", "Alex"))
        saved_arm = self._settings.value("session/arms", "Auto", type=str)
        self.arm_combo.setCurrentText(saved_arm if saved_arm in ("Auto", "Steve", "Alex") else "Auto")
        self.arm_combo.currentTextChanged.connect(lambda value: self._settings.setValue("session/arms", value))
        self.arm_combo.setToolTip("Auto — определение по прозрачности. При ошибке выберите Steve или Alex вручную.")
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
        self.output_edit = QLineEdit(self._settings.value("session/output", default_output, type=str))
        self.output_edit.textChanged.connect(lambda value: self._settings.setValue("session/output", value))
        output_button = QPushButton("Обзор…")
        output_button.clicked.connect(self._choose_output)

        self.generate_button = QPushButton("Создать GLB")
        self.generate_button.setDefault(True)
        self.generate_button.clicked.connect(self._generate)
        self.status_label = QLabel("Готово к генерации. Повторные экспорты сохраняются с новым номером.")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.open_output_button = QPushButton("Открыть папку результата")
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        self.skin_thumbnail = QLabel()
        self.skin_thumbnail.setFixedSize(80, 80)
        self.skin_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.skin_info = QLabel("Перетащите PNG 64×64 в окно или выберите файл.")
        self.skin_info.setWordWrap(True)
        pose_hint = QLabel(
            "В Blender: выберите Skeleton → Pose Mode → Head, Spine, Arm.L/R "
            "или Leg.L/R. Hand и Foot пока вспомогательные и не двигают меши."
        )
        pose_hint.setWordWrap(True)

        self.animation_checkboxes: dict[str, QCheckBox] = {}
        animation_list = QWidget()
        animation_list_layout = QGridLayout(animation_list)
        animation_list_layout.setContentsMargins(4, 4, 4, 4)
        loop_row, single_row = 1, 1
        animation_list_layout.addWidget(QLabel("Зацикленные"), 0, 0)
        animation_list_layout.addWidget(QLabel("Однократные"), 0, 1)
        for animation_name in ANIMATION_NAMES:
            duration = CLIP_DURATIONS[animation_name]
            checkbox = QCheckBox(f"{animation_name} · {duration:g} с")
            checkbox.setToolTip(f"{animation_name}: {duration:g} с; " +
                               ("зацикленный клип" if animation_name in LOOP_CLIP_NAMES else "однократное действие"))
            setting_key = self._animation_setting_key(animation_name)
            checkbox.setChecked(self._settings.value(setting_key, True, type=bool))
            checkbox.toggled.connect(
                lambda checked, key=setting_key: self._settings.setValue(key, checked)
            )
            if animation_name in LOOP_CLIP_NAMES:
                animation_list_layout.addWidget(checkbox, loop_row, 0)
                loop_row += 1
            else:
                animation_list_layout.addWidget(checkbox, single_row, 1)
                single_row += 1
            self.animation_checkboxes[animation_name] = checkbox

        self.include_idle_checkbox = self.animation_checkboxes["Idle"]
        self.include_walk_checkbox = self.animation_checkboxes["Walk"]

        self.select_all_animations_button = QPushButton("Выбрать все")
        self.clear_animations_button = QPushButton("Снять выбор")
        self.core_combat_pack_button = QPushButton("Весь набор · 15 клипов")
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
        self.select_all_animations_button.hide()  # Kept as an internal compatibility alias.
        animation_buttons.addWidget(self.clear_animations_button)
        animation_buttons.addWidget(self.core_combat_pack_button)

        animation_scroll = QScrollArea()
        animation_scroll.setWidgetResizable(True)
        animation_scroll.setMaximumHeight(300)
        animation_scroll.setWidget(animation_list)
        animation_group = QGroupBox("Анимации")
        animation_layout = QVBoxLayout(animation_group)
        animation_layout.addLayout(animation_buttons)
        animation_layout.addWidget(animation_scroll)

        form = QFormLayout()
        form.addRow("Скин PNG:", self._path_row(self.skin_edit, skin_button))
        form.addRow("Тип рук:", self.arm_combo)
        form.addRow("Материал:", self.material_combo)
        form.addRow("Папка сохранения:", self._path_row(self.output_edit, output_button))
        form.addRow("Формат:", QLabel("GLB 2.0 · модель со скелетом"))

        intro = QLabel(
            "Создаёт редактируемую chibi-модель GLB из стандартного Minecraft-скина. "
            "Текстура будет встроена в файл."
        )
        intro.setWordWrap(True)

        generator_layout = QVBoxLayout()
        generator_layout.addWidget(intro)
        generator_layout.addLayout(form)
        skin_preview_row = QHBoxLayout()
        skin_preview_row.addWidget(self.skin_thumbnail)
        skin_preview_row.addWidget(self.skin_info, 1)
        generator_layout.addLayout(skin_preview_row)
        generator_layout.addWidget(animation_group)
        generator_layout.addWidget(self.generate_button)
        generator_layout.addWidget(self.status_label)
        generator_layout.addWidget(self.open_output_button)
        generator_layout.addWidget(pose_hint)
        generator_layout.addStretch(1)

        generator_tab = QWidget()
        generator_tab.setLayout(generator_layout)
        tabs = QTabWidget()
        tabs.addTab(generator_tab, "Генератор")
        tabs.addTab(self.proportion_editor, "Пропорции")
        self.setCentralWidget(tabs)
        self._sync_preview_arm_width()

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
        try:
            skin = load_skin(self.skin_edit.text().strip(), choice)
        except SkinError as exc:
            self.skin_thumbnail.clear()
            self.skin_info.setText(str(exc) if self.skin_edit.text().strip() else "Перетащите PNG 64×64 в окно.")
        else:
            self.skin_thumbnail.setPixmap(QPixmap.fromImage(ImageQt(skin.image)).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
            self.skin_info.setText(f"64×64 · {skin.arm_model} · " + skin.path.name)

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
        self._last_output = Path(output_path)
        self.open_output_button.setEnabled(True)
        animation_list = animations or "нет"
        self.status_label.setText(
            f"GLB создан · Анимации: {animation_list}\n{output_path}"
        )
        QMessageBox.information(
            self,
            "Генерация завершена",
            f"GLB со скелетом создан\nАнимации: {animation_list}\n"
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

    def _open_output(self) -> None:
        if self._last_output is not None:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output.parent))):
                QMessageBox.warning(self, "Папка результата", f"Откройте папку вручную: {self._last_output.parent}")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() == ".png":
                event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self.skin_edit.setText(urls[0].toLocalFile())
            self._sync_preview_arm_width()
            event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(
                self, "Генерация выполняется", "Дождитесь завершения генерации."
            )
            event.ignore()
            return
        super().closeEvent(event)
