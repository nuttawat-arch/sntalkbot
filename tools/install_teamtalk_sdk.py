#!/usr/bin/env python3
"""Install matching TeamTalk5.py + native TeamTalk library from an extracted v5.22a SDK."""
from pathlib import Path
import argparse
import shutil
import sys


def find_one(root: Path, name: str):
    matches = [p for p in root.rglob(name) if p.is_file()]
    if not matches:
        return None
    # Prefer TeamTalkPy/Library paths when several examples include copies.
    matches.sort(key=lambda p: ("teamtalkpy" not in str(p).lower(), "library" not in str(p).lower(), len(p.parts)))
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="Copy TeamTalk Python wrapper and native library from an extracted SDK.")
    parser.add_argument("sdk_dir", help="Directory where the official TeamTalk SDK archive was extracted")
    parser.add_argument("--project", default=str(Path(__file__).resolve().parents[1]), help="SNTalkBot project directory")
    args = parser.parse_args()
    sdk = Path(args.sdk_dir).expanduser().resolve()
    project = Path(args.project).expanduser().resolve()
    if not sdk.is_dir():
        raise SystemExit(f"SDK directory not found: {sdk}")

    wrapper = find_one(sdk, "TeamTalk5.py")
    native_name = "TeamTalk5.dll" if sys.platform == "win32" else "libTeamTalk5.so"
    native = find_one(sdk, native_name)
    if not wrapper or not native:
        raise SystemExit(
            f"Could not find matching TeamTalk5.py and {native_name} under {sdk}. "
            "Make sure you extracted the official SDK, not the normal TeamTalk client."
        )
    project.mkdir(parents=True, exist_ok=True)
    shutil.copy2(wrapper, project / "TeamTalk5.py")
    shutil.copy2(native, project / native_name)
    print(f"Installed wrapper: {wrapper}")
    print(f"Installed native library: {native}")
    print("TeamTalk SDK files installed. Run tools/check_environment.py next.")


if __name__ == "__main__":
    main()
