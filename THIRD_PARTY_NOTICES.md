# Third-party software and source availability

This application uses **Qt / PySide6 6.11.1 under LGPLv3**, dynamically linked.
The portable release contains QtBase (Core, Gui, Widgets and Network), PySide6,
Shiboken and the QtBase Russian translation. No Qt source changes were made.
Optional QML, PDF and GPL-only Virtual Keyboard binaries/plugins are removed
from the distribution; their presence in an installed development environment
is independent of what is shipped in this application.

## LGPL library rights

LGPLv3/GPLv3 license texts and upstream notices are included in `licenses/`.
You may study, modify, replace and reverse-engineer the LGPL components for
purposes permitted by their licenses, including debugging modifications.
Nothing in this distribution restricts rights granted by those licenses.

Keep a backup of the program folder. Replace matching ABI-compatible Qt DLLs
in `_internal/PySide6/`; PySide6 modules are in the same directory and Shiboken
is in `_internal/shiboken6/`. Keep matching Python 3.11 x64 bindings and the
platform plugin `plugins/platforms/qwindows.dll`. No application signature
check or DRM blocks replacement. This is a one-folder PyInstaller bundle,
not static Qt linkage.

## Complete unmodified upstream sources

`Qt-LGPL-Sources-6.11.1.zip` is supplied beside the program in the same release,
with equivalent recipient access and no additional charge:
https://github.com/Chahmetski/ChibiSkinGenerator/releases

It contains original source archives, including upstream build instructions,
and a manifest with SHA-256 hashes:

- https://download.qt.io/official_releases/qt/6.11/6.11.1/submodules/qtbase-everywhere-src-6.11.1.tar.xz
- https://download.qt.io/official_releases/qt/6.11/6.11.1/submodules/qttranslations-everywhere-src-6.11.1.tar.xz
- https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.1-src/pyside-setup-everywhere-src-6.11.1.tar.xz

Additional build documentation:
https://doc.qt.io/qt-6.11/build-sources.html
https://doc.qt.io/qtforpython-6/building_from_source/index.html

Redistributors must preserve notices and provide equivalent access to the
corresponding library sources, including their modifications. A private
repository alone does not provide source access to recipients without access.

## Other components

CPython 3.11.9 (PSF), Pillow (HPND), NumPy (BSD), trimesh (MIT) and their bundled
components retain their own copyright and license notices in `licenses/`.
PyInstaller's bootloader exception permits bundled applications to use a
different application license.

No open-source license has yet been selected for the project's own code.
Dependency obligations apply independently of that decision.

## Skins and Minecraft branding

Input skins and embedded output textures retain their original authors' rights.
Conversion does not grant permission to redistribute or sell a skin. Example
skins must only be redistributed with the required permission.

NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR MICROSOFT.

This is a practical notice, not a legal opinion or warranty of compliance for
every modification, distribution method or jurisdiction.
