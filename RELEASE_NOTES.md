# Chibi Skin Generator 0.8.0 — English Windows portable

The Windows portable release now uses an English interface throughout:
buttons, tabs, settings, tooltips, file dialogs, validation errors and export
messages. Existing settings and user presets are preserved.

## Download and run

Download `ChibiSkinGenerator-0.8.0-Windows-x64-English.zip`, extract it completely,
and run `ChibiSkinGenerator.exe`. Keep `_internal/` beside the executable.
No Python installation is required. The application works offline.

The ZIP includes an English user guide and third-party license notices.

## Features

- Standard Minecraft PNG 64×64 input, Steve / Alex / Auto.
- Base and overlay layers, 12 editable meshes, one 12-joint glTF skin.
- Fifteen optional in-place animation clips.
- Four proportion presets, linked controls and JSON user presets.
- Embedded PNG texture; nearest sampling; Pixel Unlit or PBR Lit.
- Existing exports are preserved through numbered filenames.

## Validation

144 automated tests passed. The packaged EXE was checked for English labels
and locale, interface startup, PNG preview and GLB export with 12 meshes,
one skin, 12 joints and 15 animations. SHA-256 is supplied alongside the ZIP.

## Limits

Only 64×64 PNG skins. No elbows, knees, weapons or root motion.
Auto arm detection is heuristic. Walk/Run are rotation-only; physical foot
placement is limited by the rigid cuboid limbs. Animation transitions and
character movement are controlled by the consuming game.
