#!/usr/bin/env python3
"""Static release validation for SN TalkBot.

Does not require the TeamTalk native SDK and is safe to run before deployment.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import sys
import importlib.util
import types

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



def alias_catalog():
    path = ROOT / "bot" / "command_aliases.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COMMAND_ALIASES" for t in node.targets):
            value = ast.literal_eval(node.value)
            return {str(k).strip().lstrip("/").lower(): str(v).strip().lstrip("/").lower() for k, v in value.items()}
    fail("COMMAND_ALIASES mapping not found")
    return {}

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

aliases = alias_catalog()
alias_names = set(aliases)
canonical_names = set(names)
if alias_names.intersection(canonical_names):
    fail("alias names collide with canonical commands: " + ", ".join('/' + x for x in sorted(alias_names.intersection(canonical_names))))
else:
    ok(f"intentional short aliases do not collide with canonical commands ({len(aliases)})")
unknown_targets = sorted(set(aliases.values()) - canonical_names)
if unknown_targets:
    fail("aliases target unknown canonical commands: " + ", ".join('/' + x for x in unknown_targets))
else:
    ok("all short aliases target canonical commands")
required_aliases = {"h": "help", "rs": "restart", "sd": "shutdown", "w": "weather", "ap": "autoplay", "ch": "channel", "pf": "playfav"}
wrong_required = [f"/{a}->/{aliases.get(a, '?')}" for a, target in required_aliases.items() if aliases.get(a) != target]
if wrong_required:
    fail("required usability aliases missing or incorrect: " + ", ".join(wrong_required))
else:
    ok("required usability aliases are present (/h /rs /sd /w /ap /ch /pf)")

# Command-dispatch regression test without importing the native TeamTalk SDK.
def validate_slashless_dispatch():
    fake = types.ModuleType("TeamTalk5")
    class _MsgType:
        MSGTYPE_USER = 1
        MSGTYPE_CHANNEL = 2
        MSGTYPE_BROADCAST = 3
        MSGTYPE_CUSTOM = 4
    class _UserType:
        USERTYPE_ADMIN = 2
    fake.TextMessage = object
    fake.TextMsgType = _MsgType
    fake.UserType = _UserType
    fake.ttstr = lambda value: str(value)
    previous = sys.modules.get("TeamTalk5")
    sys.modules["TeamTalk5"] = fake
    try:
        spec = importlib.util.spec_from_file_location("_sntalkbot_command_handler_test", ROOT / "bot" / "command_handler.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        calls = []
        class Bot:
            commands_locked = False
            blocked_commands = set()
            def _(self, text): return text
            def privateMessage(self, user_id, message): pass
            def is_authorized_user(self, username): return False
            def getUser(self, user_id): return None
            def getMyUserID(self): return 99
        bot = Bot()
        handler = module.CommandHandler(bot)
        handler.register_command("help", lambda msg, *args: calls.append(("HELP",) + tuple(args)))
        handler.register_alias("h", "help")
        handler.register_command("autoplay", lambda msg, *args: calls.append(("AP",) + tuple(args)))
        handler.register_alias("ap", "autoplay")
        handler.register_command("s", lambda msg, *args: calls.append(("STOP",) + tuple(args)))
        handler.register_command("p", lambda msg, *args: calls.append(("PLAY",) + tuple(args)))

        def msg(text, msg_type, to_user_id=None, channel_id=None):
            if to_user_id is None:
                to_user_id = 99 if msg_type in (_MsgType.MSGTYPE_USER, _MsgType.MSGTYPE_CUSTOM) else 0
            if channel_id is None:
                channel_id = 0 if to_user_id else 7
            return types.SimpleNamespace(
                szMessage=text, nMsgType=msg_type, nFromUserID=10,
                nToUserID=to_user_id, nChannelID=channel_id, szFromUsername="user"
            )

        assert handler.handle_message(msg("h", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("HELP",)
        assert handler.handle_message(msg("h", _MsgType.MSGTYPE_CUSTOM)) is True
        assert calls[-1] == ("HELP",)
        # A direct destination remains private even with an unexpected type.
        odd_private = msg("h", 999, to_user_id=99, channel_id=0)
        assert handler.handle_message(odd_private) is True
        assert calls[-1] == ("HELP",)

        # Real receive-wrapper regression: some runtime representations can zero
        # nToUserID while still delivering a direct/private message with no
        # channel target.  Channel ID zero + real sender must remain slashless.
        zero_to_private = msg("h", _MsgType.MSGTYPE_USER, to_user_id=0, channel_id=0)
        assert handler.handle_message(zero_to_private) is True
        assert calls[-1] == ("HELP",)

        class _OpaqueType:
            pass
        opaque_private = msg("s", _OpaqueType(), to_user_id=0, channel_id=0)
        assert handler.handle_message(opaque_private) is True
        assert calls[-1] == ("STOP",)
        class _Scalar:
            def __init__(self, value): self.value = value
        scalar_private = msg("s", _Scalar(_MsgType.MSGTYPE_USER), to_user_id=_Scalar(99), channel_id=0)
        assert handler.handle_message(scalar_private) is True
        assert calls[-1] == ("STOP",)
        assert handler.handle_message(msg("s", _MsgType.MSGTYPE_CUSTOM)) is True
        assert calls[-1] == ("STOP",)
        assert handler.handle_message(msg("p รักเธอนะ", _MsgType.MSGTYPE_CUSTOM)) is True
        assert calls[-1] == ("PLAY", "รักเธอนะ")
        before = list(calls)
        assert handler.handle_message(msg("h", _MsgType.MSGTYPE_CHANNEL)) is False
        assert calls == before
        # nToUserID=0 must keep channel text non-command even if nMsgType is wrong.
        assert handler.handle_message(msg("h", _MsgType.MSGTYPE_USER, to_user_id=0, channel_id=7)) is False
        assert calls == before
        assert handler.handle_message(msg("/h", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("HELP",)
        assert handler.handle_message(msg("ap on", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("AP", "on")
        assert handler.handle_message(msg("ap off", _MsgType.MSGTYPE_CUSTOM)) is True
        assert calls[-1] == ("AP", "off")
        assert handler.handle_message(msg("/ap on", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("AP", "on")
        before = list(calls)
        assert handler.handle_message(msg("ap on", _MsgType.MSGTYPE_CHANNEL)) is False
        assert calls == before
        assert handler.handle_message(msg("/ap off", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("AP", "off")
        assert handler.handle_message(msg("hello there", _MsgType.MSGTYPE_USER)) is False

        bot.blocked_commands = {"autoplay"}
        before = list(calls)
        assert handler.handle_message(msg("ap on", _MsgType.MSGTYPE_USER)) is True
        assert calls == before
        return True
    except Exception as exc:
        fail(f"slashless command-dispatch regression: {exc}")
        return False
    finally:
        if previous is None:
            sys.modules.pop("TeamTalk5", None)
        else:
            sys.modules["TeamTalk5"] = previous

if validate_slashless_dispatch():
    ok("private slashless dispatch uses zero-channel routing fallback (h/s/p/ap); channel traffic still requires slash; wrapper variants are covered")

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
player_admin_utilities = {"cc", "csize", "cm"}
if not player_admin_utilities.issubset(player_only) or player_admin_utilities.intersection(manager_only):
    fail("Player cache/message controls must live only in PlayerCog: /cc /csize /cm")
else:
    ok("Player cache/message controls are no longer exposed by Manager-only mode")

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
    if " : " in line and line.split(" : ", 1)[0].split()[0].lstrip("/").lower() in set(names)
] if commands_th.exists() else []
th_names = [line.split(" : ", 1)[0].split()[0].lstrip("/").lower() for line in th_lines]
if any(line.startswith("/") for line in th_lines):
    fail("COMMANDS_TH.md still presents slash-prefixed syntax as primary")
else:
    ok("COMMANDS_TH.md presents slashless syntax as primary")
if len(th_lines) != len(names) or set(th_names) != set(names):
    fail("COMMANDS_TH.md does not exactly match registered commands")
else:
    ok(f"COMMANDS_TH.md matches all registered commands ({len(th_lines)})")
commands_th_text = commands_th.read_text(encoding="utf-8") if commands_th.exists() else ""
missing_alias_docs = sorted(alias for alias in aliases if not re.search(rf"(?:คำสั่งย่อ|Short aliases):[^\n]*\b{re.escape(alias)}\b", commands_th_text))
if missing_alias_docs:
    fail("COMMANDS_TH.md is missing short-alias documentation: " + ", ".join('/' + x for x in missing_alias_docs))
else:
    ok(f"COMMANDS_TH.md documents all intentional aliases ({len(aliases)})")
long_help_lines = [(len(line.encode("utf-8")), line) for line in th_lines if len(line.encode("utf-8")) > 480]
if long_help_lines:
    longest = max(long_help_lines, key=lambda item: item[0])
    fail(f"Thai /help line exceeds 480 UTF-8 bytes ({longest[0]}): {longest[1]}")
elif th_lines:
    max_bytes = max(len(line.encode("utf-8")) for line in th_lines)
    ok(f"Thai help lines fit one TeamTalk message (max {max_bytes}/480 UTF-8 bytes)")

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

sntalkbot_py = (ROOT / "bot" / "sntalkbot.py").read_text(encoding="utf-8")
user_manager_py = (ROOT / "bot" / "user_manager.py").read_text(encoding="utf-8")
if "just_joined" in sntalkbot_py or "_is_fresh_login_event" not in sntalkbot_py or "fresh_login=fresh_login" not in sntalkbot_py:
    fail("startup login replay suppression is missing or legacy just_joined logic remains")
else:
    ok("startup/reconnect user replay is separated from genuine fresh logins")
if "if not fresh_login:" not in user_manager_py:
    fail("UserManager does not suppress login-only side effects during startup replay")
else:
    ok("welcome/notify/pending-message side effects require a genuine fresh login")


# Guard a few regression-prone runtime edges that can be checked statically.
sntalkbot_source = (ROOT / "bot" / "sntalkbot.py").read_text(encoding="utf-8")
if 'message = chunk[last_space + 1:] + message' in sntalkbot_source:
    fail("split_long_message still contains the old boundary-loss bug")
else:
    ok("long-message splitting no longer drops the text after a split boundary")

fresh_start = sntalkbot_source.find("def _is_fresh_login_event")
fresh_end = sntalkbot_source.find("def _is_live_join_event", fresh_start)
fresh_block = sntalkbot_source[fresh_start:fresh_end]
if "_initial_login_user_ids.discard" in fresh_block or "_initial_login_user_ids.add(user_id)" not in fresh_block:
    fail("startup replay IDs are not retained safely through the current TeamTalk session")
else:
    ok("startup/reconnect replay IDs stay suppressed until logout")

direct_getuser = []
pattern_direct_user = re.compile(r"getUser\([^\n]*\)\.")
for path in sorted((ROOT / "bot").rglob("*.py")):
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if pattern_direct_user.search(line):
            direct_getuser.append(f"{path.relative_to(ROOT)}:{lineno}")
if direct_getuser:
    fail("unguarded getUser(...).attribute access remains: " + ", ".join(direct_getuser))
else:
    ok("no direct unguarded getUser(...).attribute access remains")

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


# Role-specific default status must clearly identify each bot profile while preserving custom status.
identity_path = ROOT / "bot" / "bot_identity.py"
spec = importlib.util.spec_from_file_location("sntalkbot_bot_identity", identity_path)
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)
status_cases = {
    (True, False): "Player Bot | ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h",
    (False, True): "Server Manager Bot | ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h",
    (True, True): "Full Bot (Player + Server Manager) | ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h",
}
for flags, expected in status_cases.items():
    actual = identity.role_status_message(*flags)
    if actual != expected:
        fail(f"role status mismatch for {flags}: {actual!r}")
if identity.effective_status_message("SN TalkBot", True, False) != status_cases[(True, False)]:
    fail("legacy SN TalkBot status does not migrate to Player role status")
elif identity.effective_status_message("auto", False, True) != status_cases[(False, True)]:
    fail("auto status does not resolve to Server Manager role status")
elif identity.effective_status_message("Player Bot | พิมพ์ help เพื่อดูคำสั่ง", True, False) != status_cases[(True, False)]:
    fail("r7.1 Player auto status does not migrate to the new h//h wording")
elif identity.effective_status_message("สถานะของฉัน", True, True) != "สถานะของฉัน":
    fail("custom status is not preserved")
else:
    ok("default status identifies Player/Manager/Full modes and preserves custom status")

sntalkbot_status_source = (ROOT / "bot" / "sntalkbot.py").read_text(encoding="utf-8")
player_status_source = (ROOT / "bot" / "modules" / "player.py").read_text(encoding="utf-8")
admin_status_source = (ROOT / "bot" / "modules" / "admin.py").read_text(encoding="utf-8")
if "get_idle_status_message" not in sntalkbot_status_source:
    fail("runtime role-status resolver is not wired into SNTalkBot")
elif "status_msg = self.bot.get_idle_status_message()" not in player_status_source:
    fail("Player does not restore role status after playback")
elif "ttstr(self.bot.get_idle_status_message())" not in admin_status_source:
    fail("admin status/gender path does not resolve automatic role status")
else:
    ok("role status is restored consistently after login/playback/admin changes")

for required in [
    "Dockerfile", "docker-compose.yml", "docker-entrypoint.sh", "run_linux.sh",
    "tools/setup_pulse_bridge.sh", "tools/download_teamtalk_sdk.py",
    "README_TH.md", "DEPENDENCIES_TH.md", "COMMANDS_TH.md",
]:
    if not (ROOT / required).exists():
        fail(f"required release file missing: {required}")

raise SystemExit(1 if FAILED else 0)
