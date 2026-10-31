"""Offline English/Russian UI translations, independent of persisted model data."""
from __future__ import annotations

import json
from pathlib import Path
import re
from string import Formatter

from PySide6.QtCore import QLocale, QTranslator, QLibraryInfo
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QCheckBox, QGroupBox, QLineEdit, QTabWidget, QWidget

_catalog = json.loads(Path(__file__).with_name("translations_ru.json").read_text(encoding="utf-8"))
_language = "en"
_qt_translator = None


def language() -> str:
    return _language


def set_language(value: str) -> None:
    global _language, _qt_translator
    _language = value if value in ("en", "ru") else "en"
    app = QApplication.instance()
    if app is not None and _qt_translator is not None:
        app.removeTranslator(_qt_translator)
    _qt_translator = None
    QLocale.setDefault(QLocale("ru_RU" if _language == "ru" else "en_US"))
    if app is not None and _language == "ru":
        translator = QTranslator()
        paths = [Path(__file__).parent, Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))]
        for path in paths:
            if translator.load(str(path / "qtbase_ru.qm")):
                app.installTranslator(translator)
                _qt_translator = translator
                break


def tr(text: str, _depth: int = 0) -> str:
    if _language == "en" or _depth > 3:
        return text
    if text in _catalog:
        return _catalog[text]
    for source, target in _catalog.items():
        if "{" not in source:
            continue
        fields = []
        pattern = ""
        for literal, field, _, _ in Formatter().parse(source):
            pattern += re.escape(literal)
            if field is not None:
                fields.append(field)
                pattern += "([\\s\\S]*?)"
        match = re.fullmatch(pattern, text)
        if match is None:
            continue
        values = dict(zip(fields, match.groups()))
        for key in ("exc", "spec.label", "animation_list"):
            if key in values:
                values[key] = tr(values[key], _depth + 1)
        return "".join(literal + (values.get(field, "") if field is not None else "")
                       for literal, field, _, _ in Formatter().parse(target))
    return text


def set_text(widget, source: str) -> None:
    widget.setProperty("i18n_text", source)
    widget.setText(tr(source))


def apply_to_window(window: QWidget) -> None:
    locale = QLocale("ru_RU" if _language == "ru" else "en_US")
    for widget in [window, *window.findChildren(QWidget)]:
        widget.setLocale(locale)
        properties = [("toolTip", "setToolTip", "i18n_tooltip")]
        if isinstance(widget, (QLabel, QPushButton, QCheckBox)):
            properties.append(("text", "setText", "i18n_text"))
        if isinstance(widget, QGroupBox):
            properties.append(("title", "setTitle", "i18n_title"))
        if isinstance(widget, QLineEdit):
            properties.append(("placeholderText", "setPlaceholderText", "i18n_placeholder"))
        for getter, setter, key in properties:
            source = widget.property(key)
            if source is None:
                source = getattr(widget, getter)()
                widget.setProperty(key, source)
            getattr(widget, setter)(tr(source))
        if isinstance(widget, QTabWidget):
            for index in range(widget.count()):
                key = f"i18n_tab_{index}"
                source = widget.property(key)
                if source is None:
                    source = widget.tabText(index)
                    widget.setProperty(key, source)
                widget.setTabText(index, tr(source))
