from __future__ import annotations

import json
from pathlib import Path

import pytest

from chibi_skin_generator.preset_storage import PresetError, PresetStorage, sanitize_preset_name
from chibi_skin_generator.proportions import (
    COMPACT_CHIBI,
    ProportionSettings,
    get_builtin_preset,
)


def test_user_preset_json_round_trip_and_unknown_fields(tmp_path: Path) -> None:
    storage = PresetStorage(tmp_path / "presets")
    settings = ProportionSettings(head_size=1.23, arm_angle=12.5, leg_gap=0.08)
    saved = storage.save("My: Chibi?", settings)
    assert saved.name == "My_ Chibi_"

    payload = json.loads(saved.path.read_text(encoding="utf-8"))
    payload["settings"]["future_parameter"] = 123
    saved.path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = storage.load(saved.name)
    assert loaded.settings == settings
    assert payload["format_version"] == 1


def test_missing_fields_use_safe_defaults(tmp_path: Path) -> None:
    storage = PresetStorage(tmp_path)
    path = tmp_path / "Partial.json"
    path.write_text(
        json.dumps({"format_version": 1, "name": "Partial", "settings": {"head_size": 1.2}}),
        encoding="utf-8",
    )
    loaded = storage.load("Partial")
    assert loaded.settings.head_size == pytest.approx(1.2)
    assert loaded.settings.body_width == pytest.approx(ProportionSettings().body_width)


def test_corrupted_json_and_invalid_values_are_readable_errors(tmp_path: Path) -> None:
    storage = PresetStorage(tmp_path)
    (tmp_path / "Broken.json").write_text("{ definitely broken", encoding="utf-8")
    with pytest.raises(PresetError, match="повреждённый JSON"):
        storage.load("Broken")

    (tmp_path / "Invalid.json").write_text(
        json.dumps({"format_version": 1, "settings": {"head_size": 99}}),
        encoding="utf-8",
    )
    with pytest.raises(PresetError, match="Некорректные параметры"):
        storage.load("Invalid")


def test_builtin_presets_cannot_be_overwritten_or_deleted(tmp_path: Path) -> None:
    storage = PresetStorage(tmp_path)
    with pytest.raises(PresetError, match="нельзя перезаписать"):
        storage.save(COMPACT_CHIBI, ProportionSettings())
    with pytest.raises(PresetError, match="нельзя удалить"):
        storage.delete(COMPACT_CHIBI)
    assert get_builtin_preset(COMPACT_CHIBI) == ProportionSettings()


def test_preset_name_sanitization() -> None:
    assert sanitize_preset_name('  Hero<>:"/\\|?*  ') == "Hero_________"
    with pytest.raises(PresetError):
        sanitize_preset_name("   ...   ")
