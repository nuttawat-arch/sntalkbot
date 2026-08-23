#!/usr/bin/env python3
"""Check the external/runtime requirements for SN TalkBot."""
from pathlib import Path
import importlib
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# TeamTalk5.py loads its native library by name, so make the project root
# discoverable before importing the wrapper on Linux.
if sys.platform != "win32":
    current_ld = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = str(ROOT) + ((":" + current_ld) if current_ld else "")
checks = []


def add(name, ok, detail=""):
    checks.append((name, bool(ok), detail))


def command_version(command, args=("--version",)):
    exe = shutil.which(command)
    if not exe:
        return None, "not found"
    try:
        proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=10, check=False)
        text = (proc.stdout or proc.stderr or "").strip().splitlines()
        return exe, (text[0] if text else "found")
    except Exception as exc:
        return exe, str(exc)


add("Python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0])

deno_exe, deno_detail = command_version("deno")
deno_ok = False
if deno_exe:
    match = re.search(r"deno\s+(\d+)\.(\d+)", deno_detail, re.I)
    deno_ok = bool(match and tuple(map(int, match.groups())) >= (2, 3))
add("Deno >= 2.3", deno_ok, deno_detail)

ffmpeg_exe, ffmpeg_detail = command_version("ffmpeg")
add("FFmpeg", bool(ffmpeg_exe), ffmpeg_detail)

native = ROOT / ("TeamTalk5.dll" if sys.platform == "win32" else "libTeamTalk5.so")
wrapper = ROOT / "TeamTalk5.py"
add(native.name, native.exists(), str(native))
add("TeamTalk5.py", wrapper.exists(), str(wrapper))
if native.exists() and wrapper.exists():
    try:
        tt = importlib.import_module("TeamTalk5")
        version = tt.getVersion()
        if isinstance(version, bytes):
            version = version.decode("utf-8", errors="replace")
        version_text = str(version)
        add("TeamTalk SDK >= 5.22", version_text.lower().startswith("5.22"), version_text)
    except Exception as exc:
        add("TeamTalk SDK import", False, str(exc))

for module in ("yt_dlp", "edge_tts", "gtts", "mpv", "requests", "paramiko", "deep_translator"):
    try:
        m = importlib.import_module(module)
        version = getattr(m, "__version__", getattr(m, "version", "installed"))
        add(module, True, str(version))
    except Exception as exc:
        add(module, False, str(exc))

failed = False
for name, ok, detail in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}")
    failed |= not ok
raise SystemExit(1 if failed else 0)
