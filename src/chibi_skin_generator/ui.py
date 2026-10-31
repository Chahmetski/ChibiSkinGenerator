"""PySide6 desktop interface."""

from __future__ import annotations

from pathlib import Path
from PIL.ImageQt import ImageQt

from PySide6.QtCore import QObject, QSettings, QStandardPaths, QThread, Signal, Slot, Qt, QUrl, QLocale
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
from .i18n import tr, set_text, set_language, apply_to_window
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
        set_language("en")
        self.setLocale(QLocale("en_US"))
        self.setWindowTitle(f"Minecraft Skin → Chibi GLB — v{__version__}")
        self.setMinimumSize(820, 620)
        self.resize(1040, 760)
        self._thread: QThread | None = None
        self._worker: GenerationWorker | None = None
        self._settings = settings or QSettings()
        self._last_output: Path | None = None
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Русский", "ru")
        saved_language = self._settings.value("session/language", "en", type=str)
        self.language_combo.setCurrentIndex(1 if saved_language == "ru" else 0)
        self.setAcceptDrops(True)
        self._settings.remove(self._animation_setting_key("AttackOverhead2H"))

        self.skin_edit = QLineEdit()
        set_text(self.skin_edit, self._settings.value('session/skin', '', type=str))
        self.skin_edit.textChanged.connect(lambda value: self._settings.setValue("session/skin", value))
        self.skin_edit.setPlaceholderText("Select a 64×64 skin.png file")
        skin_button = QPushButton("Browse…")
        skin_button.clicked.connect(self._choose_skin)

        self.arm_combo = QComboBox()
        self.arm_combo.addItems(("Auto", "Steve", "Alex"))
        saved_arm = self._settings.value("session/arms", "Auto", type=str)
        self.arm_combo.setCurrentText(saved_arm if saved_arm in ("Auto", "Steve", "Alex") else "Auto")
        self.arm_combo.currentTextChanged.connect(lambda value: self._settings.setValue("session/arms", value))
        self.arm_combo.setToolTip("Auto detects the arm type from transparency. If incorrect, select Steve or Alex manually.")
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
        output_button = QPushButton("Browse…")
        output_button.clicked.connect(self._choose_output)

        self.generate_button = QPushButton("Generate GLB")
        self.generate_button.setDefault(True)
        self.generate_button.clicked.connect(self._generate)
        self.status_label = QLabel("Ready to generate. Repeated exports are saved with a new number.")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.open_output_button = QPushButton("Open Output Folder")
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        self.skin_thumbnail = QLabel()
        self.skin_thumbnail.setFixedSize(80, 80)
        self.skin_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.skin_info = QLabel("Drop a 64×64 PNG here or select a file.")
        self.skin_info.setWordWrap(True)
        pose_hint = QLabel(
            "In Blender: select Skeleton → Pose Mode → Head, Spine, Arm.L/R "
            "or Leg.L/R. Hand and Foot are helper joints and do not deform meshes."
        )
        pose_hint.setWordWrap(True)

        self.animation_checkboxes: dict[str, QCheckBox] = {}
        animation_list = QWidget()
        animation_list_layout = QGridLayout(animation_list)
        animation_list_layout.setContentsMargins(4, 4, 4, 4)
        loop_row, single_row = 1, 1
        animation_list_layout.addWidget(QLabel("Looping"), 0, 0)
        animation_list_layout.addWidget(QLabel("One-shot"), 0, 1)
        for animation_name in ANIMATION_NAMES:
            duration = CLIP_DURATIONS[animation_name]
            checkbox = QCheckBox(f"{animation_name} · {duration:g} s")
            checkbox.setToolTip(f"{animation_name}: {duration:g} s; " +
                               ("looping clip" if animation_name in LOOP_CLIP_NAMES else "one-shot action"))
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

        self.select_all_animations_button = QPushButton("Select All")
        self.clear_animations_button = QPushButton("Clear Selection")
        self.core_combat_pack_button = QPushButton("Full Pack · 15 Clips")
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
        animation_group = QGroupBox("Animations")
        animation_layout = QVBoxLayout(animation_group)
        animation_layout.addLayout(animation_buttons)
        animation_layout.addWidget(animation_scroll)

        form = QFormLayout()
        language_row = QWidget()
        language_layout = QHBoxLayout(language_row)
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.addWidget(self.language_combo, 1)
        self.licenses_button = QPushButton("Licenses")
        self.licenses_button.clicked.connect(self._show_licenses)
        language_layout.addWidget(self.licenses_button)
        form.addRow("Language:", language_row)
        form.addRow("Skin PNG:", self._path_row(self.skin_edit, skin_button))
        form.addRow("Arm type:", self.arm_combo)
        form.addRow("Material:", self.material_combo)
        form.addRow("Output folder:", self._path_row(self.output_edit, output_button))
        form.addRow("Format:", QLabel("GLB 2.0 · rigged model"))

        intro = QLabel(
            "Create an editable chibi GLB from a standard Minecraft skin. "
            "The texture is embedded in the file."
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
        tabs.addTab(generator_tab, "Generator")
        tabs.addTab(self.proportion_editor, "Proportions")
        self.setCentralWidget(tabs)
        self._sync_preview_arm_width()
        self._apply_language()
        self.language_combo.currentIndexChanged.connect(self._apply_language)

    def _apply_language(self, *_args) -> None:
        value = self.language_combo.currentData()
        self._settings.setValue("session/language", value)
        set_language(value)
        apply_to_window(self)
        self.proportion_editor.preview.update()

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
        path, _ = QFileDialog.getOpenFileName(self, tr('Select Minecraft Skin'), self.skin_edit.text(), 'PNG (*.png)', options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            set_text(self.skin_edit, path)
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
            set_text(self.skin_info, str(exc) if self.skin_edit.text().strip() else 'Drop a 64×64 PNG here.')
        else:
            self.skin_thumbnail.setPixmap(QPixmap.fromImage(ImageQt(skin.image)).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
            set_text(self.skin_info, f'64×64 · {skin.arm_model} · ' + skin.path.name)

    @Slot()
    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr('Select Output Folder'), self.output_edit.text(), options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            set_text(self.output_edit, path)

    @Slot()
    def _generate(self) -> None:
        skin_path = self.skin_edit.text().strip()
        output_directory = self.output_edit.text().strip()
        if not skin_path:
            QMessageBox.warning(self, tr('No File Selected'), tr('Select skin.png.'))
            return
        if not output_directory:
            QMessageBox.warning(self, tr('No Output Folder'), tr('Select an output folder.'))
            return

        self.generate_button.setEnabled(False)
        set_text(self.status_label, 'Generating…')
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
        animation_list = animations or "None"
        set_text(self.status_label, f'GLB generated · Animations: {animation_list}\n{output_path}')
        QMessageBox.information(self, tr('Generation Complete'), tr(f'Rigged GLB generated\nAnimations: {animation_list}\nArm type: {arm_model}\n\n{output_path}'))

    @Slot(str)
    def _generation_failed(self, message: str) -> None:
        set_text(self.status_label, 'Generation failed.')
        QMessageBox.critical(self, tr('Error'), tr(message))

    @Slot()
    def _thread_finished(self) -> None:
        self.generate_button.setEnabled(True)
        self._thread = None
        self._worker = None

    def _show_licenses(self) -> None:
        message = tr("This application uses Qt / PySide6 under LGPLv3. License texts, source information and library replacement instructions are included in THIRD_PARTY_NOTICES.md next to the executable.")
        QMessageBox.information(self, tr("Third-party licenses"), message)

    def _open_output(self) -> None:
        if self._last_output is not None:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output.parent))):
                QMessageBox.warning(self, tr('Output Folder'), tr(f'Open the folder manually: {self._last_output.parent}'))

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() == ".png":
                event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            set_text(self.skin_edit, urls[0].toLocalFile())
            self._sync_preview_arm_width()
            event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None and self._thread.isRunning():
            QMessageBox.information(self, tr('Generation In Progress'), tr('Please wait for generation to finish.'))
            event.ignore()
            return
        super().closeEvent(event)
