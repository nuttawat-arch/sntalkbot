#!/usr/bin/env python3
"""Static release validation for SN TalkBot.

Does not require the TeamTalk native SDK and is safe to run before deployment.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    global FAILED
    FAILED = True


def ok(message: str) -> None:
    print(f"[OK] {message}")


def registered_commands():
    found = []
    for path in sorted((ROOT / "bot").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            fail(f"syntax error while parsing {path.relative_to(ROOT)}: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "register_command" or not node.args:
                continue
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                fail(f"dynamic command name in {path.relative_to(ROOT)}:{node.lineno}")
                continue
            name = first.value.strip().lstrip("/").lower()
            admin = any(
                kw.arg == "admin_only" and isinstance(kw.value, ast.Constant) and bool(kw.value.value)
                for kw in node.keywords
            )
            found.append((name, admin, path.relative_to(ROOT).as_posix(), node.lineno))
    return found


def help_catalog():
    path = ROOT / "bot" / "help.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    entries = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Attribute) and t.attr == "commands" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        for key, val in zip(node.value.keys, node.value.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            syntax = key.value.strip()
            description = None
            if isinstance(val, ast.Call) and val.args and isinstance(val.args[0], ast.Constant):
                description = val.args[0].value
            entries.append((syntax, description or ""))
    return entries


def thai_untranslated():
    po = ROOT / "locales" / "th" / "LC_MESSAGES" / "messages.po"
    text = po.read_text(encoding="utf-8")
    missing = []
    for block in text.split("\n\n"):
        if 'msgid ""' in block:
            continue
        if "msgid " in block and 'msgstr ""' in block:
            line = next((x for x in block.splitlines() if x.startswith("msgid ")), "msgid ?")
            missing.append(line)
    return missing


FAILED = False

# Compile every Python file without importing native dependencies.
for path in ROOT.rglob("*.py"):
    if "__pycache__" in path.parts:
        continue
    try:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    except Exception as exc:
        fail(f"Python compile {path.relative_to(ROOT)}: {exc}")
if not FAILED:
    ok("all Python source files compile")

registered = registered_commands()
names = [x[0] for x in registered]
duplicates = sorted({x for x in names if names.count(x) > 1})
if duplicates:
    fail("duplicate registered commands: " + ", ".join('/' + x for x in duplicates))
else:
    ok(f"registered command names are unique ({len(names)})")

# Avoid keeping multiple public aliases that execute exactly the same handler in the
# same command module. This catches regressions such as /l + /gl or /restart + /rs.
same_handler = []
for path in sorted((ROOT / "bot").rglob("*.py")):
    if "__pycache__" in path.parts:
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        groups = {}
        for node in ast.walk(cls):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "register_command":
                continue
            if len(node.args) < 2 or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                continue
            handler = ast.unparse(node.args[1])
            name = node.args[0].value.strip().lstrip("/").lower()
            groups.setdefault(handler, []).append(name)
        for handler, aliases in groups.items():
            if len(aliases) > 1:
                same_handler.append((path.relative_to(ROOT).as_posix(), cls.name, handler, aliases))
if same_handler:
    fail("multiple command aliases use the same handler: " + "; ".join(
        f"{path}:{cls}:{handler} -> {','.join('/'+x for x in aliases)}"
        for path, cls, handler, aliases in same_handler
    ))
else:
    ok("no same-handler command aliases remain")

forbidden_aliases = {"h", "gl", "rs", "sd"}
remaining_aliases = sorted(forbidden_aliases.intersection(names))
if remaining_aliases:
    fail("retired duplicate aliases still registered: " + ", ".join('/' + x for x in remaining_aliases))
else:
    ok("retired duplicate aliases are absent")

required_player_tts = {"ptts", "pttsmode", "pvoice", "pvoices", "pttsrate", "pttsspeed"}
if not required_player_tts.issubset(set(names)):
    fail("Player TTS control commands missing: " + ", ".join('/' + x for x in sorted(required_player_tts - set(names))))
else:
    ok("Player TTS controls are registered with distinct command names")

if "dr" not in names:
    fail("/dr official developer report command is missing")
else:
    ok("/dr official developer report command is registered")

# Static role map: Player-only must not expose Manager TTS/admin commands and
# Manager-only must not expose Player commands. General /dr remains common.
def commands_in_class(class_name):
    result = set()
    for path in sorted((ROOT / "bot").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name]:
            for node in ast.walk(cls):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "register_command" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        result.add(node.args[0].value.strip().lstrip("/").lower())
    return result

player_only = commands_in_class("PlayerCog")
manager_only = set().union(*(commands_in_class(name) for name in (
    "AdminCog", "JailCog", "TTSCog", "TranslatorCog", "AccountRequestCog", "UserManager"
)))
role_collision = sorted(player_only.intersection(manager_only))
if role_collision:
    fail("Player/Manager role-specific command collision: " + ", ".join('/' + x for x in role_collision))
else:
    ok(f"Player/Manager role-specific commands are disjoint (Player={len(player_only)}, Manager modules={len(manager_only)})")

help_entries = help_catalog()
help_names = []
for syntax, _ in help_entries:
    if not syntax.startswith("/"):
        fail(f"help syntax does not start with '/': {syntax!r}")
        continue
    name = syntax[1:].split()[0].lower()
    help_names.append(name)

help_duplicates = sorted({x for x in help_names if help_names.count(x) > 1})
if help_duplicates:
    fail("duplicate help commands: " + ", ".join('/' + x for x in help_duplicates))
else:
    ok(f"all help syntaxes start with '/' and are unique ({len(help_names)})")

missing_help = sorted(set(names) - set(help_names))
extra_help = sorted(set(help_names) - set(names))
if missing_help:
    fail("registered commands missing from help: " + ", ".join('/' + x for x in missing_help))
else:
    ok("every registered command exists in /help")
if extra_help:
    fail("help entries without a registered command: " + ", ".join('/' + x for x in extra_help))
else:
    ok("/help contains no stale command entries")

# The shipped Thai command reference mirrors runtime /help output. Keep every
# command on one TeamTalk private-message line (the bot splits at 480 UTF-8 bytes).
commands_th = ROOT / "COMMANDS_TH.md"
th_lines = [
    line for line in commands_th.read_text(encoding="utf-8").splitlines()
    if line.startswith("/")
] if commands_th.exists() else []
th_names = [line.split(" : ", 1)[0].split()[0].lstrip("/").lower() for line in th_lines]
if len(th_lines) != len(names) or set(th_names) != set(names):
    fail("COMMANDS_TH.md does not exactly match registered commands")
else:
    ok(f"COMMANDS_TH.md matches all registered commands ({len(th_lines)})")
long_help_lines = [(len(line.encode("utf-8")), line) for line in th_lines if len(line.encode("utf-8")) > 480]
if long_help_lines:
    longest = max(long_help_lines, key=lambda item: item[0])
    fail(f"Thai /help line exceeds 480 UTF-8 bytes ({longest[0]}): {longest[1]}")
elif th_lines:
    max_bytes = max(len(line.encode("utf-8")) for line in th_lines)
    ok(f"Thai /help lines fit one TeamTalk message (max {max_bytes}/480 UTF-8 bytes)")

missing_th = thai_untranslated()
if missing_th:
    fail(f"Thai locale has {len(missing_th)} untranslated entries")
else:
    ok("Thai locale has no empty translations")


# Official /dr must use the central relay, not Telegram credentials embedded in the bot.
general_py = (ROOT / "bot" / "modules" / "general.py").read_text(encoding="utf-8")
if "https://report.nuttawat.ddnsfree.com" not in general_py or "/api/report" not in general_py:
    fail("official developer report relay URL is missing")
else:
    ok("official developer report relay URL is embedded")
if "send_telegram_notification" in general_py:
    fail("GeneralCog still sends /dr directly to Telegram")
else:
    ok("/dr no longer sends directly to Telegram")

# Prevent accidentally publishing Telegram bot tokens or similar bot-token secrets.
secret_pattern = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")
secret_hits = []
for path in ROOT.rglob("*"):
    if not path.is_file() or ".git" in path.parts or path.suffix in {".mo", ".zip", ".7z"}:
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    if secret_pattern.search(text):
        secret_hits.append(path.relative_to(ROOT).as_posix())
if secret_hits:
    fail("possible Telegram bot token leaked in release files: " + ", ".join(secret_hits))
else:
    ok("no Telegram bot-token shaped secrets found in release files")

for forbidden_gui in ["bot/gui.py", "requirements-gui.txt", "setup.bat", "run_bot.bat"]:
    if (ROOT / forbidden_gui).exists():
        fail(f"Linux/Docker-only release still contains GUI/Windows runtime file: {forbidden_gui}")

# Multi-profile functionality must stay removed.
profile_hits = []
pattern = re.compile(r"bot_profiles\.json|--profile|current_profile|update_profile")
for path in list((ROOT / "bot").rglob("*.py")) + [ROOT / "main.py", ROOT / "config_default.ini"]:
    if path.exists():
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pattern.search(line):
                profile_hits.append(f"{path.relative_to(ROOT)}:{lineno}")
if profile_hits:
    fail("legacy multi-profile references remain: " + ", ".join(profile_hits))
else:
    ok("legacy multi-profile references are absent")

for required in [
    "Dockerfile", "docker-compose.yml", "docker-entrypoint.sh", "run_linux.sh",
    "tools/setup_pulse_bridge.sh", "tools/download_teamtalk_sdk.py",
    "README_TH.md", "DEPENDENCIES_TH.md", "COMMANDS_TH.md",
]:
    if not (ROOT / required).exists():
        fail(f"required release file missing: {required}")

raise SystemExit(1 if FAILED else 0)
