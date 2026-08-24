# -*- coding: utf-8 -*-

LEGACY_AUTO_STATUS_MESSAGES = {
    "sn talkbot",
    "auto",
    "player bot | พิมพ์ help เพื่อดูคำสั่ง",
    "server manager bot | พิมพ์ help เพื่อดูคำสั่ง",
    "full bot (player + server manager) | พิมพ์ help เพื่อดูคำสั่ง",
    "player bot | พิมพ์ h เพื่อดูคำสั่ง",
    "server manager bot | พิมพ์ h เพื่อดูคำสั่ง",
    "full bot (player + server manager) | พิมพ์ h เพื่อดูคำสั่ง",
    "sn talkbot | พิมพ์ h เพื่อดูคำสั่ง",
    "player bot | ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h",
    "server manager bot | ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h",
    "full bot (player + server manager) | ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h",
    "sn talkbot | ส่วนตัวพิมพ์ h | ในห้องพิมพ์ /h",
    "player bot | พิมพ์ h เพื่อดูวิธีใช้",
    "server manager bot | พิมพ์ h เพื่อดูวิธีใช้",
    "full bot (player + server manager) | พิมพ์ h เพื่อดูวิธีใช้",
    "sn talkbot | พิมพ์ h เพื่อดูวิธีใช้",
}


def role_status_message(player_enabled: bool, server_management_enabled: bool) -> str:
    """Return the clear default idle status for the active feature profile."""
    if player_enabled and server_management_enabled:
        return "Full Bot (Player + Server Manager) | พิมพ์ h เพื่อดูวิธีใช้"
    if player_enabled:
        return "Player Bot | พิมพ์ h เพื่อดูวิธีใช้"
    if server_management_enabled:
        return "Server Manager Bot | พิมพ์ h เพื่อดูวิธีใช้"
    return "SN TalkBot | พิมพ์ h เพื่อดูวิธีใช้"


def effective_status_message(configured_status, player_enabled: bool, server_management_enabled: bool) -> str:
    """Resolve auto/legacy default status while preserving an owner's custom status."""
    configured = "" if configured_status is None else str(configured_status).strip()
    if configured.lower() in LEGACY_AUTO_STATUS_MESSAGES:
        return role_status_message(player_enabled, server_management_enabled)
    return configured
