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
import tempfile
import shutil
import configparser

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

def role_alias_catalog():
    path = ROOT / "bot" / "command_aliases.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    wanted = {"COMMON_ALIASES", "PLAYER_ALIASES", "MANAGER_ALIASES"}
    result = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        for name in names:
            if name in wanted:
                value = ast.literal_eval(node.value)
                result[name] = {str(k).strip().lstrip("/").lower(): str(v).strip().lstrip("/").lower() for k, v in value.items()}
    missing = sorted(wanted - set(result))
    if missing:
        fail("role alias mappings missing: " + ", ".join(missing))
    return result


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

# Any legacy hard-coded utility version must track the release VERSION file.
release_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
utils_source_version = (ROOT / "bot" / "utils.py").read_text(encoding="utf-8")
version_match = re.search(r'^\s*VERSION\s*=\s*["\']([^"\']+)["\']', utils_source_version, re.MULTILINE)
if not version_match or version_match.group(1) != release_version:
    fail(f"BotUtils.VERSION does not match VERSION: utility={version_match.group(1) if version_match else '?'} release={release_version}")
else:
    ok(f"hard-coded utility version matches release VERSION ({release_version})")

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
    fail("duplicate registered commands: " + ", ".join(x for x in duplicates))
else:
    ok(f"registered command names are unique ({len(names)})")

# Avoid keeping multiple public aliases that execute exactly the same handler in the
# same command module. This catches duplicate handler registrations.
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
        f"{path}:{cls}:{handler} -> {','.join(aliases)}"
        for path, cls, handler, aliases in same_handler
    ))
else:
    ok("no same-handler command aliases remain")

aliases = alias_catalog()
role_aliases = role_alias_catalog()
common_aliases = role_aliases.get("COMMON_ALIASES", {})
player_aliases = role_aliases.get("PLAYER_ALIASES", {})
manager_aliases = role_aliases.get("MANAGER_ALIASES", {})
if role_aliases:
    role_keys = [set(common_aliases), set(player_aliases), set(manager_aliases)]
    overlap = sorted((role_keys[0] & role_keys[1]) | (role_keys[0] & role_keys[2]) | (role_keys[1] & role_keys[2]))
    composed = {}
    for mapping in (common_aliases, manager_aliases, player_aliases):
        composed.update(mapping)
    if overlap:
        fail("role alias names overlap across Common/Player/Manager: " + ", ".join(overlap))
    elif composed != aliases:
        fail("flat COMMAND_ALIASES does not exactly match role alias union")
    else:
        ok(f"aliases are role-separated (Common={len(common_aliases)}, Player={len(player_aliases)}, Manager={len(manager_aliases)}, total={len(aliases)})")
alias_names = set(aliases)
canonical_names = set(names)
if alias_names.intersection(canonical_names):
    fail("alias names collide with canonical commands: " + ", ".join(x for x in sorted(alias_names.intersection(canonical_names))))
else:
    ok(f"intentional short aliases do not collide with canonical commands ({len(aliases)})")
unknown_targets = sorted(set(aliases.values()) - canonical_names)
if unknown_targets:
    fail("aliases target unknown canonical commands: " + ", ".join(x for x in unknown_targets))
else:
    ok("all short aliases target canonical commands")
# Keep the command language predictable: one shorthand per canonical command.
# Multiple aliases for the same intent make screen-reader help noisier and make
# future role migrations ambiguous.
from collections import defaultdict
_alias_targets = defaultdict(list)
for alias_name, target_name in aliases.items():
    _alias_targets[target_name].append(alias_name)
duplicate_target_aliases = {target: sorted(names_) for target, names_ in _alias_targets.items() if len(names_) > 1}
if duplicate_target_aliases:
    fail("multiple short aliases target the same canonical command: " + "; ".join(
        f"{target}<-{','.join(names_)}" for target, names_ in sorted(duplicate_target_aliases.items())
    ))
else:
    ok("each canonical command has at most one short alias")
required_aliases = {
    "h": "help", "a": "about", "rs": "restart", "sd": "shutdown", "w": "weather",
    "ap": "autoplay", "ch": "channel", "pf": "playfav",
    "gl": "l", "c": "select", "sb": "-", "sf": "+",
    "j": "join", "sc": "save", "vt": "voicetx",
}
wrong_required = [f"{a}->{aliases.get(a, '?')}" for a, target in required_aliases.items() if aliases.get(a) != target]
if wrong_required:
    fail("required usability aliases missing or incorrect: " + ", ".join(wrong_required))
else:
    ok("required usability aliases are present with one shorthand per intent (h/a + Player gl/c/sb/sf + Manager j/sc/vt)")

