"""Build and validate a portable Windows release with the approved interpreter."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chibi_skin_generator import __version__


def main() -> None:
    if sys.version_info[:3] != (3, 11, 9) or sys.platform != "win32":
        raise SystemExit("Build requires Windows and Python 3.11.9.")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm",
        "--windowed", "--onedir", "--noupx", "--name", "ChibiSkinGenerator",
        "--paths", str(ROOT / "src"), "--exclude-module", "pytest",
        "--collect-data", "trimesh", "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
        str(ROOT / "launch.py")]
    if "--package-only" not in sys.argv:
        subprocess.run(command, cwd=ROOT, check=True)
    folder = ROOT / "dist" / "ChibiSkinGenerator"
    # Qt 6.11 uses Windows' built-in ICU. A generic ICU found on the build
    # machine's PATH has incompatible exports and must not shadow the OS DLL.
    for name in ("icuuc.dll", "icudt78.dll"):
        candidate = folder / "_internal" / name
        if candidate.exists():
            candidate.unlink()
    for name in ("README_EN.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, folder / name)
    # Preserve dependency notices alongside their binaries.
    licenses = folder / "licenses"
    licenses.mkdir(exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        (licenses / "CPython").mkdir(exist_ok=True)
        shutil.copy2(python_license, licenses / "CPython" / "LICENSE.txt")
    import importlib.metadata
    for distribution in importlib.metadata.distributions():
        for file in distribution.files or ():
            if "license" in str(file).lower() or str(file).lower().endswith("copying"):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = licenses / distribution.metadata["Name"] / str(file)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    report_dir = ROOT / "build" / "frozen-smoke"
    import os
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    completed = subprocess.run([str(folder / "ChibiSkinGenerator.exe"), "--self-test", str(report_dir)],
                               cwd=ROOT / "dist", env=environment, timeout=90)
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    if completed.returncode or not report.get("ok"):
        raise SystemExit(f"Frozen smoke test failed: {report}")
    archive = ROOT / "dist" / f"ChibiSkinGenerator-{__version__}-Windows-x64-English.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                bundle.write(file, file.relative_to(folder.parent))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Verified release: {archive}")


if __name__ == "__main__":
    main()
