# -*- coding: utf-8 -*-
"""Runtime state snapshot shared by the file bridge and local realtime API.

The JSON file remains the compatibility/fallback transport. TTUHelper 1.5+ can
also give each instance a token-protected loopback HTTP port for sub-second web
updates without exposing a public bot endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from bot.utils import BotUtils as utils


class RuntimeStateWriter:
    def __init__(self, bot, interval: float = 2.0):
        self.bot = bot
        try:
            self.interval = max(1.0, min(float(interval or 2.0), 30.0))
        except (TypeError, ValueError):
            self.interval = 2.0
        data_dir = Path(os.getenv("TTUTIL_DATA_DIR", "/app/data"))
        override = os.getenv("SNTALKBOT_RUNTIME_STATE_FILE", "").strip()
        self.path = Path(override) if override else data_dir / "runtime_status.json"
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="SNTalkBotRuntimeState", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._write(final=True)

    @staticmethod
    def _project_version():
        try:
            return (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
        except Exception:
            return "unknown"

    @staticmethod
    def _primitive(value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        return str(value)

    def _queue_snapshot(self, player):
        result = []
        lock = getattr(player, "queue_lock", None)
        if lock is None:
            entries = list(getattr(player, "queue", []) or [])
            queue_index = int(getattr(player, "queue_index", -1) or -1)
        else:
            with lock:
                entries = list(getattr(player, "queue", []) or [])
                queue_index = int(getattr(player, "queue_index", -1) or -1)
        for index, item in enumerate(entries[:250]):
            if not isinstance(item, dict):
                item = {"title": str(item)}
            result.append({
                "position": index + 1,
                "current": index == queue_index,
                "title": str(item.get("title") or item.get("name") or "Unknown"),
                "link": str(item.get("link") or item.get("url") or ""),
                "added_by": str(item.get("added_by") or ""),
                "added_by_user_id": self._primitive(item.get("added_by_user_id")),
                "added_at": self._primitive(item.get("added_at")),
            })
        return result, len(entries), queue_index

    def build_snapshot(self):
        bot = self.bot
        now = time.time()
        role = "full" if bot.player_enabled and bot.server_management_enabled else (
            "player" if bot.player_enabled else "manager"
        )
        try:
            my_user_id = int(bot.getMyUserID() or 0)
        except Exception:
            my_user_id = 0
        try:
            users = list(bot.getServerUsers() or [])
        except Exception:
            users = []
        users_online = sum(1 for user in users if int(getattr(user, "nUserID", 0) or 0) != my_user_id)
        # TeamTalk UserType.USERTYPE_ADMIN is 2.  Exclude this bot's own user ID
        # so the dashboard never counts the bot itself as a human/server admin.
        admins_online = []
        for user in users:
            user_id = int(getattr(user, "nUserID", 0) or 0)
            if not user_id or user_id == my_user_id:
                continue
            if int(getattr(user, "uUserType", 0) or 0) != 2:
                continue
            admins_online.append({
                "user_id": user_id,
                "username": utils.ensure_text(getattr(user, "szUsername", "")),
                "nickname": utils.ensure_text(getattr(user, "szNickname", "")),
            })

        channel_id = 0
        channel_name = ""
        try:
            channel_id = int(bot.getMyChannelID() or 0)
            if channel_id:
                channel = bot.getChannel(channel_id)
                if channel:
                    channel_name = utils.ensure_text(getattr(channel, "szName", ""))
        except Exception:
            pass

        state_counts = {}
        try:
            state_counts = bot.runtime_state_counts()
        except Exception:
            state_counts = {"voice": 0, "media": 0, "video": 0, "desktop": 0}

        snapshot = {
            "schema": 1,
            "version": self._project_version(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_epoch": now,
            "pid": os.getpid(),
            "uptime_seconds": max(0, int(now - float(getattr(bot, "started_at", now)))),
            "role": role,
            "connected": bool(my_user_id),
            "server": {
                "address": str(bot.server_config.get("address") or ""),
                "tcp_port": int(bot.server_config.get("tcp_port") or 0),
                "udp_port": int(bot.server_config.get("udp_port") or 0),
                "encrypted": bool(bot.server_config.get("encrypted", False)),
            },
            "bot": {
                "nickname": str(bot.bot_config.get("nickname") or ""),
                "status_message": str(bot.get_idle_status_message() if hasattr(bot, "get_idle_status_message") else bot.bot_config.get("status_message") or ""),
                "client_name": str(bot.bot_config.get("client_name") or ""),
            },
            "channel": {"id": channel_id, "name": channel_name},
            "users_online": users_online,
            "admins_online_count": len(admins_online),
            "admins_online": admins_online,
            "teamtalk_activity": {
                "speaking": int(state_counts.get("voice", 0) or 0),
                "media": int(state_counts.get("media", 0) or 0),
                "video": int(state_counts.get("video", 0) or 0),
                "desktop": int(state_counts.get("desktop", 0) or 0),
            },
        }

        if bot.player_enabled and getattr(bot, "player", None) is not None:
            player = bot.player
            queue, queue_count, queue_index = self._queue_snapshot(player)
            cookie_state = "none"
            try:
                if getattr(player, "cookiefile", None) and player._cookiefile_has_records(player.cookiefile):
                    cookie_state = "persistent/custom"
                elif getattr(player, "bundled_cookiefile", None) and player._cookiefile_has_records(player.bundled_cookiefile):
                    cookie_state = "bundled default"
            except Exception:
                pass
            snapshot["player"] = {
                "enabled": True,
                "is_playing": bool(getattr(player, "is_playing", False)),
                "title": str(getattr(player, "media_title", "") or ""),
                "link": str(getattr(player, "current_link", "") or ""),
                "volume": int(getattr(player, "current_volume", lambda: getattr(player, "volume", 0))() or 0),
                "speed": float(getattr(player, "speed", 1.0) or 1.0),
                "queue_mode": bool(getattr(player, "queue_mode", False)),
                "queue_count": queue_count,
                "queue_index": queue_index,
                "queue": queue,
                "play_mode": int(getattr(player, "play_mode", 2) or 2),
                "autoplay": bool(bot.playback_config.get("autoplay_enabled", True)),
                "collection_count": len(getattr(player, "collection_results", []) or []),
                "collection_index": int(getattr(player, "current_collection_index", 0) or 0),
                "collection_source": str(getattr(player, "collection_source", "") or ""),
                "radio_history_count": len(getattr(player, "radio_history", []) or []),
                "radio_index": int(getattr(player, "radio_index", -1) or -1),
                "cookies": cookie_state,
            }

        if bot.server_management_enabled:
            snapshot["manager"] = {
                "enabled": True,
                "filter": bool(getattr(bot, "profanity_filter_enabled", False)),
                "channel_input": bool(bot.bot_config.get("channel_input_enabled", True)),
                "intercept": bool(bot.bot_config.get("intercept_channel_messages", True)),
                "commands_locked": bool(getattr(bot, "commands_locked", False)),
                "welcome_mode": int(getattr(bot, "welcome_mode", 0) or 0),
                "welcome_broadcast": bool(getattr(bot, "welcome_broadcast", False)),
            }

        try:
            events = bot.activity.recent(25)
        except Exception:
            events = []
        snapshot["events"] = [{
            "timestamp": self._primitive(item.get("timestamp")),
            "category": str(item.get("category") or "event"),
            "action": str(item.get("action") or "update"),
            "message": str(item.get("message") or ""),
            "metadata": {str(k): self._primitive(v) for k, v in (item.get("metadata") or {}).items()},
        } for item in events]
        return snapshot

    def _write(self, final=False):
        try:
            payload = self.build_snapshot()
            if final:
                payload["connected"] = False
                payload["stopped_at"] = datetime.now(timezone.utc).isoformat()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(prefix="runtime_status.", suffix=".json", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temp_path, 0o640)
                os.replace(temp_path, self.path)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        except Exception:
            # Management visibility must never be able to break the bot runtime.
            return

    def _run(self):
        while not self._stop.wait(self.interval):
            self._write()
