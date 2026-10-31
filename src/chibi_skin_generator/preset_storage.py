"""Safe JSON persistence for user-defined proportion presets."""

from __future__ import annotations

import json
import os
import re
from functools import wraps
from tempfile import NamedTemporaryFile
from dataclasses import dataclass
from pathlib import Path

from .proportions import ProportionError, ProportionSettings, builtin_preset_names

PRESET_FORMAT_VERSION = 1
_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class PresetError(ValueError):
    """Raised for readable user-preset errors."""


def storage_errors(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except OSError as exc:
            raise PresetError(f"Could not complete the preset operation: {exc}") from exc
    return wrapped


@dataclass(frozen=True, slots=True)
class UserPreset:
    name: str
    settings: ProportionSettings
    path: Path


def default_preset_directory() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home()))
    return root / "ChibiSkinGenerator" / "presets"


def sanitize_preset_name(name: str) -> str:
    if not isinstance(name, str):
        raise PresetError("The preset name must be a string.")
    clean = _INVALID_NAME.sub("_", name).strip().rstrip(". ")
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        raise PresetError("Enter a non-empty preset name.")
    clean = clean[:80].rstrip(". ")
    if clean.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1,10)), *(f"LPT{i}" for i in range(1,10))}:
        raise PresetError("This name is reserved by Windows. Choose another name.")
    return clean


class PresetStorage:
    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else default_preset_directory()

    @storage_errors
    def list_names(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted((path.stem for path in self.directory.glob("*.json")), key=str.casefold)

    @storage_errors
    def save(self, name: str, settings: ProportionSettings) -> UserPreset:
        clean_name = sanitize_preset_name(name)
        if clean_name.casefold() in {item.casefold() for item in builtin_preset_names()}:
            raise PresetError("Built-in presets cannot be overwritten.")
        if not isinstance(settings, ProportionSettings):
            raise PresetError("Invalid proportion settings.")

        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{clean_name}.json"
        with NamedTemporaryFile(dir=self.directory, suffix=".json.tmp", delete=False) as handle:
            temporary = Path(handle.name)
        payload = {
            "format_version": PRESET_FORMAT_VERSION,
            "name": clean_name,
            "settings": settings.to_dict(),
        }
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return UserPreset(clean_name, settings, path)

    @storage_errors
    def load(self, name: str) -> UserPreset:
        clean_name = sanitize_preset_name(name)
        path = self.directory / f"{clean_name}.json"
        if not path.is_file():
            raise PresetError(f"User preset not found: {clean_name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PresetError(f"Could not read preset {clean_name!r}: invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise PresetError("The preset file must contain a JSON object.")
        version = payload.get("format_version", PRESET_FORMAT_VERSION)
        if version != PRESET_FORMAT_VERSION:
            raise PresetError(f"Unsupported preset version: {version}")
        stored_name = sanitize_preset_name(str(payload.get("name", clean_name)))
        try:
            settings = ProportionSettings.from_mapping(payload.get("settings", {}))
        except ProportionError as exc:
            raise PresetError(f"Invalid preset settings: {exc}") from exc
        return UserPreset(stored_name, settings, path)

    @storage_errors
    def delete(self, name: str) -> None:
        clean_name = sanitize_preset_name(name)
        if clean_name.casefold() in {item.casefold() for item in builtin_preset_names()}:
            raise PresetError("Built-in presets cannot be deleted.")
        path = self.directory / f"{clean_name}.json"
        if not path.is_file():
            raise PresetError(f"User preset not found: {clean_name}")
        path.unlink()
