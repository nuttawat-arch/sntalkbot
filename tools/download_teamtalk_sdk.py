#!/usr/bin/env python3
"""Download and install the official TeamTalk SDK runtime files.

This does not bypass TeamTalk SDK licensing. Official SDK binaries are trial
binaries unless a valid SDK license is supplied in config.ini.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

VERSION = "v5.22a"
BASE = f"https://www.bearware.dk/teamtalksdk/{VERSION}"
URLS = {
    "linux-x86_64": f"{BASE}/tt5sdk_{VERSION}_ubuntu22_x86_64.7z",
    "windows-x64": f"{BASE}/tt5sdk_{VERSION}_win64.7z",
}


def detect_platform() -> str:
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    if sys.platform == "win32" and machine in {"x86_64", "amd64"}:
        return "windows-x64"
    raise SystemExit(f"Unsupported platform for automatic SDK download: {sys.platform}/{machine}")


def find_one(root: Path, name: str) -> Path | None:
    matches = [p for p in root.rglob(name) if p.is_file()]
    matches.sort(key=lambda p: ("library" not in str(p).lower(), "teamtalkpy" not in str(p).lower(), len(p.parts)))
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=sorted(URLS), default=None)
    parser.add_argument("--project", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--keep-archive", action="store_true")
    args = parser.parse_args()

    target_platform = args.platform or detect_platform()
    url = URLS[target_platform]
    project = Path(args.project).resolve()
    sevenzip = shutil.which("7z") or shutil.which("7zz")
    if not sevenzip:
        raise SystemExit("7z/7zz is required. On Ubuntu/Debian: sudo apt install p7zip-full")

    with tempfile.TemporaryDirectory(prefix="ttsdk-") as tmp:
        tmpdir = Path(tmp)
        archive = tmpdir / "teamtalk-sdk.7z"
        extract_dir = tmpdir / "sdk"
        extract_dir.mkdir()
        print(f"Downloading official TeamTalk SDK {VERSION} from:\n{url}")
        urllib.request.urlretrieve(url, archive)
        subprocess.run([sevenzip, "x", "-y", f"-o{extract_dir}", str(archive)], check=True)

        wrapper = find_one(extract_dir, "TeamTalk5.py")
        native_name = "TeamTalk5.dll" if target_platform.startswith("windows") else "libTeamTalk5.so"
        native = find_one(extract_dir, native_name)
        license_file = find_one(extract_dir, "License.txt")
        if not wrapper or not native:
            raise SystemExit(f"The downloaded SDK did not contain TeamTalk5.py and {native_name}")

        shutil.copy2(wrapper, project / "TeamTalk5.py")
        shutil.copy2(native, project / native_name)
        if license_file:
            shutil.copy2(license_file, project / "TTSDK_license.txt")
        if args.keep_archive:
            shutil.copy2(archive, project / f"teamtalk-sdk-{VERSION}.7z")

    print(f"Installed TeamTalk SDK runtime files into {project}")
    print("Note: official SDK binaries are trial binaries unless activated with a valid SDK license.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
