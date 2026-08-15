"""PySide6 desktop interface."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .exporter import generate_model
from .geometry import PROPORTION_PRESETS


class GenerationWorker(QObject):
    succeeded = Signal(str, str)
    failed = Signal(str)

    def __init__(
        self,
        skin_path: str,
        arm_choice: str,
        output_directory: str,
        proportions: str,
    ) -> None:
        super().__init__()
        self.skin_path = skin_path
        self.arm_choice = arm_choice
        self.output_directory = output_directory
        self.proportions = proportions

    @Slot()
    def run(self) -> None:
        try:
            result = generate_model(
                self.skin_path,
                self.arm_choice,  # type: ignore[arg-type]
                self.output_directory,
                self.proportions,  # type: ignore[arg-type]
            )
        except Exception as exc:  # Display parser, filesystem and exporter errors uniformly.
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(str(result.output_path), result.arm_model)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Minecraft Skin → Chibi GLB — v{__version__}")
        self.setMinimumWidth(640)
        self._thread: QThread | None = None
        self._worker: GenerationWorker | None = None

        self.skin_edit = QLineEdit()
        self.skin_edit.setPlaceholderText("Выберите skin.png размером 64×64")
        skin_button = QPushButton("Обзор…")
        skin_button.clicked.connect(self._choose_skin)

        self.arm_combo = QComboBox()
        self.arm_combo.addItems(("Auto", "Steve", "Alex"))

        self.proportions_combo = QComboBox()
        self.proportions_combo.addItems(PROPORTION_PRESETS)

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

        form = QFormLayout()
        form.addRow("Skin PNG:", self._path_row(self.skin_edit, skin_button))
        form.addRow("Тип рук:", self.arm_combo)
        form.addRow("Proportions:", self.proportions_combo)
        form.addRow("Папка сохранения:", self._path_row(self.output_edit, output_button))

        intro = QLabel(
            "Создаёт редактируемую chibi-модель GLB из стандартного Minecraft-скина. "
            "Текстура будет встроена в файл."
        )
        intro.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.generate_button)
        layout.addWidget(self.status_label)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    @staticmethod
    def _path_row(edit: QLineEdit, button: QPushButton) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return widget

    @Slot()
    def _choose_skin(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите Minecraft skin", self.skin_edit.text(), "PNG (*.png)"
        )
        if path:
            self.skin_edit.setText(path)

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
            self.proportions_combo.currentText(),
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

    @Slot(str, str)
    def _generation_succeeded(self, output_path: str, arm_model: str) -> None:
        self.status_label.setText(f"Готово: {output_path}")
        QMessageBox.information(
            self,
            "Генерация завершена",
            f"GLB создан успешно.\nТип рук: {arm_model}\n\n{output_path}",
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
