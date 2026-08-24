# -*- coding: utf-8 -*-
"""Intentional short command aliases, separated by bot role.

The three profiles are deliberately isolated:
- Common aliases exist in Full, Player, and Server Manager.
- Player aliases exist only when the Player module is enabled.
- Manager aliases exist only when server-management modules are enabled.

Full Bot receives the union.  This prevents a legacy media shortcut from
accidentally exposing a Server Manager feature in Player-only mode (or vice
versa).  Aliases resolve to canonical handlers; they never duplicate handlers.
"""

COMMON_ALIASES = {
    "h": "help",
    "mi": "myinfo",
    "a": "about",          # TTMediaBot legacy
    "cid": "gcid",
    "ad": "admins",
    "sr": "search",
    "ci": "channelinput",
}

MANAGER_ALIASES = {
    "ic": "intercept",
    "w": "weather",
    "rep": "report",
    "rs": "restart",
    "sd": "shutdown",
    "wb": "welcomebroadcast",
    "ma": "moveall",
    "cl": "clearlog",
    "lg": "language",
    "vt": "voicetx",
    "prv": "private",
    "msgs": "messages",
    "wa": "whoall",
    "us": "users",
    "ac": "account",
    "acs": "accounts",
    "j": "join",
    "bc": "blockcmd",
    "nn": "noname",
    "nt": "notify",
    "unt": "unotify",
    "ft": "filter",
    "wc": "welcome",
    "rbt": "reboot",
    "tm": "ttsmode",
    "gv": "get_voices",
    "vc": "voice",
    "sc": "save",          # TTMediaBot legacy, Manager/Full only
}

PLAYER_ALIASES = {
    "ap": "autoplay",
    "ch": "channel",
    "pf": "playfav",
    "df": "delfav",
    "c": "select",         # TTMediaBot legacy
    "fl": "favorites",
    "sh": "shuffle",
    "cz": "csize",
    "gl": "l",             # TTMediaBot legacy: get current link
    "sb": "-",             # TTMediaBot legacy: seek backward
    "sf": "+",             # TTMediaBot legacy: seek forward
    "ptm": "pttsmode",
    "pvo": "pvoice",
    "pvl": "pvoices",
    "ptr": "pttsrate",
    "pts": "pttsspeed",
}

# Flat literal kept for validators/site tooling that consume one alias catalog.
# Keep this exactly equal to the union of the three role maps above.
COMMAND_ALIASES = {
    "h": "help", "mi": "myinfo", "a": "about",
    "cid": "gcid", "ad": "admins", "sr": "search", "ci": "channelinput",
    "ic": "intercept", "w": "weather", "rep": "report", "rs": "restart",
    "sd": "shutdown", "wb": "welcomebroadcast", "ma": "moveall",
    "cl": "clearlog", "lg": "language", "vt": "voicetx", "prv": "private",
    "msgs": "messages", "wa": "whoall", "us": "users", "ac": "account",
    "acs": "accounts", "j": "join", "bc": "blockcmd",
    "nn": "noname", "nt": "notify", "unt": "unotify", "ft": "filter",
    "wc": "welcome", "rbt": "reboot", "tm": "ttsmode", "gv": "get_voices",
    "vc": "voice", "sc": "save",
    "ap": "autoplay", "ch": "channel", "pf": "playfav", "df": "delfav",
    "c": "select", "fl": "favorites", "sh": "shuffle",
    "cz": "csize", "gl": "l", "sb": "-", "sf": "+",
    "ptm": "pttsmode", "pvo": "pvoice", "pvl": "pvoices",
    "ptr": "pttsrate", "pts": "pttsspeed",
}
