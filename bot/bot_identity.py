# -*- coding: utf-8 -*-

LEGACY_AUTO_STATUS_MESSAGES = {"sn talkbot", "auto"}


def role_status_message(player_enabled: bool, server_management_enabled: bool) -> str:
    """Return the clear default idle status for the active feature profile."""
    if player_enabled and server_management_enabled:
        return "Full Bot (Player + Server Manager) | พิมพ์ help เพื่อดูคำสั่ง"
    if player_enabled:
        return "Player Bot | พิมพ์ help เพื่อดูคำสั่ง"
    if server_management_enabled:
        return "Server Manager Bot | พิมพ์ help เพื่อดูคำสั่ง"
    return "SN TalkBot | พิมพ์ help เพื่อดูคำสั่ง"


def effective_status_message(configured_status, player_enabled: bool, server_management_enabled: bool) -> str:
    """Resolve auto/legacy default status while preserving an owner's custom status."""
    configured = "" if configured_status is None else str(configured_status).strip()
    if configured.lower() in LEGACY_AUTO_STATUS_MESSAGES:
        return role_status_message(player_enabled, server_management_enabled)
    return configured
