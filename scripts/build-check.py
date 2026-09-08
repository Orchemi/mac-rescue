#!/usr/bin/env python3
"""Compile the native source in a disposable directory without installing Rescue."""
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    if sys.platform != "darwin":
        raise SystemExit("Native build check requires macOS and Xcode Command Line Tools.")
    source = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("rescue_installer", source / "install-rescue.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    with tempfile.TemporaryDirectory(prefix="rescue-build-check-") as folder:
        root = Path(folder)
        (root / "rescue-native").mkdir()
        shutil.copy2(source / "rescue-native/Rescue.swift", root / "rescue-native/Rescue.swift")
        installer.build_native(root)
    print("Native compile: OK (temporary output removed; Rescue was not installed)")


if __name__ == "__main__":
    main()
