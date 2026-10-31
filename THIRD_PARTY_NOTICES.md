# Third-party software

This distribution bundles CPython 3.11.9, PySide6 / Qt, Shiboken, Pillow,
NumPy and trimesh. Their licenses and copyright notices remain applicable.
The portable release includes a `licenses/` directory with notices collected
from the installed dependency distributions. CPython's license is included
with the bundled runtime. Qt and PySide6 libraries are dynamically linked and
remain separate files in `_internal/`; do not remove them from the release.

PySide6 / Qt: LGPLv3 / GPLv3 / commercial licensing, as applicable to each module.
Only the modules required by the application are collected by PyInstaller.
Pillow: HPND license. NumPy: BSD license. trimesh: MIT license.
PyInstaller's bootloader distribution exception permits bundled applications.

Minecraft is a trademark of Mojang / Microsoft. This is an independent tool,
not an official Minecraft product. User-provided skins remain their owners'
work; no third-party skin collection is bundled.
