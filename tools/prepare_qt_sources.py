"""Fetch unmodified upstream LGPL sources for release assets (build-time only)."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URLS = [
    "https://download.qt.io/official_releases/qt/6.11/6.11.1/submodules/qtbase-everywhere-src-6.11.1.tar.xz",
    "https://download.qt.io/official_releases/qt/6.11/6.11.1/submodules/qttranslations-everywhere-src-6.11.1.tar.xz",
    "https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.1-src/pyside-setup-everywhere-src-6.11.1.tar.xz",
]


def main():
    from pip._vendor import truststore
    truststore.inject_into_ssl()
    folder = ROOT / "build" / "upstream-sources"
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    for url in URLS:
        path = folder / url.rsplit("/", 1)[1]
        if not path.exists():
            with urllib.request.urlopen(url, timeout=180) as response, path.with_suffix(".part").open("wb") as target:
                shutil.copyfileobj(response, target)
            path.with_suffix(".part").replace(path)
        with tarfile.open(path) as archive:
            for member in archive.getmembers():
                name = Path(member.name)
                if not member.isfile() or ".." in name.parts:
                    continue
                if "LICENSES" in name.parts or name.name == "qt_attribution.json" or re.match(r"^(LICENSE|COPYING|COPYRIGHT|NOTICE)([.\-]|$)", name.name, re.I):
                    target = ROOT / "licenses" / "Qt-6.11.1" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
        records.append({"file": path.name, "url": url, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print("Prepared source:", path.name, flush=True)
    (folder / "SOURCES.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", folder / "THIRD_PARTY_NOTICES.md")
    output = ROOT / "dist" / "Qt-LGPL-Sources-6.11.1.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix != ".part":
                archive.write(path, path.name)
    output.with_suffix(".zip.sha256").write_text(hashlib.sha256(output.read_bytes()).hexdigest()+"  "+output.name+"\n")


if __name__ == "__main__":
    main()