# Command-dispatch regression test without importing the native TeamTalk SDK.
def validate_prefix_free_dispatch():
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
    # Reproduce TeamTalkPy on Linux: Python str is encoded for outbound calls while
    # incoming UTF-8 bytes are decoded to Python str. This exact shape caused
    # r7.4.2 to pass the old str-only validator but fail in the real event loop.
    fake.ttstr = lambda value: value.encode("utf-8") if isinstance(value, str) else (bytes(value).decode("utf-8") if isinstance(value, (bytes, bytearray, memoryview)) else value)
    previous = sys.modules.get("TeamTalk5")
    root_str = str(ROOT)
    added_root = root_str not in sys.path
    if added_root:
        sys.path.insert(0, root_str)
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
        handler.register_command("select", lambda msg, *args: calls.append(("SELECT",) + tuple(args)))
        handler.register_alias("c", "select")
        handler.register_command(".", lambda msg, *args: calls.append(("NEXTSEARCH",) + tuple(args)))
        handler.register_command(",", lambda msg, *args: calls.append(("PREVSEARCH",) + tuple(args)))

        def msg(text, msg_type, to_user_id=None, channel_id=None):
            if to_user_id is None:
                to_user_id = 99 if msg_type in (_MsgType.MSGTYPE_USER, _MsgType.MSGTYPE_CUSTOM) else 0
            if channel_id is None:
                channel_id = 0 if msg_type in (_MsgType.MSGTYPE_USER, _MsgType.MSGTYPE_CUSTOM) else 7
            return types.SimpleNamespace(
                szMessage=text, nMsgType=msg_type, nFromUserID=10,
                nToUserID=to_user_id, nChannelID=channel_id, szFromUsername="user"
            )

        # Private prefix-free commands and aliases.
        private = msg("h", _MsgType.MSGTYPE_USER)
        assert handler.channel_input_allowed(private, False) is True
        assert handler.handle_message(private) is True
        assert calls[-1] == ("HELP",)
        assert handler.handle_message(msg("s", _MsgType.MSGTYPE_CUSTOM)) is True
        assert calls[-1] == ("STOP",)
        assert handler.handle_message(msg("p รักเธอนะ", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("PLAY", "รักเธอนะ")
        assert handler.handle_message(msg("ap on", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("AP", "on")
        assert handler.handle_message(msg("\u200bh\ufeff", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("HELP",)
        # Slash remains optional compatibility input.
        assert handler.handle_message(msg("/ap off", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("AP", "off")
        assert handler.handle_message(msg("c 56", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("SELECT", "56")
        assert handler.handle_message(msg(". 34", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("NEXTSEARCH", "34")
        assert handler.handle_message(msg(", 34", _MsgType.MSGTYPE_USER)) is True
        assert calls[-1] == ("PREVSEARCH", "34")

        # Explicit USER/CUSTOM stays private even with an odd non-zero channel id.
        odd_private = msg("h", _MsgType.MSGTYPE_USER, to_user_id=0, channel_id=7)
        assert handler.is_channel_message(odd_private) is False
        assert handler.channel_input_allowed(odd_private, False) is True
        assert handler.handle_message(odd_private) is True
        assert calls[-1] == ("HELP",)

        # Channel/Broadcast: exactly the same prefix-free command syntax works
        # when Channel Input is ON. Slash form also remains accepted.
        channel = msg("h", _MsgType.MSGTYPE_CHANNEL)
        assert handler.is_channel_message(channel) is True
        assert handler.channel_input_allowed(channel, True) is True
        assert handler.handle_message(channel) is True
        assert calls[-1] == ("HELP",)
        assert handler.handle_message(msg("s", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("STOP",)
        assert handler.handle_message(msg("p รักเธอนะ", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("PLAY", "รักเธอนะ")
        assert handler.handle_message(msg("ap on", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("AP", "on")
        assert handler.handle_message(msg("h", _MsgType.MSGTYPE_BROADCAST)) is True
        assert calls[-1] == ("HELP",)
        assert handler.handle_message(msg("/h", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("HELP",)
        assert handler.handle_message(msg(". 34", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("NEXTSEARCH", "34")
        assert handler.handle_message(msg(", 34", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("PREVSEARCH", "34")
        assert handler.handle_message(msg("\u200b/\ufeffh", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls[-1] == ("HELP",)

        # Channel Input OFF gates all normal channel text; Private remains usable.
        assert handler.channel_input_allowed(channel, False) is False
        assert handler.channel_input_allowed(msg("/h", _MsgType.MSGTYPE_CHANNEL), False) is False
        assert handler.channel_input_allowed(private, False) is True

        class _Scalar:
            def __init__(self, value): self.value = value
        opaque_channel = msg("h", _Scalar(999), to_user_id=0, channel_id=_Scalar(7))
        assert handler.is_channel_message(opaque_channel) is True
        assert handler.channel_input_allowed(opaque_channel, False) is False
        assert handler.handle_message(opaque_channel) is True
        assert calls[-1] == ("HELP",)

        # Unknown ordinary chat is not a registered command. The legacy error
        # hint applies only to direct USER text, never Channel/Broadcast/CUSTOM
        # conversation and never our own message.
        before = list(calls)
        unknown_private = msg("hello there", _MsgType.MSGTYPE_USER)
        unknown_channel = msg("hello there", _MsgType.MSGTYPE_CHANNEL)
        unknown_custom = msg("typing", _MsgType.MSGTYPE_CUSTOM)
        assert handler.handle_message(unknown_private) is False
        assert handler.handle_message(unknown_channel) is False
        assert calls == before
        assert handler.should_reply_unknown(unknown_private, 99) is True
        assert handler.should_reply_unknown(unknown_channel, 99) is False
        assert handler.should_reply_unknown(unknown_custom, 99) is False
        own_private = msg("hello there", _MsgType.MSGTYPE_USER)
        own_private.nFromUserID = 99
        assert handler.should_reply_unknown(own_private, 99) is False

        # Canonical blocking also blocks aliases in every context.
        bot.blocked_commands = {"autoplay"}
        before = list(calls)
        assert handler.handle_message(msg("ap on", _MsgType.MSGTYPE_USER)) is True
        assert handler.handle_message(msg("ap on", _MsgType.MSGTYPE_CHANNEL)) is True
        assert handler.handle_message(msg("/ap on", _MsgType.MSGTYPE_CHANNEL)) is True
        assert calls == before
        return True
    except Exception as exc:
        fail(f"prefix-free private/channel command-dispatch regression: {exc!r}")
        return False
    finally:
        if previous is None:
            sys.modules.pop("TeamTalk5", None)
        else:
            sys.modules["TeamTalk5"] = previous
        if added_root and root_str in sys.path:
            sys.path.remove(root_str)

if validate_prefix_free_dispatch():
    ok("prefix-free commands work in private + channel/broadcast with Linux bytes/Windows str; slash is optional compatibility; channel-input OFF still rejects channel text")

command_handler_source = (ROOT / "bot" / "command_handler.py").read_text(encoding="utf-8")
utils_source_for_text = (ROOT / "bot" / "utils.py").read_text(encoding="utf-8")
if "ensure_text" not in command_handler_source or "decode(\"utf-8\"" not in utils_source_for_text:
    fail("TeamTalk incoming-text byte decoding guard is missing")
else:
    ok("TeamTalk incoming bytes are decoded to Unicode before command/moderation parsing")

# Legacy unknown-command response must happen only after real workflows and must
# not answer TeamTalk CUSTOM events such as typing notifications.
sntalkbot_source_for_unknown = (ROOT / "bot" / "sntalkbot.py").read_text(encoding="utf-8")
unknown_text = 'Unknown or invalid command. Send h for help.'
unknown_pos = sntalkbot_source_for_unknown.find(unknown_text)
translator_pos = sntalkbot_source_for_unknown.find("self.translator_cog.handle_whisper_translation(textmessage)")
super_pos = sntalkbot_source_for_unknown.find("super().onCmdUserTextMessage(textmessage)")
if unknown_pos < 0:
    fail("unknown-command fallback is missing")
elif translator_pos < 0 or super_pos < 0 or not (translator_pos < unknown_pos < super_pos):
    fail("unknown-command fallback must run after command/helper workflows and before superclass fallback")
elif 'should_reply_unknown(textmessage, self.getMyUserID())' not in sntalkbot_source_for_unknown:
    fail("unknown-command fallback is not using the tested private-only routing guard")
else:
    ok("unknown Private text gets an h-help hint after real workflows; Channel/CUSTOM chat is not spammed")

# Moderation must stay alive even when Channel Input is disabled, but `filter`
# is the single master switch for all word-list checks. The intended order is:
# master-filter moderation -> Channel Input gate -> command dispatch -> helpers.
sntalkbot_source = (ROOT / "bot" / "sntalkbot.py").read_text(encoding="utf-8")
config_source = (ROOT / "bot" / "config_handler.py").read_text(encoding="utf-8")
general_source = (ROOT / "bot" / "modules" / "general.py").read_text(encoding="utf-8")
player_source = (ROOT / "bot" / "modules" / "player.py").read_text(encoding="utf-8")
admin_source = (ROOT / "bot" / "modules" / "admin.py").read_text(encoding="utf-8")
if "channel_input_enabled" not in config_source or "channel_input_allowed(" not in sntalkbot_source:
    fail("persistent channel-input gate is missing")
else:
    moderation_pos = sntalkbot_source.find("# Word moderation is intentionally independent")
    blacklist_pos = sntalkbot_source.find("check_message_for_blacklist(textmessage)")
    gate_pos = sntalkbot_source.find("channel_input_allowed(")
    dispatch_pos = sntalkbot_source.find("if self.command_handler.handle_message(textmessage):")
    account_pos = sntalkbot_source.find("self.account_request_cog.handle_message(textmessage)")
    if min(moderation_pos, blacklist_pos, gate_pos, dispatch_pos, account_pos) < 0 or not (moderation_pos < blacklist_pos < gate_pos < dispatch_pos < account_pos):
        fail("text callback order must be master-filter moderation -> channel gate -> command -> helper workflows")
    else:
        ok("word moderation runs before channel-input gating; ci off cannot blind an enabled filter")

# `filter` must gate every word-list path, including runtime profile/channel updates.
message_gate = admin_source.find("def check_message_for_blacklist")
message_gate = admin_source.find("if not self.bot.profanity_filter_enabled", message_gate) if message_gate >= 0 else -1
profile_gate = admin_source.find("def check_user_profile_for_blacklist")
profile_gate = admin_source.find("if not self.bot.profanity_filter_enabled", profile_gate) if profile_gate >= 0 else -1
channel_gate = sntalkbot_source.find("def _moderate_channel_metadata")
channel_gate = sntalkbot_source.find("not self.profanity_filter_enabled", channel_gate) if channel_gate >= 0 else -1
if message_gate < 0:
    fail("message blacklist path is not gated by the filter master switch")
elif profile_gate < 0:
    fail("nickname/status blacklist path is not gated by the filter master switch")
elif channel_gate < 0:
    fail("channel-name/topic blacklist path is not gated by the filter master switch")
else:
    ok("filter on/off is the master switch for message, profile, and channel metadata word filtering")

alias_source = (ROOT / "bot" / "command_aliases.py").read_text(encoding="utf-8")
if "register_command('channelinput'" not in general_source or '"ci": "channelinput"' not in alias_source:
    fail("channelinput/ci admin control is missing")
else:
    ok("channelinput command and ci short alias are registered")
if "register_command('intercept'" not in general_source or '"ic": "intercept"' not in alias_source:
    fail("intercept/ic all-channel control is missing")
elif "set_intercept_channel_messages" not in sntalkbot_source or "doUnsubscribe" not in sntalkbot_source:
    fail("intercept toggle does not apply subscribe/unsubscribe changes at runtime")
else:
    ok("intercept/ic toggles server-wide channel interception at runtime")
# All-in-one runtime dashboard/audit must use actual TeamTalk callback names from SDK 5.22a.
required_event_callbacks = [
    "def onCmdUserUpdate(", "def onCmdChannelUpdate(", "def onCmdChannelRemove(",
    "def onCmdServerUpdate(", "def onCmdFileNew(", "def onCmdFileRemove(",
    "def onUserStateChange(",
]
missing_event_callbacks = [name for name in required_event_callbacks if name not in sntalkbot_source]
if missing_event_callbacks:
    fail("runtime TeamTalk event coverage missing: " + ", ".join(missing_event_callbacks))
elif "register_command('status'" not in general_source or "register_command('events'" not in general_source:
    fail("status/events all-in-one commands are not registered")
elif "command arguments/secrets are never stored" not in (ROOT / "bot" / "help.py").read_text(encoding="utf-8"):
    fail("events help does not document secret-safe admin auditing")
elif "used {command_name}" not in (ROOT / "bot" / "command_handler.py").read_text(encoding="utf-8"):
    fail("admin command audit does not record canonical action names")
else:
    ok("status/events use real TeamTalk update/file/state callbacks and admin audit stores no raw command arguments")

if 'value not in ("on", "off")' not in player_source or '"send_channel_messages"' not in player_source or '"status"' not in player_source:
    fail("cm on|off|status playback-channel-message control is incomplete")
else:
    ok("cm supports on/off/status while preserving playback channel-message persistence")

# Canonical multilingual blacklist regression. Thai must live in the same file
# as the preserved legacy English/Arabic entries, while badword.txt remains as a
# backward-compatible supplemental file.
def validate_multilingual_blacklist():
    blacklist_path = ROOT / "blacklist.txt"
    badword_path = ROOT / "badword.txt"
    if not blacklist_path.exists() or not badword_path.exists():
        fail("blacklist.txt or compatibility badword.txt is missing")
        return False
    words = [line.strip().lower() for line in blacklist_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    required_th = {"ควย", "หี", "เย็ด", "ไอเหี้ย", "ไอสัส", "สัส", "เหี้ย"}
    required_legacy = {"fuck", "shit", "bitch", "dick", "fucker", "asshole", "متناك", "كس"}
    missing = sorted((required_th | required_legacy) - set(words))
    if missing:
        fail("canonical multilingual blacklist is missing required legacy/Thai coverage: " + ", ".join(missing))
        return False
    compatibility_words = {
        line.strip().casefold() for line in badword_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing_from_canonical = sorted(compatibility_words - set(words))
    if missing_from_canonical:
        fail("badword.txt contains entries not present in canonical blacklist.txt: " + ", ".join(missing_from_canonical[:20]))
        return False
    spec = importlib.util.spec_from_file_location("validate_bot_utils", ROOT / "bot" / "utils.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = {
        "ไอเหี้ย": True,
        "ไอสัส": True,
        "ค ว ย": True,
        "เย็ดแม่": True,
        "หี": True,
        "หีบใบนี้ใหญ่": False,
        "fuck": True,
        "what the fuck": True,
        "class assignment": False,
        "password reset": False,
        "สวัสดีครับ": False,
    }
    for text, expected in cases.items():
        actual = module.BotUtils.contains_profanity(text, words)
        if actual is not expected:
            fail(f"multilingual blacklist matcher failed for {text!r}: expected {expected}, got {actual}")
            return False
    return True

if validate_multilingual_blacklist():
    ok("canonical blacklist.txt preserves legacy languages, includes Thai, and fully contains compatibility badword.txt")

if 'contains_profanity(message_text, self.bad_words)' in sntalkbot_source:
    fail("legacy supplemental badword warning path still runs separately from canonical blacklist")
elif 'self.bad_words = utils.load_blacklist("blacklist.txt")' not in sntalkbot_source:
    fail("runtime bad-word compatibility list is not sourced from canonical blacklist.txt")
else:
    ok("runtime word moderation uses one canonical multilingual blacklist path")

# Missing optional blacklist.wav must never block the moderation action.
if 'if os.path.exists(audio_path):' not in admin_source or 'unable to play blacklist alert audio' not in admin_source:
    fail("missing blacklist.wav is not handled safely")
else:
    ok("missing optional blacklist.wav cannot abort blacklist enforcement")

# Historical Manager regression: AdminCog.ban_user was a pass-only stub and some
# blacklist paths incorrectly called self.bot.ban_user. Both make blacklist_mode=2 fail.
if "# (existing code ...)" in admin_source or "self.bot.ban_user(" in admin_source:
    fail("blacklist/Manager ban path still contains the legacy placeholder or wrong target")
elif "self.bot.doBan(" not in admin_source or "BannedUser()" not in admin_source:
    fail("AdminCog.ban_user does not implement a real TeamTalk ban operation")
else:
    ok("blacklist_mode=2 uses a real AdminCog ban path instead of the legacy pass-only stub")


def validate_runtime_word_filter_paths():
    """Exercise filter OFF/ON, Thai/English matching, and kick/ban without TeamTalk."""
    fake = types.ModuleType("TeamTalk5")
    class _BanType:
        BANTYPE_NONE = 0
        BANTYPE_CHANNEL = 1
        BANTYPE_IPADDR = 2
        BANTYPE_USERNAME = 4
    class _BannedUser:
        def __init__(self):
            self.szIPAddress = ""
            self.szUsername = ""
            self.uBanTypes = 0
    class _UserType:
        USERTYPE_ADMIN = 2
    class _TextMsgType:
        MSGTYPE_USER = 1
        MSGTYPE_CHANNEL = 2
        MSGTYPE_BROADCAST = 3
        MSGTYPE_CUSTOM = 4
    fake.BanType = _BanType
    fake.BannedUser = _BannedUser
    fake.UserAccount = object
    fake.UserType = _UserType
    fake.TextMsgType = _TextMsgType
    fake.TextMessage = object
    fake.VideoCodec = type("VideoCodec", (), {"__init__": lambda self: setattr(self, "nCodec", 0)})
    fake.ttstr = lambda value: value.encode("utf-8") if isinstance(value, str) else (bytes(value).decode("utf-8") if isinstance(value, (bytes, bytearray, memoryview)) else value)
    previous = sys.modules.get("TeamTalk5")
    previous_paramiko = sys.modules.get("paramiko")
    previous_admin = sys.modules.pop("_sntalkbot_admin_filter_test", None)
    root_str = str(ROOT)
    added_root = root_str not in sys.path
    if added_root:
        sys.path.insert(0, root_str)
    sys.modules["TeamTalk5"] = fake
    if previous_paramiko is None:
        sys.modules["paramiko"] = types.ModuleType("paramiko")
    try:
        spec = importlib.util.spec_from_file_location("_sntalkbot_admin_filter_test", ROOT / "bot" / "modules" / "admin.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        class FakeUser:
            nUserID = 7
            szIPAddress = "203.0.113.9"
            szUsername = "tester"
            szNickname = "tester"
            szStatusMsg = ""
        class _ConfigHandler:
            def __init__(self): self.updates = []
            def update_bot_settings(self, values): self.updates.append(dict(values))
        class Bot:
            profanity_filter_enabled = False
            bot_config = {"blacklist_mode": 1}
            def __init__(self):
                self.kicked=[]; self.bans=[]; self.private=[]; self.config_handler=_ConfigHandler()
            def _(self, text): return text
            def getUser(self, uid): return FakeUser()
            def getMyUserID(self): return 99
            def record_activity(self, *args, **kwargs): pass
            def kick_user(self, uid): self.kicked.append(uid)
            def privateMessage(self, uid, text): self.private.append((uid, str(text)))
            def doBan(self, banned): self.bans.append((banned.uBanTypes, str(banned.szIPAddress), str(banned.szUsername))); return 1
        bot=Bot(); cog=module.AdminCog(bot)
        def msg(text): return types.SimpleNamespace(szMessage=text, nFromUserID=7)

        # Exercise the real filter command handler, including persistence.
        cog.handle_filter_toggle_command(msg("filter on"), "on")
        assert bot.profanity_filter_enabled is True, "filter on handler did not enable master filter"
        assert bot.config_handler.updates[-1] == {"profanity_filter_enabled": True}, "filter on was not persisted"
        cog.handle_filter_toggle_command(msg("filter off"), "off")
        assert bot.profanity_filter_enabled is False, "filter off handler did not disable master filter"
        assert bot.config_handler.updates[-1] == {"profanity_filter_enabled": False}, "filter off was not persisted"

        # Master OFF means no blacklist action at all.
        assert cog.check_message_for_blacklist(msg("fuck ไอเหี้ย")) is False, "filter OFF still enforced"
        assert bot.kicked == [], f"filter OFF kicked {bot.kicked!r}"

        # Master ON: Thai and English canonical entries enforce; false positives do not.
        bot.profanity_filter_enabled=True
        assert cog.check_message_for_blacklist(msg("class assignment password")) is False, "English false positive"
        assert cog.check_message_for_blacklist(msg("หีบใบนี้ใหญ่")) is False, "Thai short-word false positive"
        assert cog.check_message_for_blacklist(msg("fuck")) is True, "English blacklist not enforced"
        assert bot.kicked == [7], f"expected kick [7], got {bot.kicked!r}"
        bot.kicked.clear()
        assert cog.check_message_for_blacklist(msg("ค ว ย")) is True, "spaced Thai blacklist not enforced"
        assert bot.kicked == [7], f"expected kick [7], got {bot.kicked!r}"

        # Ban mode calls the real AdminCog ban implementation then kicks.
        bot.kicked.clear(); bot.bot_config["blacklist_mode"] = 2
        assert cog.check_message_for_blacklist(msg("ไอเหี้ย")) is True, "Thai ban-mode blacklist not enforced"
        assert bot.bans and bot.bans[-1][0] == _BanType.BANTYPE_USERNAME, f"expected username ban, got {bot.bans!r}"
        assert bot.kicked == [7], f"expected kick [7], got {bot.kicked!r}"

        # USER_UPDATE profile moderation shares the same master switch/list.
        bad_profile = types.SimpleNamespace(
            nUserID=8, szNickname="good", szStatusMsg="ค ว ย",
            szIPAddress="203.0.113.10", szUsername="profileuser"
        )
        bot.kicked.clear(); bot.bot_config["blacklist_mode"] = 1
        bot.profanity_filter_enabled = False
        assert cog.check_user_profile_for_blacklist(bad_profile) is False, "filter OFF still moderated profile update"
        bot.profanity_filter_enabled = True
        assert cog.check_user_profile_for_blacklist(bad_profile) is True, "profile update profanity not enforced"
        assert bot.kicked == [8], f"expected updated profile kick [8], got {bot.kicked!r}"
        return True
    except Exception as exc:
        fail(f"runtime word-filter regression: {exc!r}")
        return False
    finally:
        if previous is None:
            sys.modules.pop("TeamTalk5", None)
        else:
            sys.modules["TeamTalk5"] = previous
        if previous_admin is not None:
            sys.modules["_sntalkbot_admin_filter_test"] = previous_admin
        if previous_paramiko is None:
            sys.modules.pop("paramiko", None)
        else:
            sys.modules["paramiko"] = previous_paramiko
        if added_root and root_str in sys.path:
            sys.path.remove(root_str)

if validate_runtime_word_filter_paths():
    ok("runtime filter ON/OFF, Thai/English message matching, profile-update moderation, false-positive guards, kick, and ban paths work")



def validate_status_events_runtime():
    """Exercise the all-in-one dashboard and bounded event viewer without native TeamTalk."""
    fake_tt = types.ModuleType("TeamTalk5")
    class _UserType:
        USERTYPE_ADMIN = 2
    fake_tt.UserType = _UserType
    fake_tt.ttstr = lambda value: value
    previous_tt = sys.modules.get("TeamTalk5")
    previous_wikipedia = sys.modules.get("wikipedia")
    previous_langdetect = sys.modules.get("langdetect")
    previous_requests = sys.modules.get("requests")
    root_str = str(ROOT)
    added_root = root_str not in sys.path
    if added_root:
        sys.path.insert(0, root_str)
    sys.modules["TeamTalk5"] = fake_tt
    # GeneralCog imports these modules for unrelated commands; the dashboard
    # itself must remain testable without performing network work.
    if previous_wikipedia is None:
        wiki = types.ModuleType("wikipedia")
        wiki.exceptions = types.SimpleNamespace(PageError=Exception, DisambiguationError=Exception)
        sys.modules["wikipedia"] = wiki
    if previous_langdetect is None:
        lang = types.ModuleType("langdetect")
        lang.detect = lambda value: "th"
        sys.modules["langdetect"] = lang
    if previous_requests is None:
        sys.modules["requests"] = types.ModuleType("requests")
    try:
        activity_spec = importlib.util.spec_from_file_location("_sntalkbot_activity_test", ROOT / "bot" / "activity.py")
        activity_module = importlib.util.module_from_spec(activity_spec)
        activity_spec.loader.exec_module(activity_module)
        general_spec = importlib.util.spec_from_file_location("_sntalkbot_general_status_test", ROOT / "bot" / "modules" / "general.py")
        general_module = importlib.util.module_from_spec(general_spec)
        general_spec.loader.exec_module(general_module)

        import threading, time as _time
        messages = []
        admin_user = types.SimpleNamespace(nUserID=7, uUserType=2, szNickname="Admin", szUsername="admin")
        other_user = types.SimpleNamespace(nUserID=8, uUserType=0, szNickname="Guest", szUsername="guest")
        player = types.SimpleNamespace(
            media_title="Test Song", is_playing=True, queue=[{"title":"A"},{"title":"B"}],
            queue_lock=threading.RLock(), queue_mode=True, play_mode=2,
            cookiefile=str(ROOT / "does-not-exist.cookies"),
            bundled_cookiefile=str(ROOT / "defaults" / "cookies.txt"),
        )
        class Bot:
            player_enabled = True
            server_management_enabled = True
            playback_config = {"autoplay_enabled": True}
            profanity_filter_enabled = True
            bot_config = {"channel_input_enabled": False, "intercept_channel_messages": True}
            commands_locked = False
            welcome_mode = 1
            def __init__(self):
                self.player = player
                self.started_at = _time.time() - 3661
                self.activity = activity_module.ActivityLog(max_items=20)
            def _(self, text): return text
            def privateMessage(self, uid, text): messages.append(str(text))
            def getServerUsers(self): return [admin_user, other_user]
            def getMyUserID(self): return 99
            def getMyChannelID(self): return 5
            def getChannel(self, channel_id): return types.SimpleNamespace(szName="Music")
            def getUser(self, uid): return admin_user if uid == 7 else other_user
            def is_authorized_user(self, username): return str(username).lower() == "admin"
            def runtime_state_counts(self): return {"voice":1,"media":1,"video":0,"desktop":0}
        bot = Bot()
        bot.activity.record("user", "login", "Guest logged in")
        bot.activity.record("channel", "rename", "Lobby renamed to Music")
        cog = general_module.GeneralCog(bot)
        msg = types.SimpleNamespace(nFromUserID=7, szFromUsername="admin")
        cog.handle_status_command(msg)
        assert any("Full Bot" in line and "users 2" in line for line in messages), messages
        assert any("Player | Test Song" in line and "queue 2" in line for line in messages), messages
        assert any("Manager | filter ON | ci OFF | ic ON" in line for line in messages), messages
        assert any("speaking 1 | media 1" in line for line in messages), messages
        before = len(messages)
        cog.handle_events_command(msg, "2")
        event_lines = messages[before:]
        assert event_lines and "Recent events" in event_lines[0], event_lines
        assert any("channel/rename" in line for line in event_lines[1:]), event_lines
        assert any("user/login" in line for line in event_lines[1:]), event_lines
        return True
    except Exception as exc:
        fail(f"status/events runtime regression: {exc!r}")
        return False
    finally:
        if previous_tt is None: sys.modules.pop("TeamTalk5", None)
        else: sys.modules["TeamTalk5"] = previous_tt
        if previous_wikipedia is None: sys.modules.pop("wikipedia", None)
        else: sys.modules["wikipedia"] = previous_wikipedia
        if previous_langdetect is None: sys.modules.pop("langdetect", None)
        else: sys.modules["langdetect"] = previous_langdetect
        if previous_requests is None: sys.modules.pop("requests", None)
        else: sys.modules["requests"] = previous_requests
        if added_root and root_str in sys.path: sys.path.remove(root_str)

if validate_status_events_runtime():
    ok("role-aware status dashboard and recent-events viewer execute with bounded secret-safe activity data")

def validate_player_queue_and_radio_regressions():
    """Reproduce the end-of-track enqueue race and verify normal radio navigation."""
    fake_tt = types.ModuleType("TeamTalk5")
    fake_tt.ttstr = lambda value: value
    previous_tt = sys.modules.get("TeamTalk5")
    previous_yt = sys.modules.get("yt_dlp")
    root_str = str(ROOT)
    added_root = root_str not in sys.path
    if added_root:
        sys.path.insert(0, root_str)
    sys.modules["TeamTalk5"] = fake_tt
    if previous_yt is None:
        fake_yt = types.ModuleType("yt_dlp")
        fake_yt.YoutubeDL = object
        sys.modules["yt_dlp"] = fake_yt
    try:
        spec = importlib.util.spec_from_file_location("_sntalkbot_player_regression_test", ROOT / "bot" / "modules" / "player.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class ImmediatePool:
            def submit(self, fn, *args, **kwargs):
                return fn(*args, **kwargs)

        class FakeBot:
            def __init__(self):
                self.io_pool = ImmediatePool()
                self.playback_config = {"autoplay_enabled": True}
                self.bot_config = {"gender": ""}
                self.messages = []
            def _(self, text): return text
            def privateMessage(self, uid, text): self.messages.append((uid, str(text)))
            def enableVoiceTransmission(self, enabled): pass
            def doChangeStatus(self, *args): pass
            def get_idle_status_message(self): return "idle"

        player = types.SimpleNamespace(
            queue=[{"title":"A","link":"a"},{"title":"B","link":"b"}],
            queue_index=0, queue_mode=True, queue_lock=__import__("threading").RLock(),
            queue_transition=False, playback_end_transition=True, queue_history=[],
            is_playing=False, play_mode=2, current_link="a", media_title="A",
            collection_results=[], search_results=[{"title":"S1","link":"s1"},{"title":"S2","link":"s2"}],
            current_search_index=0, current_collection_index=0, radio_history=[],
            radio_index=-1, radio_candidates=[], radio_source="youtube",
        )
        bot = FakeBot()
        cog = module.PlayerCog.__new__(module.PlayerCog)
        cog.bot = bot; cog.player = player; cog._ = bot._; cog.loading_new_track = False; cog.autoplay_enabled = True
        plays = []
        def fake_play_queue(index):
            with player.queue_lock:
                player.queue_index = index
                player.queue_transition = False
                plays.append(player.queue[index]["title"])
        cog._play_from_queue = fake_play_queue
        cog._send_playback_message = lambda *args, **kwargs: None
        cog._announce_track = lambda *args, **kwargs: None
        cog._is_in_same_channel = lambda user_id: True
        cog._nickname = lambda user_id: "Tester"

        # First Queue Mode item must announce its queue position before playback
        # enqueues the separate "Now playing" announcement.  _enqueue_queue_items
        # reserves item 1 but the caller explicitly starts only after announcing.
        first_player = types.SimpleNamespace(
            queue=[], queue_index=-1, queue_mode=True, queue_lock=__import__("threading").RLock(),
            queue_transition=False, playback_end_transition=False, queue_history=[],
            is_playing=False, play_mode=2, current_link=None, media_title="",
            collection_results=[], search_results=[], current_search_index=0, current_collection_index=0,
        )
        first_cog = module.PlayerCog.__new__(module.PlayerCog)
        first_cog.bot=bot; first_cog.player=first_player; first_cog._=bot._
        first_cog._nickname=lambda uid: "Tester"
        order=[]
        first_cog._play_from_queue=lambda index: order.append(("play", index))
        first_cog._prefetch_next_for_current=lambda: order.append(("prefetch", None))
        qr=first_cog._enqueue_queue_items([{"title":"First","link":"first"}], user_id=7)
        assert qr[:2] == (1,1) and qr[2] is True and order == [], (qr, order)
        order.append(("queue", qr[0]))
        first_cog._after_queue_enqueue(qr[2])
        assert order == [("queue",1),("play",0)], order
        # Adding while already playing must not interrupt; it should kick prefetch.
        first_player.is_playing=True; first_player.queue_index=0; first_player.queue_transition=False
        qr2=first_cog._enqueue_queue_items([{"title":"Second","link":"second"}], user_id=7)
        first_cog._after_queue_enqueue(qr2[2])
        assert qr2[2] is False and order[-1] == ("prefetch",None), (qr2, order)

        # Queue prefetch must inspect the FIFO queue itself. Queue playback clears
        # collection_results, so relying on the active playlist would leave item 2
        # cold and force yt-dlp work after item 1 already ended.
        scheduled=[]
        first_player.prefetcher=types.SimpleNamespace(schedule=lambda links: scheduled.append(list(links)))
        first_player.queue=[{"title":"First","link":"first"},{"title":"Second","link":"second"},{"title":"Third","link":"third"}]
        first_player.queue_index=0; first_player.queue_mode=True
        module.PlayerCog._prefetch_next_for_current(first_cog)
        assert scheduled == [["second","third"]], scheduled

        # Exact historical race: mpv already flipped is_playing False, while A is
        # still the active queue item. Adding C must append only; it must not play C.
        cog._enqueue_queue_items([{"title":"C","link":"c"}], user_id=7)
        assert [x["title"] for x in player.queue] == ["A","B","C"], player.queue
        assert player.queue[-1].get("added_by") == "Tester" and player.queue[-1].get("added_by_user_id") == 7, player.queue[-1]
        assert isinstance(player.queue[-1].get("added_at"), int), player.queue[-1]
        assert plays == [], f"newest item jumped the queue: {plays!r}"

        # Playback-end removes A only and starts B; then B removes itself and C follows.
        player.playback_end_transition = False
        cog.on_playback_end()
        assert [x["title"] for x in player.queue] == ["B","C"], player.queue
        assert plays == ["B"], plays
        cog.on_playback_end()
        assert [x["title"] for x in player.queue] == ["C"], player.queue
        assert plays == ["B","C"], plays
        assert [x["title"] for x in player.queue_history] == ["A","B"], player.queue_history

        # If Queue Mode remains ON but cq has made the queue empty, playback end
        # must stop instead of leaking into normal M2/Related Radio.
        player.queue = []; player.queue_index = -1; player.queue_mode = True
        player.current_link = "detached-queue-track"; player.play_mode = 2
        related_after_cq = []
        cog._play_next_related = lambda *args, **kwargs: (related_after_cq.append(True) or True)
        cog.on_playback_end()
        assert related_after_cq == [], "empty Queue Mode leaked into Related Radio"
        cog._play_next_related = module.PlayerCog._play_next_related.__get__(cog, module.PlayerCog)

        # Normal mode: n/b are radio history, while . and , remain search-result navigation.
        player.queue_mode = False; player.collection_results = []; player.current_link = "seed"; player.media_title = "Seed"
        player.radio_history = [{"title":"Seed","link":"seed","source":"youtube"}]; player.radio_index = 0
        player.radio_candidates = []
        player.related_radio = lambda seed, source, limit=30: [
            {"title":"Related 1","link":"r1","source":"youtube"},
            {"title":"Related 2","link":"r2","source":"youtube"},
        ]
        radio_plays = []
        cog._play_radio_item = lambda item, **kwargs: (radio_plays.append(item["title"]) or True)
        assert cog._play_next_related(user_id=7, announce_private=True) is True
        assert radio_plays[-1] == "Related 1" and player.radio_index == 1
        assert cog._play_previous_related(user_id=7, announce_private=True) is True
        assert radio_plays[-1] == "Seed" and player.radio_index == 0
        assert cog._play_next_related(user_id=7, announce_private=True) is True
        assert radio_plays[-1] == "Related 1" and player.radio_index == 1

        search_moves = []
        cog._play_search_result_at = lambda index, user_id: (search_moves.append(index) or True)
        msg = types.SimpleNamespace(nFromUserID=7)
        # Earlier queue/end tests intentionally clear global search state; restore
        # a normal-mode search fixture before proving legacy ,/. navigation.
        player.search_results = [{"title":"S1","link":"s1"},{"title":"S2","link":"s2"}]
        player.current_search_index = 0
        cog.handle_next_search_result_selection(msg)
        assert search_moves[-1] == 1, search_moves
        player.current_search_index = 1
        cog.handle_prev_search_result_selection(msg)
        assert search_moves[-1] == 0, search_moves

        # Queue search navigation must be isolated per queued search item.  This
        # reproduces the multi-user bug where a later user's search overwrote the
        # global result buffer and ,/. then replaced queue[-1] regardless of whose
        # item the caller intended to change.
        player.queue_mode = True
        first_results = [
            {"title":"A v1","link":"a1","source":"youtube"},
            {"title":"A v2","link":"a2","source":"youtube"},
            {"title":"A v3","link":"a3","source":"youtube"},
        ]
        second_results = [
            {"title":"B v1","link":"b1","source":"youtube"},
            {"title":"B v2","link":"b2","source":"youtube"},
        ]
        player.queue = [
            {"title":"plain","link":"plain","added_by":"Other"},
            {"title":"A v1","link":"a1","added_by":"Alice","added_by_user_id":11,"added_at":100,
             "_search_results":first_results,"_search_index":0,"_search_source":"youtube"},
            {"title":"B v1","link":"b1","added_by":"Bob","added_by_user_id":12,"added_at":200,
             "_search_results":second_results,"_search_index":0,"_search_source":"youtube"},
        ]
        player.queue_index = 0
        queue_replays = []
        cog._play_from_queue = lambda index: queue_replays.append(index)
        alice_msg = types.SimpleNamespace(nFromUserID=11)
        bob_msg = types.SimpleNamespace(nFromUserID=12)

        # Explicit . 2 changes Alice's queued search even though Bob added later.
        cog.handle_next_search_result_selection(alice_msg, "2")
        assert player.queue[1]["title"] == "A v2" and player.queue[1]["link"] == "a2", player.queue
        assert player.queue[2]["title"] == "B v1", player.queue
        assert player.queue[1]["added_by"] == "Alice" and player.queue[1]["added_at"] == 100, player.queue[1]
        assert queue_replays == [], "changing a pending queue item unexpectedly interrupted playback"

        # Explicit , 2 goes back inside the same private search session.
        cog.handle_prev_search_result_selection(alice_msg, "2")
        assert player.queue[1]["title"] == "A v1", player.queue[1]

        # No-argument legacy behavior targets the newest search-backed queue item.
        cog.handle_next_search_result_selection(bob_msg)
        assert player.queue[2]["title"] == "B v2", player.queue[2]
        assert player.queue[1]["title"] == "A v1", player.queue[1]

        # A queue position that came from a URL/playlist has no alternate search
        # result and must not mutate any other item.
        before = [dict(item) for item in player.queue]
        cog.handle_next_search_result_selection(alice_msg, "1")
        assert player.queue == before, (before, player.queue)

        # n/b remain Related Radio controls even while an explicit playlist is
        # loaded. Playlist position jumps use select <index>; automatic playback
        # still walks the authored collection until its final item.
        player.queue_mode = False
        player.collection_results = [{"title":"P1","link":"p1"},{"title":"P2","link":"p2"}]
        related_cmd = []; list_cmd = []
        cog._play_next_related = lambda **kwargs: (related_cmd.append("n") or True)
        cog._play_previous_related = lambda **kwargs: (related_cmd.append("b") or True)
        cog._play_next_from_active_list = lambda **kwargs: list_cmd.append("next")
        cog._play_previous_from_active_list = lambda **kwargs: list_cmd.append("prev")
        cog.handle_next_track_command(msg)
        cog.handle_previous_track_command(msg)
        assert related_cmd == ["n", "b"], related_cmd
        assert list_cmd == [], f"n/b unexpectedly navigated playlist: {list_cmd!r}"

        # Explicit playlist position selection is 1-based. A long YouTube/YT Music
        # playlist can jump directly to item 56 without walking 55 tracks first.
        player.collection_results = [
            {"title": f"P{i}", "link": f"p{i}"} for i in range(1, 61)
        ]
        player.current_collection_index = 0
        selected_links = []
        player.stop = lambda: None
        def fake_play_stream(link):
            selected_links.append(link)
            player.media_title = next((x["title"] for x in player.collection_results if x["link"] == link), link)
        player.play_stream = fake_play_stream
        cog._prefetch_next_for_current = lambda: None
        cog.handle_select_command(msg, "56")
        assert player.current_collection_index == 55, player.current_collection_index
        assert player.current_link == "p56" and selected_links[-1] == "p56", (player.current_link, selected_links)

        # Reset the playlist fixture before exercising a second, independent pp case.
        player.collection_results = [{"title":"P1","link":"p1"},{"title":"P2","link":"p2"}]

        # pp appends a second playlist without interrupting the active collection.
        player.queue_mode = False; player.is_playing = True; player.current_link = "p1"; player.media_title = "P1"
        player.current_collection_index = 0
        player.fetch_collection_details = lambda link: ("playlist", "Second", [
            {"title":"P3","link":"p3"},{"title":"P4","link":"p4"}
        ])
        player_stops = []
        player.stop = lambda: player_stops.append(True)
        cog._prefetch_next_for_current = lambda: None
        cog._play_collection_task("playlist2", 7, True)
        assert [x["title"] for x in player.collection_results] == ["P1","P2","P3","P4"], player.collection_results
        assert player_stops == [], "pp interrupted current playback"

        # In Queue Mode the whole playlist is appended atomically and the exact
        # 1-based queue range is available to Player TTS/channel announcements.
        player.queue_mode = True; player.queue = [{"title":"Q1","link":"q1"},{"title":"Q2","link":"q2"}]
        player.queue_index = 0; player.queue_transition = False; player.playback_end_transition = False; player.is_playing = True
        announced = []
        cog._announce_queue = lambda **kwargs: announced.append(kwargs)
        cog._play_collection_task("playlist2", 7, True)
        assert [x["title"] for x in player.queue] == ["Q1","Q2","P3","P4"], player.queue
        assert announced and announced[-1].get("start") == 3 and announced[-1].get("end") == 4, announced
        assert announced[-1].get("collection_title") == "Second", announced
        assert announced[-1].get("nickname") == "Tester", announced
        assert all(item.get("added_by") == "Tester" for item in player.queue[-2:]), player.queue[-2:]
        return True
    except Exception as exc:
        fail(f"Player queue/radio regression: {exc!r}")
        return False
    finally:
        if previous_tt is None:
            sys.modules.pop("TeamTalk5", None)
        else:
            sys.modules["TeamTalk5"] = previous_tt
        if previous_yt is None:
            sys.modules.pop("yt_dlp", None)
        else:
            sys.modules["yt_dlp"] = previous_yt
        if added_root and root_str in sys.path:
            sys.path.remove(root_str)

if validate_player_queue_and_radio_regressions():
    ok("queue FIFO/ownership, first-item queue-before-play announcement, pending prefetch, pp/select/search targeting, and normal n/b Radio are regression-tested")

def validate_radio_webpage_resolver():
    """Verify station-homepage/playlist resolution without external network access."""
    previous_mpv = sys.modules.get("mpv")
    previous_yt = sys.modules.get("yt_dlp")
    root_str = str(ROOT)
    added_root = root_str not in sys.path
    if added_root:
        sys.path.insert(0, root_str)
    fake_mpv = types.ModuleType("mpv")
    class FakeMPV:
        pass
    fake_mpv.MPV = FakeMPV
    fake_yt = types.ModuleType("yt_dlp")
    fake_yt.YoutubeDL = object
    sys.modules["mpv"] = fake_mpv
    sys.modules["yt_dlp"] = fake_yt
    try:
        spec = importlib.util.spec_from_file_location("_sntalkbot_radio_resolver_test", ROOT / "bot" / "player.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fixture = """
        <html><head><title>ลูกทุ่ง รักไทย FM 90 Mhz.</title></head><body>
        <script>const streamUrl = "http://radio11.plathong.net:8896/;stream.mp3";</script>
        <audio><source src="/fallback/live.aac"></audio>
        </body></html>
        """
        found = module.Player._extract_stream_candidates(fixture, "https://90rakthai.com/")
        assert found and found[0] == "http://radio11.plathong.net:8896/;stream.mp3", found
        assert "https://90rakthai.com/fallback/live.aac" in found, found

        class FakeResponse:
            def __init__(self, url, content_type, body=b"", headers=None):
                self.url = url
                self.headers = {"content-type": content_type, **(headers or {})}
                self.encoding = "utf-8"
                self._body = body
            def raise_for_status(self): return None
            def iter_content(self, chunk_size=16384):
                yield self._body
            def close(self): return None

        calls = []
        def fake_get(url, **kwargs):
            calls.append(url)
            if url == "https://90rakthai.com/":
                return FakeResponse(url, "text/html; charset=utf-8", fixture.encode("utf-8"))
            raise AssertionError(f"unexpected resolver fetch {url}")

        player = module.Player.__new__(module.Player)
        old_get = module.requests.get
        module.requests.get = fake_get
        try:
            resolved = player._resolve_radio_webpage("https://90rakthai.com/")
        finally:
            module.requests.get = old_get
        assert resolved["url"] == "http://radio11.plathong.net:8896/;stream.mp3", resolved
        assert "90" in resolved["title"], resolved
        assert calls == ["https://90rakthai.com/"], calls

        playlist_html = '<a href="http://example.test/listen.pls">Listen</a>'
        pls_body = b"[playlist]\nFile1=http://stream.example.test:8000/;stream.mp3\nNumberOfEntries=1\n"
        def fake_get_playlist(url, **kwargs):
            if url == "https://station.example/":
                return FakeResponse(url, "text/html", playlist_html.encode())
            if url == "http://example.test/listen.pls":
                return FakeResponse(url, "audio/x-scpls", pls_body)
            raise AssertionError(url)
        module.requests.get = fake_get_playlist
        try:
            resolved = player._resolve_radio_webpage("https://station.example/")
        finally:
            module.requests.get = old_get
        assert resolved["url"] == "http://stream.example.test:8000/;stream.mp3", resolved
        return True
    except Exception as exc:
        fail(f"radio webpage resolver regression: {exc!r}")
        return False
    finally:
        if previous_mpv is None: sys.modules.pop("mpv", None)
        else: sys.modules["mpv"] = previous_mpv
        if previous_yt is None: sys.modules.pop("yt_dlp", None)
        else: sys.modules["yt_dlp"] = previous_yt
        if added_root and root_str in sys.path: sys.path.remove(root_str)

if validate_radio_webpage_resolver():
    ok("radio webpage resolver handles embedded stream URLs and PLS/M3U indirection, including the 90 Rak Thai fixture")

# Prefetch/playback use one yt-dlp lock. If playback arrives while the worker is
# still extracting the same next URL, play_stream must re-check cache *after*
# acquiring that lock; otherwise it extracts the same song twice and creates a
# visible gap between queue items.
_player_core = (ROOT / "bot" / "player.py").read_text(encoding="utf-8")
_play_start = _player_core.find("def play_stream")
_play_end = _player_core.find("def fade_out_and_stop", _play_start)
_play_block = _player_core[_play_start:_play_end]
if _play_block.count("self._prefetch_cache.pop(link, None)") < 2 or "with self._ydl_lock" not in _play_block:
    fail("queue handoff prefetch race guard is missing from play_stream")
else:
    ok("queue handoff reuses in-flight prefetch after yt-dlp lock instead of extracting the next track twice")
_prefetch_start = _player_core.find("    def prefetch_stream_info(self, link):")
_prefetch_end = _player_core.find("    def get_channel_link", _prefetch_start)
_prefetch_block = _player_core[_prefetch_start:_prefetch_end]
if not (
    "with self._ydl_lock:" in _prefetch_block
    and "if info:\n                    self._prefetch_cache[link] = info" in _prefetch_block
    and _prefetch_block.find("self._prefetch_cache[link] = info") < _prefetch_block.find("        except Exception")
):
    fail("prefetch cache is not committed before releasing the yt-dlp lock")
else:
    ok("prefetch commits the next-track cache before releasing yt-dlp lock, closing the last duplicate-extraction race")

# Linux/source line endings are release-critical.  Windows checkouts must not
# re-introduce CRLF into Python/shell/config sources that are copied into Docker.
lf_suffixes = {".py", ".sh", ".ini", ".yml", ".yaml", ".md", ".txt"}
crlf_files = []
for path in ROOT.rglob("*"):
    if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
        continue
    if path.suffix.lower() not in lf_suffixes and path.name not in {"Dockerfile", "VERSION"}:
        continue
    # Netscape cookie exports are accepted from Windows at runtime and TTUHelper
    # normalizes user cookies; the bundled default is data, not an executable.
    if path == ROOT / "defaults" / "cookies.txt":
        continue
    try:
        if b"\r\n" in path.read_bytes():
            crlf_files.append(str(path.relative_to(ROOT)))
    except OSError:
        pass
if crlf_files:
    fail("CRLF found in Linux/source files: " + ", ".join(crlf_files[:12]))
else:
    ok("Linux/Python source line endings are LF-only")

# Official TeamTalk SDK text arrives with Windows line endings. The Linux build
# must normalize the copied wrapper/license so strict validation of the deployed
# image remains meaningful instead of permanently failing on vendor CRLF.
sdk_downloader = (ROOT / "tools" / "download_teamtalk_sdk.py").read_text(encoding="utf-8")
if all(token in sdk_downloader for token in ("def normalize_text_lf", "normalize_text_lf(wrapper_target)", "normalize_text_lf(license_target)")):
    ok("Linux TeamTalk SDK wrapper/license are normalized to LF at image build time")
else:
    fail("Linux TeamTalk SDK text normalization is missing")

# Customer ownership verification is a one-shot TeamTalk login performed inside
# the SNTalkBot image. Keep the password off argv and make the account-type check
# executable in the source validator without the native SDK.
admin_verify_path = ROOT / "tools" / "verify_teamtalk_admin.py"
if not admin_verify_path.is_file():
    fail("one-shot TeamTalk Administrator credential verifier is missing")
else:
    admin_verify_source = admin_verify_path.read_text(encoding="utf-8")
    required = (
        "sys.stdin.buffer.read", "onCmdMyselfLoggedIn", "UserType.USERTYPE_ADMIN",
        "self.doLogin", "probe.doLogout()", "probe.disconnect()", "probe.closeTeamTalk()",
    )
    if all(token in admin_verify_source for token in required) and "argparse" not in admin_verify_source:
        ok("TeamTalk Administrator verifier reads secret JSON from stdin and checks authenticated UserType")
    else:
        fail("TeamTalk Administrator verifier lost stdin/account-type/cleanup safety")
    try:
        fake = types.ModuleType("TeamTalk5")
        class _FakeTeamTalk:
            def __init__(self): pass
            def doLogin(self,*a,**k): return 1
            def connect(self,*a,**k): return True
            def runEventLoop(self): return None
            def doLogout(self): return 1
            def disconnect(self): return True
            def closeTeamTalk(self): return None
        class _FakeUserType:
            USERTYPE_ADMIN = 2
        fake.TeamTalk = _FakeTeamTalk
        fake.UserType = _FakeUserType
        fake.ttstr = lambda value: value.decode() if isinstance(value,(bytes,bytearray)) else str(value or "")
        old_tt = sys.modules.get("TeamTalk5")
        sys.modules["TeamTalk5"] = fake
        try:
            spec = importlib.util.spec_from_file_location("_verify_teamtalk_admin_test", admin_verify_path)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            p1 = mod.AdminProbe("owneradmin","secret")
            p1.onCmdMyselfLoggedIn(7, types.SimpleNamespace(uUserType=2, szUsername="owneradmin"))
            p2 = mod.AdminProbe("normaluser","secret")
            p2.onCmdMyselfLoggedIn(8, types.SimpleNamespace(uUserType=1, szUsername="normaluser"))
            if p1.result and p1.result.get("administrator") is True and p2.result and p2.result.get("administrator") is False:
                ok("TeamTalk credential verifier accepts Administrator and rejects valid non-Administrator accounts")
            else:
                fail("TeamTalk credential verifier account-type regression")
        finally:
            if old_tt is None: sys.modules.pop("TeamTalk5",None)
            else: sys.modules["TeamTalk5"] = old_tt
    except Exception as exc:
        fail(f"TeamTalk credential verifier regression test failed: {exc}")

# The mpv idle callback must raise the queue/end transition guard before it
# exposes is_playing=False. This closes the real cross-thread enqueue window,
# not just the callback-body case reproduced above.
player_core_source = (ROOT / "bot" / "player.py").read_text(encoding="utf-8")
config_default_source = (ROOT / "config_default.ini").read_text(encoding="utf-8")
dockerignore_source = (ROOT / ".dockerignore").read_text(encoding="utf-8")
gitignore_source = (ROOT / ".gitignore").read_text(encoding="utf-8")
playlist_detail_start = player_core_source.find("def _fetch_playlist_details")
playlist_detail_end = player_core_source.find("def _fetch_playlist_videos", playlist_detail_start)
playlist_detail_block = player_core_source[playlist_detail_start:playlist_detail_end]
if (playlist_detail_start < 0
        or 'source = "ytmusic" if "music.youtube.com"' not in playlist_detail_block
        or 'https://music.youtube.com/watch?v=' not in playlist_detail_block):
    fail("YouTube Music playlist entries do not preserve ytmusic source/link identity")
else:
    ok("YouTube Music playlist entries preserve ytmusic source identity for post-playlist Radio")
if "cookiefile_path = /app/data/cookies.txt" not in config_default_source or 'or "/app/data/cookies.txt"' not in player_core_source:
    fail("Player cookie path is not defaulted to persistent /app/data/cookies.txt")
elif 'self.bundled_cookiefile = os.path.join(' not in player_core_source or '"defaults", "cookies.txt"' not in player_core_source:
    fail("Player has no bundled default cookie fallback")
elif 'if self.cookiefile and self._cookiefile_has_records(self.cookiefile):' not in player_core_source or 'elif self.bundled_cookiefile and self._cookiefile_has_records(self.bundled_cookiefile):' not in player_core_source:
    fail("Player cookie precedence does not require a real persistent cookie before the bundled default")
elif 'opts["cookiefile"] = active_cookiefile' not in player_core_source:
    fail("Player does not pass the resolved persistent/bundled cookie file to yt-dlp")
else:
    ok("Player prefers a real persistent/user cookie and falls back to the bundled default when the persistent file is absent or header-only")

bridge_source = (ROOT / "bot" / "dashboard_state.py").read_text(encoding="utf-8") if (ROOT / "bot" / "dashboard_state.py").is_file() else ""
api_source = (ROOT / "bot" / "http_api.py").read_text(encoding="utf-8") if (ROOT / "bot" / "http_api.py").is_file() else ""
sntalk_source = (ROOT / "bot" / "sntalkbot.py").read_text(encoding="utf-8")
if not bridge_source or 'runtime_status.json' not in bridge_source:
    fail("Web runtime-state bridge is missing")
elif 'RuntimeStateWriter(self)' not in sntalk_source or '.runtime_state_writer.start()' not in sntalk_source:
    fail("SNTalkBot does not start the web runtime-state bridge")
elif any(secret in bridge_source for secret in ('server_config.get("password")', 'channel_password', 'telegram_bot_token', 'api_key')):
    fail("Web runtime-state bridge appears to expose secret configuration")
elif not api_source or 'SNTALKBOT_API_PORT' not in api_source or 'SNTALKBOT_API_TOKEN' not in api_source:
    fail("token-protected local realtime HTTP API is missing")
elif 'do_POST' in api_source or 'do_PUT' in api_source or 'do_DELETE' in api_source:
    fail("local bot API exposes a management write method; it must remain read-only")
elif '127.0.0.1' not in api_source or 'Authorization' not in api_source or 'Bearer' not in api_source:
    fail("local bot API is not clearly loopback/token protected")
elif 'LocalStatusApi(self)' not in sntalk_source or '.local_status_api.start()' not in sntalk_source:
    fail("SNTalkBot does not start the optional local realtime API")
elif 'bot_username' not in bridge_source or 'username == bot_username' not in bridge_source or 'room_users_online' not in bridge_source or 'server_users_online' not in bridge_source:
    fail("dashboard state does not separate room/server counts or exclude the bot TeamTalk username from Administrator results")
else:
    ok("secret-free JSON fallback + read-only token-protected loopback HTTP API expose room/server realtime state and exclude the bot ID/username from Administrator results")

# Exercise room-scoped dashboard semantics with fake TeamTalk users.
try:
    from types import SimpleNamespace as _NS
    _spec_state = importlib.util.spec_from_file_location("_snt_dashboard_state_validation", ROOT / "bot" / "dashboard_state.py")
    _state_mod = importlib.util.module_from_spec(_spec_state); _spec_state.loader.exec_module(_state_mod)
    class _Activity:
        def recent(self, _n): return []
    class _FakeBot:
        player_enabled=False; server_management_enabled=True; started_at=0; activity=_Activity()
        server_config={"address":"example","tcp_port":10333,"udp_port":10333,"encrypted":False,"username":"bot-account"}
        bot_config={"nickname":"Bot","status_message":"auto","client_name":"SNTalkBot","channel_input_enabled":True,"intercept_channel_messages":True}
        profanity_filter_enabled=False; commands_locked=False; welcome_mode=0; welcome_broadcast=False
        def getMyUserID(self): return 10
        def getMyChannelID(self): return 7
        def getChannel(self, cid): return _NS(szName="Room A") if cid==7 else None
        def _state_flag(self, name): return {"USERSTATE_VOICE":1,"USERSTATE_MEDIAFILE_AUDIO":2,"USERSTATE_MEDIAFILE_VIDEO":4,"USERSTATE_VIDEOCAPTURE":8,"USERSTATE_DESKTOP":16}.get(name,0)
        def get_idle_status_message(self): return "auto"
        def getServerUsers(self):
            return [
                _NS(nUserID=10,nChannelID=7,uUserType=2,uUserState=0,szUsername="bot-account",szNickname="Bot",szStatusMsg=""),
                _NS(nUserID=11,nChannelID=7,uUserType=2,uUserState=1,nStatusMode=3,szUsername="human-admin",szNickname="Admin",szStatusMsg="ready",szClientName="TeamTalk"),
                _NS(nUserID=12,nChannelID=7,uUserType=1,uUserState=8,nStatusMode=0,szUsername="listener",szNickname="Listener",szStatusMsg="hello",szClientName="WebClient"),
                _NS(nUserID=13,nChannelID=9,uUserType=2,uUserState=16,szUsername="other-admin",szNickname="Other",szStatusMsg=""),
                _NS(nUserID=14,nChannelID=7,uUserType=2,uUserState=0,szUsername="BOT-ACCOUNT",szNickname="Duplicate bot session",szStatusMsg=""),
            ]
    _snap=_state_mod.RuntimeStateWriter(_FakeBot()).build_snapshot()
    assert _snap["users_online"]==2 and _snap["room_users_online"]==2, _snap
    assert _snap["server_users_online"]==3, _snap
    assert _snap["admins_online_count"]==2 and _snap["admins_in_room_count"]==1, _snap
    assert [x["username"] for x in _snap["admins_online"]]==["human-admin","other-admin"], _snap
    assert [x["username"] for x in _snap["room_users"]]==["human-admin","listener"], _snap
    assert _snap["room_users"][0]["status_mode"]==3 and _snap["room_users"][0]["client_name"]=="TeamTalk", _snap
    assert _snap["teamtalk_activity"]=={"speaking":1,"media":0,"video":1,"desktop":0}, _snap
    assert _snap["server_teamtalk_activity"]["desktop"]==1, _snap
    ok("realtime dashboard counts people in the bot room, keeps server totals separate, excludes every bot-username session, and exposes safe room-user detail")
except Exception as exc:
    fail(f"room-scoped realtime dashboard runtime test failed: {exc!r}")

# Exercise the standalone HTTP transport with a real loopback socket.
try:
    import socket, urllib.request, urllib.error, os as _os
    _spec = importlib.util.spec_from_file_location("_snt_http_api_validation", ROOT / "bot" / "http_api.py")
    _mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)
    _sock = socket.socket(); _sock.bind(("127.0.0.1", 0)); _port = _sock.getsockname()[1]; _sock.close()
    class _Writer:
        def build_snapshot(self): return {"connected": True, "admins_online_count": 1, "admins_online": [{"username":"human-admin"}]}
    class _Bot:
        runtime_state_writer = _Writer()
    _old_port=_os.environ.get("SNTALKBOT_API_PORT"); _old_token=_os.environ.get("SNTALKBOT_API_TOKEN"); _old_bind=_os.environ.get("SNTALKBOT_API_BIND")
    _os.environ["SNTALKBOT_API_PORT"]=str(_port); _os.environ["SNTALKBOT_API_TOKEN"]="validation-token"; _os.environ["SNTALKBOT_API_BIND"]="127.0.0.1"
    _api=_mod.LocalStatusApi(_Bot()); assert _api.start()
    try:
        _bad=urllib.request.Request(f"http://127.0.0.1:{_port}/v1/status")
        try:
            urllib.request.urlopen(_bad,timeout=2); raise AssertionError("unauthorized request unexpectedly succeeded")
        except urllib.error.HTTPError as exc:
            assert exc.code==401
        _good=urllib.request.Request(f"http://127.0.0.1:{_port}/v1/status",headers={"Authorization":"Bearer validation-token"})
        with urllib.request.urlopen(_good,timeout=2) as resp:
            _payload=__import__("json").loads(resp.read().decode())
        assert _payload["connected"] is True and _payload["api"]["realtime"] is True
        ok("local realtime HTTP API rejects unauthenticated reads and serves token-authenticated status on loopback")
    finally:
        _api.stop()
        for _k,_v in (("SNTALKBOT_API_PORT",_old_port),("SNTALKBOT_API_TOKEN",_old_token),("SNTALKBOT_API_BIND",_old_bind)):
            if _v is None: _os.environ.pop(_k,None)
            else: _os.environ[_k]=_v
except Exception as exc:
    fail(f"local realtime HTTP API runtime test failed: {exc!r}")
required_docker_ignores = {"cookies.txt", "config.ini", ".env", ".env.*"}
actual_docker_ignores = {line.strip() for line in dockerignore_source.splitlines() if line.strip() and not line.lstrip().startswith("#")}
missing_docker_ignores = sorted(required_docker_ignores - actual_docker_ignores)
if missing_docker_ignores:
    fail(f"Docker build context can include runtime credentials: missing .dockerignore entries {missing_docker_ignores}")
else:
    if "!defaults/cookies.txt" not in actual_docker_ignores:
        fail("bundled default cookie is excluded from Docker build context")
    else:
        ok("Docker build context blocks accidental root cookies/config/.env secrets while allowing only the bundled defaults/cookies.txt bootstrap")
default_cookie_path = ROOT / "defaults" / "cookies.txt"
entrypoint_source = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
if not default_cookie_path.is_file():
    fail("legacy bundled default YouTube cookie is missing")
else:
    try:
        records = []
        for raw_line in default_cookie_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw_line or (raw_line.startswith("#") and not raw_line.startswith("#HttpOnly_")):
                continue
            cols = raw_line.split("\t")
            if len(cols) >= 7:
                records.append(cols)
        if not records or not all("youtube.com" in cols[0] for cols in records):
            fail("bundled default cookie is not a valid YouTube Netscape cookie set")
        elif 'if [ ! -f "$RUNTIME_COOKIES" ] && [ -f "$DEFAULT_COOKIES" ]' not in entrypoint_source:
            fail("entrypoint does not bootstrap default cookies only when the persistent cookie is absent")
        elif 'DEFAULT_COOKIES="/app/defaults/cookies.txt"' not in entrypoint_source:
            fail("entrypoint default cookie path is incorrect")
        else:
            ok(f"bundled default YouTube cookie bootstrap is present ({len(records)} records) and never overwrites a persistent replacement")
    except Exception as exc:
        fail(f"unable to validate bundled default cookies: {exc!r}")
if "cookies.txt" not in gitignore_source:
    fail("Git ignore rules do not protect cookies.txt")
elif "!defaults/cookies.txt" not in gitignore_source:
    fail("Git ignore rules also hide the bundled defaults/cookies.txt, so git archive would omit the default")
else:
    ok("Git ignores personal cookies but explicitly allows the bundled defaults/cookies.txt")
cookie_guide_path = ROOT / "YOUTUBE_COOKIES_TH.md"
cookie_export_path = ROOT / "tools" / "export_youtube_cookies.ps1"
if not cookie_guide_path.is_file() or not cookie_export_path.is_file():
    fail("YouTube cookie guide/export helper is missing from the package")
else:
    cookie_guide_source = cookie_guide_path.read_text(encoding="utf-8")
    cookie_export_source = cookie_export_path.read_text(encoding="utf-8")
    required_cookie_guide = ("-ListProfiles", "chrome://version", "about:profiles", "robots.txt", "private/incognito")
    missing_cookie_guide = [token for token in required_cookie_guide if token not in cookie_guide_source]
    if missing_cookie_guide:
        fail("YouTube cookie guide is missing profile/export steps: " + ", ".join(missing_cookie_guide))
    elif "[switch]$ListProfiles" not in cookie_export_source or "Show-BrowserProfiles" not in cookie_export_source:
        fail("Windows cookie export helper does not expose browser profile listing")
    else:
        ok("YouTube cookie guide/export helper include browser-profile discovery and private/incognito workflow")
idle_start = player_core_source.find("def _on_idle_active")
idle_end = player_core_source.find("def set_output_device", idle_start)
idle_block = player_core_source[idle_start:idle_end]
transition_pos = idle_block.find("self.playback_end_transition = True")
not_playing_pos = idle_block.find("self.is_playing = False")
if idle_start < 0 or transition_pos < 0 or not_playing_pos < 0 or transition_pos > not_playing_pos:
    fail("mpv idle transition guard must be raised before is_playing=False")
else:
    ok("mpv idle boundary is guarded before is_playing=False, closing the last-second enqueue window")

# Queue playback must not retain a stale playlist/radio that could resume after
# clearing or leaving the queue.
queue_play_start = player_source.find("def _play_from_queue")
queue_play_end = player_source.find("def handle_pause_resume_command", queue_play_start)
queue_play_block = player_source[queue_play_start:queue_play_end]
if "self.player.clear_collection()" not in queue_play_block or "self.player.clear_radio_history()" not in queue_play_block:
    fail("queue playback does not isolate stale collection/radio state")
else:
    ok("queue playback isolates stale collection/radio state before starting queued audio")

# Related playback should use YouTube's Mix/Radio surfaces first, not quietly
# regress to advancing the ordinary search-results array.
player_core_radio = player_core_source[player_core_source.find("def related_radio"):player_core_source.find("def reset_radio_history")]
if "RDAMVM{video_id}" not in player_core_radio or "list=RD{video_id}&start_radio=1" not in player_core_radio:
    fail("YouTube/YouTube Music radio surface construction is missing")
else:
    ok("related playback constructs YouTube Mix and YouTube Music Radio surfaces before fallback search")

# About must expose developer contact + active role + dr usage, but must not
# advertise the report service base URL as a user-facing page.
required_contact = ["nuttawat", "SN Family", "nutblind2545t@gmail.com", "0637457797"]
required_about_block = ["dr <your message>", "Full Bot", "Player Bot", "Server Manager Bot"]
about_start = general_source.find("def handle_about_command")
about_end = general_source.find("def handle_gcid_command", about_start)
about_block = general_source[about_start:about_end]
if any(value not in general_source for value in required_contact) or any(value not in about_block for value in required_about_block):
    fail("about command is missing role/contact/dr information")
elif "DEVELOPER_REPORT_BASE_URL" in about_block or "Developer reports:" in about_block:
    fail("about command still exposes the non-form report service URL")
else:
    ok("about shows bot role/contact and dr usage without advertising the support-service URL")


# Existing persistent Docker configs must not be forced into the interactive
# setup wizard when a release adds a new optional setting. Reproduce the r7.3
# failure by deleting channel_input_enabled from a complete config and verify
# that ConfigHandler restores it from the schema default without stdin.
def validate_noninteractive_config_migration():
    fake_tt = types.ModuleType("TeamTalk5")
    fake_tt.ttstr = lambda value: str(value)
    fake_tt.TeamTalk = lambda: None
    fake_mpv = types.ModuleType("mpv")
    previous_tt = sys.modules.get("TeamTalk5")
    previous_mpv = sys.modules.get("mpv")
    sys.modules["TeamTalk5"] = fake_tt
    sys.modules["mpv"] = fake_mpv
    try:
        spec = importlib.util.spec_from_file_location(
            "validate_config_handler", ROOT / "bot" / "config_handler.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            config_path = Path(td) / "config.ini"
            shutil.copyfile(ROOT / "config_default.ini", config_path)
            parser = configparser.ConfigParser()
            parser.read(config_path, encoding="utf-8")
            parser.remove_option("bot", "channel_input_enabled")
            with config_path.open("w", encoding="utf-8") as handle:
                parser.write(handle)

            module.ConfigHandler(str(config_path))
            migrated = configparser.ConfigParser()
            migrated.read(config_path, encoding="utf-8")
            if not migrated.getboolean("bot", "channel_input_enabled", fallback=False):
                fail("old config did not auto-migrate channel_input_enabled=True")
                return False
        return True
    except Exception as exc:
        fail(f"non-interactive config migration regression: {exc}")
        return False
    finally:
        if previous_tt is None:
            sys.modules.pop("TeamTalk5", None)
        else:
            sys.modules["TeamTalk5"] = previous_tt
        if previous_mpv is None:
            sys.modules.pop("mpv", None)
        else:
            sys.modules["mpv"] = previous_mpv

if validate_noninteractive_config_migration():
    ok("old persistent config auto-migrates new optional settings without an interactive Docker prompt")

# Guard the ordering that caused the outage: optional migration must happen
# before validation/wizard logic, and non-interactive required failures must be
# explicit rather than falling through to input()/getpass().
read_config_pos = config_source.find("def read_config_file")
migrate_call_pos = config_source.find("self._migrate_missing_optional_settings()", read_config_pos)
validate_call_pos = config_source.find("self._validate_config()", read_config_pos)
if migrate_call_pos < 0 or validate_call_pos < 0 or migrate_call_pos > validate_call_pos:
    fail("optional config migration must run before config validation")
elif "sys.stdin.isatty()" not in config_source:
    fail("non-interactive config validation guard is missing")
else:
    ok("config migration runs before validation and Docker cannot fall into the interactive setup wizard")

required_player_tts = {"ptts", "pttsmode", "pvoice", "pvoices", "pttsrate", "pttsspeed"}
if not required_player_tts.issubset(set(names)):
    fail("Player TTS control commands missing: " + ", ".join('/' + x for x in sorted(required_player_tts - set(names))))
else:
    ok("Player TTS controls are registered with distinct command names")

if "dr" not in names:
    fail("dr official developer report command is missing")
else:
    ok("dr official developer report command is registered")

# Static role map: Player-only must not expose Manager TTS/admin commands and
# Manager-only must not expose Player commands. General dr remains common.
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
manager_modules = set().union(*(commands_in_class(name) for name in (
    "AdminCog", "JailCog", "TTSCog", "TranslatorCog", "AccountRequestCog", "UserManager"
)))
manager_general = {"weather", "report", "intercept", "events"}
manager_only = manager_modules | manager_general
general_registered = commands_in_class("GeneralCog")
common_only = general_registered - manager_general
role_collision = sorted(player_only.intersection(manager_only))
if role_collision:
    fail("Player/Manager role-specific command collision: " + ", ".join(x for x in role_collision))
else:
    ok(f"role command groups are disjoint (Common={len(common_only)}, Player={len(player_only)}, Manager={len(manager_only)}, Full={len(common_only | player_only | manager_only)})")

if role_aliases:
    bad_common = sorted(set(common_aliases.values()) - common_only)
    bad_player = sorted(set(player_aliases.values()) - player_only)
    bad_manager = sorted(set(manager_aliases.values()) - manager_only)
    if bad_common or bad_player or bad_manager:
        fail(f"role alias target leak: common={bad_common} player={bad_player} manager={bad_manager}")
    else:
        ok("Common/Player/Manager aliases target only commands owned by the same role")

player_admin_utilities = {"cc", "csize", "cm"}
if not player_admin_utilities.issubset(player_only) or player_admin_utilities.intersection(manager_only):
    fail("Player cache/message controls must live only in PlayerCog: cc csize cm")
else:
    ok("Player cache/message controls are no longer exposed by Manager-only mode")

help_entries = help_catalog()
help_names = []
for syntax, _ in help_entries:
    if syntax.startswith("/"):
        fail(f"help syntax still uses a slash prefix: {syntax!r}")
        continue
    name = syntax.split()[0].lower()
    help_names.append(name)

help_duplicates = sorted({x for x in help_names if help_names.count(x) > 1})
if help_duplicates:
    fail("duplicate help commands: " + ", ".join(help_duplicates))
else:
    ok(f"all help syntaxes are prefix-free and unique ({len(help_names)})")

missing_help = sorted(set(names) - set(help_names))
extra_help = sorted(set(help_names) - set(names))
if missing_help:
    fail("registered commands missing from help: " + ", ".join(missing_help))
else:
    ok("every registered command exists in help")
if extra_help:
    fail("help entries without a registered command: " + ", ".join(extra_help))
else:
    ok("help contains no stale command entries")

# The shipped Thai command reference mirrors runtime help output. Commands are
# prefix-free in both Private and Channel; keep each line within TeamTalk limits.
commands_th = ROOT / "COMMANDS_TH.md"
th_lines = [
    line for line in commands_th.read_text(encoding="utf-8").splitlines()
    if " : " in line and line.split(" : ", 1)[0].split()[0].lstrip("/").lower() in set(names)
] if commands_th.exists() else []
th_names = [line.split(" : ", 1)[0].split()[0].lstrip("/").lower() for line in th_lines]
if any(line.startswith("/") for line in th_lines):
    fail("COMMANDS_TH.md contains slash-prefixed command syntax")
else:
    ok("COMMANDS_TH.md presents prefix-free syntax for both private and channel use")
if len(th_lines) != len(names) or set(th_names) != set(names):
    fail("COMMANDS_TH.md does not exactly match registered commands")
else:
    ok(f"COMMANDS_TH.md matches all registered commands ({len(th_lines)})")
commands_th_text = commands_th.read_text(encoding="utf-8") if commands_th.exists() else ""
# Current help/source references must not advertise slash-prefixed command syntax.
help_source = (ROOT / "bot" / "help.py").read_text(encoding="utf-8")
slash_help_tokens = re.findall(r"['\"]/[A-Za-z0-9+.,_-]", help_source)
if slash_help_tokens:
    fail("help.py still advertises slash-prefixed command syntax")
else:
    ok("runtime help advertises prefix-free commands for both private and channel use")
missing_alias_docs = sorted(alias for alias in aliases if not re.search(rf"(?:คำสั่งย่อ|Short aliases):[^\n]*\b{re.escape(alias)}\b", commands_th_text))
if missing_alias_docs:
    fail("COMMANDS_TH.md is missing short-alias documentation: " + ", ".join(missing_alias_docs))
else:
    ok(f"COMMANDS_TH.md documents all intentional aliases ({len(aliases)})")
long_help_lines = [(len(line.encode("utf-8")), line) for line in th_lines if len(line.encode("utf-8")) > 480]
if long_help_lines:
    longest = max(long_help_lines, key=lambda item: item[0])
    fail(f"Thai help line exceeds 480 UTF-8 bytes ({longest[0]}): {longest[1]}")
elif th_lines:
    max_bytes = max(len(line.encode("utf-8")) for line in th_lines)
    ok(f"Thai help lines fit one TeamTalk message (max {max_bytes}/480 UTF-8 bytes)")

missing_th = thai_untranslated()
if missing_th:
    fail(f"Thai locale has {len(missing_th)} untranslated entries")
else:
    ok("Thai locale has no empty translations")


# Official dr must use the central relay, not Telegram credentials embedded in the bot.
general_py = (ROOT / "bot" / "modules" / "general.py").read_text(encoding="utf-8")
if "https://report.nuttawat.ddnsfree.com" not in general_py or "/api/report" not in general_py:
    fail("official developer report relay URL is missing")
else:
    ok("official developer report relay URL is embedded")
if '"X-SNTalkBot-Report": "1"' not in general_py:
    fail("dr does not send the official report-client marker expected by Report API 1.0.1")
else:
    ok("dr sends the official X-SNTalkBot-Report marker expected by Report API 1.0.1")
if "send_telegram_notification" in general_py:
    fail("GeneralCog still sends dr directly to Telegram")
else:
    ok("dr no longer sends directly to Telegram")

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
    (True, False): "Player Bot | พิมพ์ h เพื่อดูวิธีใช้",
    (False, True): "Server Manager Bot | พิมพ์ h เพื่อดูวิธีใช้",
    (True, True): "Full Bot (Player + Server Manager) | พิมพ์ h เพื่อดูวิธีใช้",
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
    fail("legacy Player auto status does not migrate to the private h / channel /h wording")
elif identity.effective_status_message("Player Bot | พิมพ์ h เพื่อดูวิธีใช้", True, False) != status_cases[(True, False)]:
    fail("r7.4 Player auto status does not migrate to the private h / channel /h wording")
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
