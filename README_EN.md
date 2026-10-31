# Chibi Skin Generator — Windows portable

Convert a standard 64×64 Minecraft skin PNG into an editable chibi GLB model.
Use the Language selector to switch between English and Russian. The choice
is saved between launches. It runs completely offline.

## Start

Extract the entire ZIP, then run `ChibiSkinGenerator.exe`. Keep `_internal/`
next to the EXE. Python and Blender are not required to generate a model.

## Generate a model

1. Browse for a PNG skin or drag it into the window.
2. Choose Auto, Steve (4-pixel arms), or Alex (3-pixel arms).
3. Select an output folder.
4. Optionally adjust the Proportions tab and select animation clips.
5. Click Generate GLB. Use Open Output Folder to locate the result.

Existing exports are preserved: new files receive a numeric suffix.
The source texture is embedded in the GLB. Import the GLB in Blender using
File → Import → glTF 2.0.

## Proportions and animation

Four built-in presets: Compact Chibi, Balanced Chibi, Big Head, and Legacy.
Save your own presets as JSON; previous settings are restored on startup.
The model has 12 separate meshes and one 12-joint skeleton. Fifteen animation
clips can be selected individually. Clips are in-place; movement, jumping,
transitions, and damage are controlled by your game. Hand and Foot are helper
joints; this rig does not have elbows or knees.

## Troubleshooting

Only actual PNG files sized 64×64 are accepted. If Auto picks the wrong arm
type, select Steve or Alex manually. Ensure the output folder is writable.
Startup failures are recorded in `%LOCALAPPDATA%\ChibiSkinGenerator\error.log`.

The explicit `--self-test <folder>` command runs an offline diagnostic that
opens the interface, checks PNG preview, and exports all 15 clips.

## Developers

Use Windows and Python 3.11.9. Run `setup.bat`, then `run.bat` for development.
Run `build.bat` to create and validate a portable Windows ZIP and SHA-256 file.
Dependency versions are pinned in requirements files. Internet is only needed
for the initial package installation when dependencies are not cached.
