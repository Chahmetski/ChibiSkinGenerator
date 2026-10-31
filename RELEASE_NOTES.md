# Chibi Skin Generator 0.8.0 — English / Russian

- Switch between English and Russian in the Language selector; the choice is saved.
- Live translation of controls, messages, Qt dialogs and validation errors.
- Existing presets, paths, proportions and animation selections are preserved.
- English README; promotional cover and slogan removed.
- LGPL notices, license texts, a Licenses button and matching dependency sources.
- Optional QML/PDF and GPL-only virtual keyboard binaries excluded from this desktop build.

## Download

Extract `ChibiSkinGenerator-0.8.0-Windows-x64-EN-RU.zip` completely and run
`ChibiSkinGenerator.exe`. Keep `_internal/` beside the EXE. Python and Blender
are not required to generate models. The program runs offline.

`Qt-LGPL-Sources-6.11.1.zip` contains the unmodified QtBase, Qt translations,
PySide6 and Shiboken sources. It is a dependency source bundle, not a program
installer. Redistributors must preserve equivalent source access and notices.
Both archives have SHA-256 checksums.

## Validation

148 tests passed. The packaged executable was checked for switching between
both languages, GUI startup, PNG preview and export of 12 meshes, one skin,
12 joints and 15 animation clips.

Only standard 64×64 PNG skins. No elbows, knees, weapons or root motion.
Auto arm detection is heuristic. Walk/Run remain rotation-only. Animation
transitions and game movement are controlled by the consuming game.
