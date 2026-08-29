# -*- coding: utf-8 -*-
"""Release notification delivery for SNTalkBot.

GitHub webhook delivery is the primary path. Optional polling exists only as a
fallback for installations that cannot expose the Web Manager webhook endpoint.
No update is installed automatically.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request

from bot.utils import BotUtils as utils


def _version_tuple(value):
    nums = [int(x) for x in re.findall(r"\d+", str(value or ""))[:4]]
    return tuple(nums + [0] * (4 - len(nums))) if nums else (0, 0, 0, 0)


class UpdateNotifier:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config_handler.get_updates_config()
        self._stop = threading.Event()
        self._thread = None
        if self.config.get("enabled") and self.config.get("polling_fallback"):
            self._thread = threading.Thread(
                target=self._poll_loop,
                name="sntalkbot-update-fallback",
                daemon=True,
            )
            self._thread.start()

    def shutdown(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _repository(self):
        return str(self.config.get("repository") or "nuttawat-arch/sntalkbot").strip().lower()

    def _notify(self, version, url=""):
        current = utils.VERSION
        if _version_tuple(version) <= _version_tuple(current):
            return False
        key = "last_notified_version"
        if self.bot.state_store.get_update_state(key, "") == str(version):
            return False
        message = self.bot._(
            "SNTalkBot update available: {version} (current {current})."
        ).format(version=version, current=current)
        if url:
            message += " " + str(url)
        delivered = False
        if self.config.get("broadcast_enabled"):
            try:
                self.bot.send_broadcast_message(message)
                delivered = True
            except Exception:
                pass
        if self.config.get("telegram_enabled"):
            telegram = self.bot.config_handler.get_telegram_config()
            if utils.send_telegram_notification(
                telegram.get("telegram_bot_token"), telegram.get("default_chat_id"), message
            ):
                delivered = True
        # Remember only notifications that were actually delivered. If both
        # outputs are disabled/misconfigured, a later configuration fix can retry.
        if delivered:
            self.bot.state_store.set_update_state(key, str(version))
        return delivered

    def handle_release_event(self, payload):
        if not self.config.get("enabled") or not isinstance(payload, dict):
            return False
        repository = str(payload.get("repository") or "").strip().lower()
        if repository != self._repository():
            return False
        version = str(payload.get("version") or "").strip().lstrip("vV")
        if not version:
            return False
        return self._notify(version, str(payload.get("url") or "").strip())

    def _poll_once(self):
        repo = self._repository()
        if "/" not in repo:
            return False
        url = f"https://raw.githubusercontent.com/{repo}/main/VERSION"
        with urllib.request.urlopen(url, timeout=5) as resp:
            version = resp.read(100).decode("utf-8", "replace").strip()
        return self.handle_release_event({"repository": repo, "version": version, "url": ""})

    def _poll_loop(self):
        initial = max(0, int(self.config.get("initial_delay_seconds") or 20))
        if self._stop.wait(initial):
            return
        interval = max(60, int(self.config.get("check_interval_minutes") or 360) * 60)
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception:
                pass
            if self._stop.wait(interval):
                return
