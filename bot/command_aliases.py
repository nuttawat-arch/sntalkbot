# -*- coding: utf-8 -*-
"""Intentional short command aliases.

Aliases are resolved by CommandHandler and never register a second handler.
This keeps the canonical command set unambiguous while preserving fast,
screen-reader-friendly shortcuts. Commands accept the same arguments as their canonical target.
"""

COMMAND_ALIASES = {
    # Common
    "h": "help",
    "mi": "myinfo",
    "ab": "about",
    "cid": "gcid",
    "ad": "admins",
    "sr": "search",

    # Server Manager / Full
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

    # Player / Full
    "ap": "autoplay",
    "ch": "channel",
    "pf": "playfav",
    "df": "delfav",
    "sel": "select",
    "fl": "favorites",
    "sh": "shuffle",
    "cz": "csize",
    "ptm": "pttsmode",
    "pvo": "pvoice",
    "pvl": "pvoices",
    "ptr": "pttsrate",
    "pts": "pttsspeed",
}
