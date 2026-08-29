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
    "rs": "restart",
    "sd": "shutdown",
    "rep": "report",
    "cl": "clearlog",
    "lg": "language",
    "vt": "voicetx",
    "bc": "blockcmd",
    "sc": "save",          # TTMediaBot legacy, bot-local in every profile
}

MANAGER_ALIASES = {
    "ic": "intercept",
    "gb": "globalbroadcast",
    "w": "weather",
    "wb": "welcomebroadcast",
    "ma": "moveall",
    "prv": "private",
    "msgs": "messages",
    "wa": "whoall",
    "us": "users",
    "ac": "account",
    "acs": "accounts",
    "j": "join",
    "nn": "noname",
    "nt": "notify",
    "unt": "unotify",
    "ft": "filter",
    "wc": "welcome",
    "rbt": "reboot",
    "tm": "ttsmode",
    "gv": "get_voices",
    "vc": "voice",
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
    "cid": "gcid", "ad": "admins", "sr": "search", "ci": "channelinput", "rs": "restart",
    "sd": "shutdown", "rep": "report", "cl": "clearlog", "lg": "language",
    "vt": "voicetx", "bc": "blockcmd", "sc": "save",
    "ic": "intercept", "gb": "globalbroadcast", "w": "weather",
    "wb": "welcomebroadcast", "ma": "moveall",
    "wa": "whoall", "us": "users", "ac": "account",
    "acs": "accounts", "j": "join",
    "nn": "noname", "nt": "notify", "unt": "unotify", "ft": "filter",
    "wc": "welcome", "rbt": "reboot", "tm": "ttsmode", "gv": "get_voices",
    "vc": "voice", "prv": "private", "msgs": "messages",
    "ap": "autoplay", "ch": "channel", "pf": "playfav", "df": "delfav",
    "c": "select", "fl": "favorites", "sh": "shuffle",
    "cz": "csize", "gl": "l", "sb": "-", "sf": "+",
    "ptm": "pttsmode", "pvo": "pvoice", "pvl": "pvoices",
    "ptr": "pttsrate", "pts": "pttsspeed",
}
