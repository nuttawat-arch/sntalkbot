# -*- coding: utf-8 -*-
from TeamTalk5 import TeamTalk, User, UserType, UserAccount, UserRight, TextMessage, ttstr, TextMsgType, Subscription, TTMessage, VideoCodec, Channel, ChannelType, AudioCodec, OpusCodec, Codec, OPUS_APPLICATION_VOIP, BanType, StreamType
import TeamTalk5
from bot.command_handler import CommandHandler
from bot.command_aliases import COMMON_ALIASES, PLAYER_ALIASES, MANAGER_ALIASES
from bot.utils import BotUtils as utils, LoggingThreadPoolExecutor
from bot.modules.admin import AdminCog
from bot.modules.general import GeneralCog
from bot.modules.jail import JailCog
from bot.modules.tts import TTSCog
from bot.modules.player import PlayerCog
from bot.modules.translator import TranslatorCog
from bot.modules.account_requests import AccountRequestCog
from bot.user_manager import UserManager
from bot.groq_client import GroqClient
import gettext
import logging
import time
from datetime import datetime
import os, sys, re, configparser, argparse
import ctypes
import random
import threading
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
from bot.player import Player
from bot.bot_identity import effective_status_message
from bot.activity import ActivityLog
from bot.dashboard_state import RuntimeSnapshotBuilder
from bot.http_api import LocalStatusApi
from bot.state_store import StateStore
from bot.update_notifier import UpdateNotifier


class SNTalkBot(TeamTalk):
    def __init__(self, config_handler, account_creator, help_commands, cookiefile=None):
        self.config_handler = config_handler
        self.account_creator = account_creator
        self.help_commands = help_commands

        # Load config from the config handler
        self.features_config = self.config_handler.get_features_config()
        self.player_enabled = self.features_config.get("player_enabled", True)
        self.server_management_enabled = self.features_config.get("server_management_enabled", True)
        self.server_config = self.config_handler.get_server_config()
        self.bot_config = self.config_handler.get_bot_config()
        self.playback_config = self.config_handler.get_playback_config()
        self.telegram_config = self.config_handler.get_telegram_config()
        self.exclusion_config = self.config_handler.get_exclusion_config()
        self.accounts_config = self.config_handler.get_accounts_config()
        self.account_request_config = self.config_handler.get_account_request_config()
        self.global_broadcast_config = self.config_handler.get_global_broadcast_config()
        self.weather_config = self.config_handler.get_weather_config()
        self.tts_config = self.config_handler.get_tts_config()
        self.groq_config = self.config_handler.get_groq_config()
        self.groq_client = GroqClient(
            api_key=self.groq_config.get("api_key"),
            model=self.groq_config.get("model", "llama-3.1-8b-instant"),
            base_url=self.groq_config.get("base_url", "https://api.groq.com/openai/v1"),
        )
        self.ssh_config = self.config_handler.get_ssh_config()
        self.teamtalk_license_config = self.config_handler.get_teamtalk_license_config()
        if self.teamtalk_license_config.get("license_name") and self.teamtalk_license_config.get("license_key"):
            # TeamTalk requires SDK license information to be set before creating a TeamTalk instance.
            TeamTalk5.setLicense(
                ttstr(self.teamtalk_license_config["license_name"]),
                ttstr(self.teamtalk_license_config["license_key"]),
            )
        self.commands = self.help_commands.commands
        self.blocked_commands = set(x.lower().lstrip("/") for x in self.bot_config.get("blocked_commands", []))
        self.cookiefile = cookiefile
        self._reconnect_lock = threading.Lock()
        self._reconnect_scheduled = False
        self._reconnect_attempt = 0
        self._event_bootstrap_lock = threading.Lock()
        self._event_bootstrap_ready = False
        self._initial_login_user_ids = set()
        self._event_bootstrap_timer = None
        self.io_pool = LoggingThreadPoolExecutor(max_workers=10, thread_name_prefix='TTBot_IO')
        self.quick_task_pool = LoggingThreadPoolExecutor(max_workers=5, thread_name_prefix='TTBot_Quick')
        # Bounded, in-memory audit state. This deliberately stores only plain
        # strings/ints, never ctypes TeamTalk objects, so event tracking cannot
        # hold stale SDK structures or interfere with playback.
        self.activity = ActivityLog(max_items=200)
        self.started_at = self.activity.started_at
        self.state_store = StateStore()
        self._user_profile_snapshots = {}
        self._channel_snapshots = {}
        self._user_state_snapshots = {}
        self.player = Player(self.config_handler, cookiefile=self.cookiefile, state_store=self.state_store) if self.player_enabled else None
        self._startup_queue_resume_pending = bool(
            self.player is not None
            and self.playback_config.get("resume_queue_on_start", False)
            and len(self.player.queue) > 0
        )
        self.command_handler = CommandHandler(self)
        self.commands_locked = self.bot_config.get("is_locked", False)
        self.tts_enabled = self.bot_config.get("tts_enabled", True)
        self.profanity_filter_enabled = self.bot_config.get("profanity_filter_enabled", False)
        self.welcome_mode = self.bot_config.get("welcome_mode", 0)
        self.welcome_broadcast = self.bot_config.get("welcome_broadcast", True)
        self.welcome_msg = self.bot_config.get("welcome_msg", "ยินดีต้อนรับคุณ ชื่อ เข้าสู่ห้องครับ")
        print(f"Channel Input: {'ON' if self.bot_config.get('channel_input_enabled', True) else 'OFF'}")
        # One canonical multilingual word-filter source. badword.txt remains in
        # release packages only as a compatibility/reference mirror; every shipped
        # entry is required by validation to exist in blacklist.txt as well.
        self.bad_words = utils.load_blacklist("blacklist.txt")
            
        self.initialize_connection()
        self._register_cogs()
        self.update_notifier = UpdateNotifier(self)
        self.runtime_snapshot_builder = RuntimeSnapshotBuilder(self)
        self.local_status_api = LocalStatusApi(self)
        self.local_status_api.start()

    # Settings which can be applied safely through the loopback API without
    # recreating the Docker container.  Everything else remains persisted in
    # config.ini and is reported as restart-required.
    _LIVE_BOT_KEYS = {
        "nickname", "gender", "status_message", "welcome_broadcast",
        "vpn_detection", "prevent_noname", "noname_note",
        "channel_input_enabled", "intercept_channel_messages", "char_limit",
        "char_limit_mode", "blacklist_mode", "banned_countries",
        "video_deletion_timer", "profanity_filter_enabled", "tts_enabled",
        "welcome_mode", "welcome_msg", "is_locked", "blocked_commands",
        "jail_users", "jail_names", "jail_channel", "jail_timer_seconds",
        "jail_flood_count", "reconnection_attempts", "reconnection_timeout",
    }
    _LIVE_PLAYBACK_KEYS = {
        "seek_step", "default_volume", "max_volume", "send_channel_messages",
        "channel_messages_mode", "volume_fading", "is_stereo_wide",
        "is_stereo_echo", "is_bass_boosted", "speed", "fade_enabled",
        "queue_mode", "persist_queue", "resume_queue_on_start", "play_mode",
        "autoplay_enabled", "announce_tracks", "announce_queue",
        "announcement_tts_mode", "announcement_voice",
        "announcement_microsoft_voice", "announcement_google_lang",
        "announcement_google_tld", "announcement_google_slow",
        "announcement_rate", "announcement_google_speed", "announcement_volume",
    }
    _LIVE_UPDATE_KEYS = {"enabled", "repository", "broadcast_enabled", "telegram_enabled"}
    _LIVE_SECTIONS = {"telegram", "exclusion", "accounts", "account_requests", "global_broadcast", "weather", "tts", "groq"}

    def apply_live_config(self, changed_keys):
        """Reload config.ini and apply safe changed keys to this running bot.

        Returns a JSON-safe result containing keys applied live and keys which
        still require a container restart.  The Web Manager owns persistence;
        this method owns runtime synchronization only.
        """
        requested = []
        for raw in changed_keys or []:
            key = str(raw or "").strip().lower()
            if key and "." in key and key not in requested:
                requested.append(key)
        self.config_handler.reload_config_file()

        live, restart = [], []
        for dotted in requested:
            section, key = dotted.split(".", 1)
            allowed = (
                section == "bot" and key in self._LIVE_BOT_KEYS
                or section == "playback" and key in self._LIVE_PLAYBACK_KEYS
                or section == "updates" and key in self._LIVE_UPDATE_KEYS
                or section in self._LIVE_SECTIONS
            )
            (live if allowed else restart).append(dotted)

        # Refresh canonical parsed dictionaries. Modules reference these objects
        # at runtime, so replacing them synchronizes Web and TeamTalk controls.
        self.bot_config = self.config_handler.get_bot_config()
        self.playback_config = self.config_handler.get_playback_config()
        self.telegram_config = self.config_handler.get_telegram_config()
        self.exclusion_config = self.config_handler.get_exclusion_config()
        self.accounts_config = self.config_handler.get_accounts_config()
        self.account_request_config = self.config_handler.get_account_request_config()
        self.global_broadcast_config = self.config_handler.get_global_broadcast_config()
        self.weather_config = self.config_handler.get_weather_config()
        self.tts_config = self.config_handler.get_tts_config()
        self.groq_config = self.config_handler.get_groq_config()

        if any(k.startswith("groq.") for k in live):
            self.groq_client = GroqClient(
                api_key=self.groq_config.get("api_key"),
                model=self.groq_config.get("model", "llama-3.1-8b-instant"),
                base_url=self.groq_config.get("base_url", "https://api.groq.com/openai/v1"),
            )

        if any(k.startswith("updates.") for k in live) and getattr(self, "update_notifier", None):
            # Webhook flags/repository are safe to change live. Polling thread
            # lifecycle settings remain restart-required by the whitelist above.
            self.update_notifier.config = self.config_handler.get_updates_config()

        bot_live = {k.split(".", 1)[1] for k in live if k.startswith("bot.")}
        self.blocked_commands = set(x.lower().lstrip("/") for x in self.bot_config.get("blocked_commands", []))
        self.commands_locked = self.bot_config.get("is_locked", False)
        self.tts_enabled = self.bot_config.get("tts_enabled", True)
        self.profanity_filter_enabled = self.bot_config.get("profanity_filter_enabled", False)
        self.welcome_mode = self.bot_config.get("welcome_mode", 0)
        self.welcome_broadcast = self.bot_config.get("welcome_broadcast", True)
        self.welcome_msg = self.bot_config.get("welcome_msg", self.welcome_msg)
        if "intercept_channel_messages" in bot_live:
            try:
                self.set_intercept_channel_messages(self.bot_config.get("intercept_channel_messages", True))
            except Exception:
                restart.append("bot.intercept_channel_messages")
                live.remove("bot.intercept_channel_messages")
        if "nickname" in bot_live:
            try:
                self.doChangeNickname(ttstr(self.bot_config.get("nickname", "SN TalkBot")))
            except Exception:
                pass
        if bot_live.intersection({"gender", "status_message"}):
            try:
                self.doChangeStatus(ttstr(self.bot_config.get("gender", 0)), ttstr(self.get_idle_status_message()))
            except Exception:
                pass

        if self.player is not None:
            self.player.playback_config = dict(self.playback_config)
            playback_live = {k.split(".", 1)[1] for k in live if k.startswith("playback.")}
            if "queue_mode" in playback_live:
                self.player.queue_mode = bool(self.playback_config.get("queue_mode", False))
            if "play_mode" in playback_live:
                self.player.play_mode = int(self.playback_config.get("play_mode", 2) or 2)
            if "fade_enabled" in playback_live:
                self.player.fade_enabled = bool(self.playback_config.get("fade_enabled", True))
            filter_changed = False
            for key, attr in (("is_stereo_wide", "is_stereo_wide"), ("is_stereo_echo", "is_stereo_echo"), ("is_bass_boosted", "is_bass_boosted")):
                if key in playback_live:
                    setattr(self.player, attr, bool(self.playback_config.get(key, False)))
                    filter_changed = True
            if "speed" in playback_live:
                speed = float(self.playback_config.get("speed", 1.0))
                self.player.speed = speed
                try:
                    self.player["speed"] = speed
                except Exception:
                    pass
            if filter_changed:
                self.player.update_filters()
            if getattr(self, "player_cog", None) is not None:
                self.player_cog.autoplay_enabled = bool(
                    self.playback_config.get("autoplay_enabled", self.player.play_mode == 2)
                )

        return {"ok": True, "applied": live, "restart_required": restart}

    def get_idle_status_message(self):
        """Return the configured custom status or a role-specific automatic default."""
        return effective_status_message(
            self.bot_config.get("status_message", ""),
            self.player_enabled,
            self.server_management_enabled,
        )

    def _resolve_input_device(self, configured):
        """Resolve TeamTalk input by numeric ID, name substring, or auto."""
        if isinstance(configured, int):
            return configured
        value = str(configured or "auto").strip()
        try:
            return int(value)
        except ValueError:
            pass
        devices = self.getSoundDevices()
        inputs = [d for d in devices if getattr(d, "nMaxInputChannels", 0) > 0]
        if not inputs:
            raise RuntimeError("No TeamTalk input devices are available")
        if value.lower() == "auto":
            pulse = next((d for d in inputs if "pulse" in ttstr(d.szDeviceName).lower()), None)
            return (pulse or inputs[0]).nDeviceID
        needle = value.lower()
        match = next((d for d in inputs if needle in ttstr(d.szDeviceName).lower()), None)
        if not match:
            raise RuntimeError(f"Input device not found: {value}")
        return match.nDeviceID

    def initialize_connection(self):
        """
        Initializes the TeamTalk C-instance, audio devices, and connects to the server.
        This method is safe to call multiple times (after a shutdown).
        """
        super().__init__()
        
        with self._event_bootstrap_lock:
            self._event_bootstrap_ready = False
            self._initial_login_user_ids = set()
            if self._event_bootstrap_timer is not None:
                try:
                    self._event_bootstrap_timer.cancel()
                except Exception:
                    pass
                self._event_bootstrap_timer = None
        self.last_command_sender_id = None
        self.last_command_sender_username = None

        # Set language
        self.language = self.bot_config.get("language")
        gettext.bindtextdomain("messages", "locales")
        gettext.textdomain("messages")
        try:
            translation = gettext.translation("messages", "locales", [self.language])
            translation.install()
            self._ = translation.gettext
        except FileNotFoundError:
            print(f"Language '{self.language}' not found, defaulting to English.")
            translation = gettext.translation("messages", "locales", ["en"])
            translation.install()
            self._ = gettext.gettext

        try:
            print(self._("Initializing audio devices..."))
            input_device = self._resolve_input_device(self.playback_config.get('input_device', 'auto'))
            if not self.initSoundInputDevice(input_device):
                raise RuntimeError(f"TeamTalk rejected input device ID {input_device}")
            print(self._("Audio devices Initialized."))
        except Exception as e:
            print(self._("Error while initializing audio devices: {e}").format(e=e))

        try:
            print(self._("Connecting to {address}:{port}...").format(
                address=self.server_config["address"],
                port=self.server_config["tcp_port"]
            ))
            self.connect(
                ttstr(self.server_config["address"]),
                self.server_config["tcp_port"],
                self.server_config["udp_port"],
                bEncrypted=self.server_config.get("encrypted", False),
            )
        except Exception as e:
            logging.error(f"Connection failed during initialization: {e}")
            print(self._("Error: Connection failed. Check server details or network. See sntalkbot.log for details."))

    def shutdown(self):
        """Cleanly shuts down all resources used by the bot instance."""
        try:
            if getattr(self, "local_status_api", None) is not None:
                self.local_status_api.stop()
            if getattr(self, "player_cog", None) is not None and hasattr(self.player_cog, "shutdown"):
                self.player_cog.shutdown()
            if getattr(self, "admin_cog", None) is not None and hasattr(self.admin_cog, "shutdown"):
                self.admin_cog.shutdown()
            if getattr(self, "update_notifier", None) is not None:
                self.update_notifier.shutdown()
            if self.player is not None:
                self.player.close_player()            
            self.disconnect()            
            self.closeTeamTalk()
            self.io_pool.shutdown(wait=False)
            self.quick_task_pool.shutdown(wait=False)
            if getattr(self, "state_store", None) is not None:
                self.state_store.close()
            print("Shutdown complete.")
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
            print(f"An error occurred during shutdown: {e}")

    def get_media_file_duration_ms(self, filepath):
        try:
            media_info = TeamTalk5.MediaFileInfo()
            ok = TeamTalk5._GetMediaFileInfo(self._tt, ttstr(filepath), ctypes.byref(media_info))
            if not ok:
                return 0
            return int(getattr(media_info, "uDurationMSec", 0) or 0)
        except Exception:
            return 0

    def _register_cogs(self):
        """Initializes and registers command cogs according to the feature switches."""
        self.admin_cog = None
        self.general_cog = GeneralCog(self)
        self.jail_cog = None
        self.tts_cog = None
        self.player_cog = None
        self.translator_cog = None
        self.account_request_cog = None
        self.user_manager = None

        cogs_to_register = [self.general_cog]

        # The music player uses TTSCog internally for track/queue announcements.
        # In Player-only mode we create TTSCog but deliberately do NOT register
        # its public TTS commands, so the instance remains a music bot.
        if self.server_management_enabled or self.player_enabled:
            self.tts_cog = TTSCog(self)

        if self.server_management_enabled:
            self.admin_cog = AdminCog(self)
            self.jail_cog = JailCog(self)
            self.translator_cog = TranslatorCog(self)
            self.account_request_cog = AccountRequestCog(self)
            self.user_manager = UserManager(self)
            cogs_to_register.extend([
                self.admin_cog,
                self.jail_cog,
                self.tts_cog,
                self.translator_cog,
                self.account_request_cog,
                self.user_manager,
            ])

        if self.player_enabled:
            self.player_cog = PlayerCog(self)
            cogs_to_register.append(self.player_cog)

        for cog in cogs_to_register:
            if cog is not None:
                cog.register(self.command_handler)

        # Register aliases by feature profile.  Keep Player and Server Manager
        # shortcuts physically separate so legacy compatibility cannot leak a
        # management command into Player-only mode (or a media command into
        # Manager-only mode).  Full Bot intentionally receives the union.
        active_alias_maps = [COMMON_ALIASES]
        if self.player_enabled:
            active_alias_maps.append(PLAYER_ALIASES)
        if self.server_management_enabled:
            active_alias_maps.append(MANAGER_ALIASES)
        for alias_map in active_alias_maps:
            for alias, target in alias_map.items():
                if target in self.command_handler.commands:
                    self.command_handler.register_alias(alias, target)

        # Migrate any blocked-command entries that were saved using an alias.
        normalized_blocked = {
            self.command_handler.resolve_name(name)
            for name in self.blocked_commands
            if self.command_handler.has_name(name)
        }
        if normalized_blocked != self.blocked_commands:
            self.blocked_commands = normalized_blocked
            self.bot_config["blocked_commands"] = sorted(normalized_blocked)
            self.config_handler.update_bot_settings({"blocked_commands": sorted(normalized_blocked)})

        print(self._("All command modules have been registered."))

    def record_activity(self, category, action, message, **metadata):
        """Record a bounded runtime event without touching the TeamTalk event loop."""
        try:
            return self.activity.record(category, action, message, **metadata)
        except Exception as exc:
            logging.debug("activity log write failed: %s", exc)
            return None

    def _event_tracking_live(self):
        with self._event_bootstrap_lock:
            return bool(self._event_bootstrap_ready)

    @staticmethod
    def _profile_snapshot(user):
        if not user:
            return None
        return {
            "nickname": utils.ensure_text(ttstr(getattr(user, "szNickname", ""))),
            "username": utils.ensure_text(ttstr(getattr(user, "szUsername", ""))),
            "status": utils.ensure_text(ttstr(getattr(user, "szStatusMsg", ""))),
            "status_mode": int(getattr(user, "nStatusMode", 0) or 0),
            "channel_id": int(getattr(user, "nChannelID", 0) or 0),
        }

    @staticmethod
    def _channel_snapshot(channel):
        if not channel:
            return None
        return {
            "id": int(getattr(channel, "nChannelID", 0) or 0),
            "name": utils.ensure_text(ttstr(getattr(channel, "szName", ""))),
            "topic": utils.ensure_text(ttstr(getattr(channel, "szTopic", ""))),
            "parent_id": int(getattr(channel, "nParentID", 0) or 0),
        }

    def _moderate_channel_metadata(self, channel):
        """Apply the same canonical multilingual filter to new and edited channels."""
        if not self.server_management_enabled or not self.profanity_filter_enabled or not channel:
            return False
        blacklist = self.bad_words or utils.load_blacklist("blacklist.txt")
        if not blacklist:
            return False
        channel_name = utils.ensure_text(ttstr(getattr(channel, "szName", "")))
        channel_topic = utils.ensure_text(ttstr(getattr(channel, "szTopic", "")))
        if not utils.contains_profanity(f"{channel_name} {channel_topic}", blacklist):
            return False
        channel_id = int(getattr(channel, "nChannelID", 0) or 0)
        if channel_id:
            self.doRemoveChannel(channel_id)
            self.record_activity("moderation", "channel_removed", f"Removed channel with blocked name/topic: {channel_name}", channel_id=channel_id)
        return True

    @staticmethod
    def _state_flag(name):
        enum = getattr(TeamTalk5, "UserState", None)
        value = getattr(enum, name, 0) if enum is not None else 0
        try:
            return int(getattr(value, "value", value) or 0)
        except Exception:
            return 0

    def runtime_state_counts(self):
        """Return current TeamTalk stream-state counts using SDK user-state flags."""
        result = {"voice": 0, "media": 0, "video": 0, "desktop": 0}
        flags = {
            "voice": self._state_flag("USERSTATE_VOICE"),
            "media_audio": self._state_flag("USERSTATE_MEDIAFILE_AUDIO"),
            "media_video": self._state_flag("USERSTATE_MEDIAFILE_VIDEO"),
            "video": self._state_flag("USERSTATE_VIDEOCAPTURE"),
            "desktop": self._state_flag("USERSTATE_DESKTOP"),
        }
        try:
            users = self.getServerUsers()
        except Exception:
            users = []
        for user in users:
            if int(getattr(user, "nUserID", 0) or 0) == int(self.getMyUserID() or 0):
                continue
            state = int(getattr(user, "uUserState", 0) or 0)
            if flags["voice"] and state & flags["voice"]:
                result["voice"] += 1
            if ((flags["media_audio"] and state & flags["media_audio"]) or
                    (flags["media_video"] and state & flags["media_video"])):
                result["media"] += 1
            if flags["video"] and state & flags["video"]:
                result["video"] += 1
            if flags["desktop"] and state & flags["desktop"]:
                result["desktop"] += 1
        return result

    def onConnectSuccess(self):
        print(self._("Connected successfully!"))
        self.record_activity("system", "connect", "Connected to TeamTalk server")
        self._reconnect_attempt = 0
        self._event_bootstrap_lock = threading.Lock()
        self._event_bootstrap_ready = False
        self._initial_login_user_ids = set()
        self._event_bootstrap_timer = None
        self.doLogin(ttstr(self.bot_config["nickname"]), ttstr(self.server_config["username"]), ttstr(self.server_config["password"]), ttstr(self.bot_config["client_name"]))

    def onConnectFailed(self):
        self.record_activity("system", "connect_failed", "TeamTalk connection failed")
        print(self._("Could not connect to server {server_address} port={port}").format(server_address=self.server_config["address"], port=self.server_config["tcp_port"]))
        print(self._("Trying to reconnect."))
        self.reconnect()

    def onConnectionLost(self):
        self.record_activity("system", "connection_lost", "TeamTalk connection lost")
        print(self._("Connection lost. Trying to reconnect..."))
        self.reconnect()

    def reconnect(self):
        """Schedule a reconnect without blocking the TeamTalk event callback thread."""
        max_attempts = int(self.bot_config.get("reconnection_attempts", -1))
        if max_attempts >= 0 and self._reconnect_attempt >= max_attempts:
            print(self._("Reconnect limit reached; waiting for a manual restart."))
            return
        with self._reconnect_lock:
            if self._reconnect_scheduled:
                return
            self._reconnect_scheduled = True
        threading.Thread(target=self._reconnect_worker, daemon=True, name="TTBot_Reconnect").start()

    def _reconnect_worker(self):
        delay = max(1, int(self.bot_config.get("reconnection_timeout", 10)))
        self._reconnect_attempt += 1
        print(self._("Connection lost. Attempting reconnect #{attempt} in {seconds} seconds...").format(attempt=self._reconnect_attempt, seconds=delay))
        time.sleep(delay)
        try:
            try:
                self.enableVoiceTransmission(False)
            except Exception:
                pass
            try:
                self.disconnect()
            except Exception:
                pass
            try:
                self.closeTeamTalk()
            except Exception:
                pass
            self.initialize_connection()
        finally:
            with self._reconnect_lock:
                self._reconnect_scheduled = False
    
    def _finish_event_bootstrap(self):
        with self._event_bootstrap_lock:
            self._event_bootstrap_ready = True
            self._event_bootstrap_timer = None
        if getattr(self, "user_manager", None) is not None:
            try:
                self.user_manager.reconcile_private_channels()
            except Exception:
                logging.exception("Private-channel reconciliation failed")
        print(self._("Initial TeamTalk user synchronization complete; live login welcomes are enabled."))

    def _begin_event_bootstrap(self):
        """Suppress startup/reconnect replay events without disabling real checks.

        TeamTalk can replay UserLoggedIn/UserJoinedChannel events for users that
        were already online before the bot connected. Those events are state
        synchronization, not new arrivals, and must not trigger welcome broadcasts.
        """
        try:
            existing_ids = {
                int(user.nUserID)
                for user in self.getServerUsers()
                if int(user.nUserID) != int(self.getMyUserID())
            }
        except Exception:
            existing_ids = set()
        with self._event_bootstrap_lock:
            self._event_bootstrap_ready = False
            self._initial_login_user_ids = existing_ids
            if self._event_bootstrap_timer is not None:
                try:
                    self._event_bootstrap_timer.cancel()
                except Exception:
                    pass
            # The short grace window drains TeamTalk's initial event replay. The
            # baseline ID set also suppresses any delayed login replay after it.
            self._event_bootstrap_timer = threading.Timer(3.0, self._finish_event_bootstrap)
            self._event_bootstrap_timer.daemon = True
            self._event_bootstrap_timer.start()

    def _is_fresh_login_event(self, user):
        """Return True only for a login that happened after startup sync finished.

        User IDs seen during the initial/reconnect synchronization remain marked
        for the lifetime of that TeamTalk session. This prevents delayed duplicate
        login/join events from producing welcome messages later. The ID is removed
        when TeamTalk reports a logout.
        """
        user_id = int(getattr(user, "nUserID", 0) or 0)
        if not user_id or user_id == int(self.getMyUserID() or 0):
            return False
        with self._event_bootstrap_lock:
            if not self._event_bootstrap_ready:
                self._initial_login_user_ids.add(user_id)
                return False
            return user_id not in self._initial_login_user_ids

    def _is_live_join_event(self, user):
        """Suppress channel-join replay for users already present at bot startup."""
        user_id = int(getattr(user, "nUserID", 0) or 0)
        if not user_id or user_id == int(self.getMyUserID() or 0):
            return False
        with self._event_bootstrap_lock:
            if not self._event_bootstrap_ready:
                self._initial_login_user_ids.add(user_id)
                return False
            return user_id not in self._initial_login_user_ids

    def onCmdMyselfLoggedIn(self, userid, useraccount):
        print(self._("Logged in successfully"))
        self.record_activity("system", "login", "Bot logged in to TeamTalk")
        self._begin_event_bootstrap()
        channel_kind, channel_ref = utils.parse_channel_reference(self.bot_config.get('default_channel', '/'))
        if channel_kind == "id":
            # Legacy TTMediaBot behavior: a numeric channel value is already a
            # TeamTalk Channel ID and must not be sent through path resolution.
            channel_id = int(channel_ref)
        else:
            channel_id = self.getChannelIDFromPath(ttstr(channel_ref))

        if channel_id == 0 or channel_id is None:
            print(self._("Error: Could not get channel ID for default channel."))
        else:
            self.doJoinChannelByID(channel_id, ttstr(self.bot_config['channel_password']))
        self.subscribe_user_messages()
        self.subscribe_channel_messages()
        self.doChangeStatus(
            ttstr(self.bot_config["gender"]),
            ttstr(self.get_idle_status_message()),
        )

    def onCmdMyselfKickedFromChannel(self, channelid, user):
        self.record_activity("system", "kicked", f"Bot was kicked from channel {int(channelid or 0)}", channel_id=int(channelid or 0))
        # Never sleep inside TeamTalk's event callback. Reuse the non-blocking
        # reconnect worker so the event loop remains responsive.
        print(self._("I've been kicked from the channel. Scheduling reconnect..."))
        self.reconnect()

    def _subscribe_user(self, user):
        if not user or int(getattr(user, "nUserID", 0) or 0) == int(self.getMyUserID() or 0):
            return
        self.doSubscribe(user.nUserID, Subscription.SUBSCRIBE_USER_MSG)
        if self.server_management_enabled and self.bot_config['intercept_channel_messages'] is True:
            self.doSubscribe(user.nUserID, self._intercept_channel_subscription())
            print(self._("intercepting channel messages for user {user}").format(user=ttstr(user.szNickname)))

    @staticmethod
    def _intercept_channel_subscription():
        return getattr(Subscription, "SUBSCRIBE_INTERCEPT_CHANNEL_MSG", 131072)

    def set_intercept_channel_messages(self, enabled):
        """Apply all-channel interception immediately and persist the setting."""
        enabled = bool(enabled)
        self.bot_config["intercept_channel_messages"] = enabled
        self.config_handler.update_bot_settings({"intercept_channel_messages": enabled})
        subscription = self._intercept_channel_subscription()
        for user in self.getServerUsers():
            user_id = int(getattr(user, "nUserID", 0) or 0)
            if not user_id or user_id == int(self.getMyUserID() or 0):
                continue
            if enabled:
                self.doSubscribe(user_id, subscription)
            else:
                self.doUnsubscribe(user_id, subscription)

    def subscribe_user_messages(self):
        for user in self.getServerUsers():
            self._subscribe_user(user)
        print(self._("subscribed to user messages"))

    def subscribe_channel_messages(self):
        channel_id = self.getMyChannelID()

        self.doSubscribe(channel_id, Subscription.SUBSCRIBE_CHANNEL_MSG)
        print(self._("Subscribed to channel messages"))

    def onCmdUserLoggedIn(self, user: User):
        fresh_login = self._is_fresh_login_event(user)
        # Subscribe only the user represented by this event. Re-subscribing the
        # entire server for every login was unnecessary work on busy servers.
        self._subscribe_user(user)
        snapshot = self._profile_snapshot(user)
        if snapshot is not None:
            self._user_profile_snapshots[int(getattr(user, "nUserID", 0) or 0)] = snapshot
        if fresh_login:
            self.record_activity(
                "user", "login",
                f"{snapshot.get('nickname') or snapshot.get('username') or 'Unknown'} logged in",
                user_id=int(getattr(user, "nUserID", 0) or 0),
            )
        if self.accounts_config['detect_server_admins'] is True and user.uUserType == UserType.USERTYPE_ADMIN:
            username_lower = ttstr(user.szUsername).lower()
            if username_lower not in [u.lower() for u in self.accounts_config['authorized_users']]:
                self.accounts_config['authorized_users'].append(ttstr(user.szUsername))

        if self.admin_cog is not None:
            self.admin_cog.handle_admin_login(user)

        if ttstr(user.szUsername) in self.exclusion_config["usernames"] or \
           ttstr(user.szNickname) in self.exclusion_config["nicknames"] or \
           ttstr(user.szIPAddress) in self.exclusion_config["ips"]:
            print(self._("User {nickname} is excluded, skipping checks.").format(nickname=ttstr(user.szNickname)))
            return

        if self.admin_cog is not None:
            self.admin_cog.handle_user_login_checks(user)
        if self.user_manager is not None:
            self.user_manager.on_user_logged_in(user, fresh_login=fresh_login)

    def onCmdUserUpdate(self, user: User):
        """React to real TeamTalk user-property updates without polling."""
        user_id = int(getattr(user, "nUserID", 0) or 0)
        if not user_id:
            return
        current = self._profile_snapshot(user) or {}
        previous = self._user_profile_snapshots.get(user_id)
        self._user_profile_snapshots[user_id] = current

        if user_id == int(self.getMyUserID() or 0):
            return

        # Re-check profile text when users change nickname/status after login.
        # This closes the common loophole of logging in clean and renaming later.
        if self.server_management_enabled and self.admin_cog is not None:
            if self.admin_cog.check_user_profile_for_blacklist(user):
                return

        if not self._event_tracking_live() or not previous:
            return
        old_name = previous.get("nickname", "")
        new_name = current.get("nickname", "")
        old_status = previous.get("status", "")
        new_status = current.get("status", "")
        if old_name != new_name:
            self.record_activity("user", "rename", f"{old_name or 'Unknown'} renamed to {new_name or 'Unknown'}", user_id=user_id)
        if old_status != new_status:
            display = new_name or current.get("username") or "Unknown"
            self.record_activity("user", "status", f"{display} changed status", user_id=user_id)

    def onCmdUserJoinedChannel(self, user: User):
        user_id = int(getattr(user, "nUserID", 0) or 0)
        if (
            user_id == int(self.getMyUserID() or 0)
            and self._startup_queue_resume_pending
            and self.player_cog is not None
            and self.player is not None
            and len(self.player.queue) > 0
        ):
            self._startup_queue_resume_pending = False
            index = self.player.queue_index if 0 <= self.player.queue_index < len(self.player.queue) else 0
            # URL extraction/network work must not block TeamTalk's callback thread.
            self.quick_task_pool.submit(self.player_cog._play_from_queue, index)
        is_live = self._is_live_join_event(user)
        snapshot = self._profile_snapshot(user)
        if snapshot is not None:
            self._user_profile_snapshots[user_id] = snapshot
        if self.jail_cog is not None:
            self.jail_cog.handle_user_join_channel(user)

        if is_live:
            nickname = (snapshot or {}).get("nickname") or (snapshot or {}).get("username") or "Unknown"
            self.record_activity("user", "join", f"{nickname} joined channel {int(getattr(user, 'nChannelID', 0) or 0)}", user_id=user_id, channel_id=int(getattr(user, "nChannelID", 0) or 0))

        # Static welcome is a Manager/Full concern and only fires for a true live join.
        if self.server_management_enabled and self.welcome_mode > 0 and is_live:
            nm = ttstr(user.szNickname)
            msg = self.welcome_msg.replace("ชื่อ", nm)
            self.send_message(msg)

    def onCmdUserLeftChannel(self, channelid: int, user: User):
        user_id = int(getattr(user, "nUserID", 0) or 0)
        if self._event_tracking_live() and user_id != int(self.getMyUserID() or 0):
            nickname = utils.ensure_text(ttstr(getattr(user, "szNickname", ""))) or utils.ensure_text(ttstr(getattr(user, "szUsername", ""))) or "Unknown"
            self.record_activity("user", "leave", f"{nickname} left channel {int(channelid or 0)}", user_id=user_id, channel_id=int(channelid or 0))
        if self.user_manager is not None:
            self.user_manager.on_user_parted(user)
        if self.translator_cog is not None:
            self.translator_cog.on_user_parted(user)
        if self.tts_cog is not None:
            self.tts_cog.on_user_parted(user)

    def onCmdUserLoggedOut(self, user: User):
        user_id = int(getattr(user, "nUserID", 0) or 0)
        if self._event_tracking_live() and user_id != int(self.getMyUserID() or 0):
            snapshot = self._user_profile_snapshots.get(user_id) or self._profile_snapshot(user) or {}
            nickname = snapshot.get("nickname") or snapshot.get("username") or "Unknown"
            self.record_activity("user", "logout", f"{nickname} logged out", user_id=user_id)
        self._user_profile_snapshots.pop(user_id, None)
        self._user_state_snapshots.pop(user_id, None)
        with self._event_bootstrap_lock:
            self._initial_login_user_ids.discard(user_id)
        if self.user_manager is not None:
            self.user_manager.on_user_parted(user)
        if self.translator_cog is not None:
            self.translator_cog.on_user_parted(user)
        if self.tts_cog is not None:
            self.tts_cog.on_user_parted(user)
        if self.account_request_cog is not None:
            self.account_request_cog.on_user_parted(user)

    def split_long_message(self, message, chunk_size=500):
        """Split text without dropping characters around a word boundary."""
        remaining = str(message or "")
        chunks = []
        while remaining:
            if len(remaining) <= chunk_size:
                chunks.append(remaining)
                break
            candidate = remaining[:chunk_size]
            split_at = candidate.rfind(" ")
            if split_at <= 0:
                split_at = chunk_size
                chunks.append(remaining[:split_at])
                remaining = remaining[split_at:]
            else:
                chunks.append(remaining[:split_at])
                remaining = remaining[split_at + 1:]
        return chunks

    def onCmdUserTextMessage(self, textmessage: TextMessage):
        message_text = utils.ensure_text(ttstr(textmessage.szMessage))
        from_uid = textmessage.nFromUserID
        from_username = utils.ensure_text(ttstr(textmessage.szFromUsername))
        sender_user = self.getUser(from_uid)
        from_nickname = utils.ensure_text(ttstr(sender_user.szNickname)) if sender_user else "Unknown"

        # TeamTalk CUSTOM text is transport metadata (the common example is the
        # client typing indicator "typing\n1"), not user chat and never a bot
        # command.  Do not let it flood console logs or enter TTS/player flows.
        msg_type = self.command_handler._numeric(getattr(textmessage, "nMsgType", None))
        custom_type = self.command_handler._numeric(getattr(TextMsgType, "MSGTYPE_CUSTOM", None))
        if custom_type is not None and msg_type == custom_type:
            super().onCmdUserTextMessage(textmessage)
            return

        # Word moderation is intentionally independent from Channel Input. The
        # `filter` switch is the single master ON/OFF control for the canonical
        # multilingual blacklist (Thai, English, and other configured languages).
        # Therefore `ci off` silences normal channel features without blinding an
        # enabled filter, while `filter off` disables all word filtering at once.
        if self.server_management_enabled and self.profanity_filter_enabled and from_uid != self.getMyUserID():
            # Canonical blacklist.txt contains English, Arabic, Thai, and any other
            # configured languages. Preserve its historical kick/ban action first.
            if self.admin_cog is not None and self.admin_cog.check_message_for_blacklist(textmessage):
                return


        # Channel Input controls normal reactions only. Moderation above has
        # already inspected the message. Private input is never blocked here.
        if not self.command_handler.channel_input_allowed(
            textmessage, self.bot_config.get("channel_input_enabled", True)
        ):
            # Do not make a disabled Channel Input look like a dead command
            # parser.  Keep the setting authoritative, but make the reason clear
            # in logs without changing or executing the message.
            if self.command_handler.is_command_candidate(message_text, textmessage):
                print(self._("Message received: {message} from {username}").format(
                    message=f"{message_text} [ignored: Channel Input OFF]",
                    username=from_username,
                ))
            return

        # TTMediaBot-style prefix-free commands work in both private and channel
        # text. `ci off` is the explicit safety switch for normal channel reactions.
        if self.command_handler.handle_message(textmessage):
            return

        print(self._("Message received: {message} from {username}").format(message=message_text, username=from_username))

        if self.account_request_cog is not None and self.account_request_cog.handle_message(textmessage):
            return

        if self.tts_cog is not None and self.tts_cog.handle_prefixed_message(textmessage):
            return
        if self.player_cog is not None and self.player_cog.handle_prefixed_message(textmessage):
            return

        # Auto-play links
        if re.match(r'^https?://[^\s]+$', message_text.strip()) and self.player_cog is not None:
            self.player_cog.handle_play_url_command(textmessage, message_text.strip())
            return

        if self.player_cog is not None and self.player_cog.handle_playlist_selection_message(textmessage):
            return
        if self.player_cog is not None and self.player_cog.handle_channel_selection_message(textmessage):
            return

        if self.translator_cog is not None:
            self.translator_cog.handle_whisper_translation(textmessage)
            if self.translator_cog.handle_channel_translation(textmessage):
                return
            if self.translator_cog.handle_private_translation(textmessage):
                return

        # Legacy-friendly final fallback: after every real workflow has had a
        # chance to consume the text, tell the sender that it is not a command.
        # Never answer TeamTalk CUSTOM events (for example typing notifications),
        # and never answer our own text, otherwise the bot could create noise or
        # a bot-to-bot response loop.
        if self.command_handler.should_reply_unknown(textmessage, self.getMyUserID()):
            self.privateMessage(from_uid, self._("Unknown or invalid command. Send h for help."))
            return

        super().onCmdUserTextMessage(textmessage)

    def onUserAudioBlock(self, nUserID: int, nStreamType: StreamType):
        pass

    def onCmdChannelNew(self, channel: Channel):
        snapshot = self._channel_snapshot(channel) or {}
        channel_id = snapshot.get("id", 0)
        if channel_id:
            self._channel_snapshots[channel_id] = snapshot
        removed = self._moderate_channel_metadata(channel)
        if not removed and self._event_tracking_live() and self.server_management_enabled:
            self.record_activity("channel", "new", f"Channel created: {snapshot.get('name') or channel_id}", channel_id=channel_id)

    def onCmdChannelUpdate(self, channel: Channel):
        snapshot = self._channel_snapshot(channel) or {}
        channel_id = snapshot.get("id", 0)
        previous = self._channel_snapshots.get(channel_id)
        if channel_id:
            self._channel_snapshots[channel_id] = snapshot
        removed = self._moderate_channel_metadata(channel)
        if removed or not self._event_tracking_live() or not self.server_management_enabled:
            return
        if previous:
            if previous.get("name") != snapshot.get("name"):
                self.record_activity("channel", "rename", f"Channel renamed: {previous.get('name') or channel_id} -> {snapshot.get('name') or channel_id}", channel_id=channel_id)
            elif previous.get("topic") != snapshot.get("topic"):
                self.record_activity("channel", "topic", f"Channel topic changed: {snapshot.get('name') or channel_id}", channel_id=channel_id)
        else:
            self.record_activity("channel", "update", f"Channel updated: {snapshot.get('name') or channel_id}", channel_id=channel_id)

    def onCmdChannelRemove(self, channel: Channel):
        snapshot = self._channel_snapshot(channel) or {}
        channel_id = snapshot.get("id", 0)
        previous = self._channel_snapshots.pop(channel_id, None) or snapshot
        if self._event_tracking_live() and self.server_management_enabled:
            self.record_activity("channel", "remove", f"Channel removed: {previous.get('name') or channel_id}", channel_id=channel_id)

    def onCmdServerUpdate(self, serverproperties):
        if not self._event_tracking_live() or not self.server_management_enabled:
            return
        name = utils.ensure_text(ttstr(getattr(serverproperties, "szServerName", ""))) or "server"
        self.record_activity("server", "update", f"Server settings updated: {name}")

    def onCmdFileNew(self, remote_file):
        if not self._event_tracking_live() or not self.server_management_enabled:
            return
        name = utils.ensure_text(ttstr(getattr(remote_file, "szFileName", ""))) or "file"
        channel_id = int(getattr(remote_file, "nChannelID", 0) or 0)
        self.record_activity("file", "new", f"File added: {name}", channel_id=channel_id)

    def onCmdFileRemove(self, remote_file):
        if not self._event_tracking_live() or not self.server_management_enabled:
            return
        name = utils.ensure_text(ttstr(getattr(remote_file, "szFileName", ""))) or "file"
        channel_id = int(getattr(remote_file, "nChannelID", 0) or 0)
        self.record_activity("file", "remove", f"File removed: {name}", channel_id=channel_id)

    def onUserStateChange(self, user: User):
        """Track media/video/desktop state changes; voice transitions are not logged to avoid noise."""
        user_id = int(getattr(user, "nUserID", 0) or 0)
        if not user_id or user_id == int(self.getMyUserID() or 0):
            return
        current = int(getattr(user, "uUserState", 0) or 0)
        previous = self._user_state_snapshots.get(user_id, current)
        self._user_state_snapshots[user_id] = current
        if not self._event_tracking_live() or not self.server_management_enabled or previous == current:
            return
        nickname = utils.ensure_text(ttstr(getattr(user, "szNickname", ""))) or "Unknown"
        watched = [
            ("USERSTATE_MEDIAFILE_AUDIO", "media audio"),
            ("USERSTATE_MEDIAFILE_VIDEO", "media video"),
            ("USERSTATE_VIDEOCAPTURE", "camera"),
            ("USERSTATE_DESKTOP", "desktop"),
        ]
        changes = []
        for flag_name, label in watched:
            flag = self._state_flag(flag_name)
            if not flag or not ((previous ^ current) & flag):
                continue
            changes.append(f"{label} {'started' if current & flag else 'stopped'}")
        if changes:
            self.record_activity("stream", "state", f"{nickname}: {', '.join(changes)}", user_id=user_id, channel_id=int(getattr(user, "nChannelID", 0) or 0))

    def onUserAccount(self, useraccount: UserAccount):
        username = ttstr(useraccount.szUsername)
        user_type = useraccount.uUserType

        if username == self.last_command_sender_username:
            user = self.getUserByUsername(ttstr(username))  # Get the User object
            if user:
                nickname = ttstr(user.szNickname)
                ip_address = ttstr(user.szIPAddress)
                status_message = ttstr(user.szStatusMsg)
                password = ttstr(useraccount.szPassword)

                info_message = self._("User Info:\n Nickname: {nickname}\n Username: {username}\n Password: {password}\n  IP Address: {ip_address}\n Status Message: {status_message}").format(nickname=nickname, username=username, password=password, status_message=status_message, ip_address=ip_address)
                self.privateMessage(self.last_command_sender_id, info_message)
                self.last_command_sender_id = None
                self.last_command_sender_username = None

    def getUserByName(self, nickname):
        nickname = ttstr(nickname)
        users = self.getServerUsers()
        for user in users:
            if user.szNickname.strip() == nickname:
                return user
        return None

    def is_authorized_user(self, username):
        if not username:
            return False
        authorized_users = [u.strip().lower() for u in self.accounts_config["authorized_users"]]
        return utils.ensure_text(ttstr(username)).strip().lower() in authorized_users

    def _split_private_message(self, message_text, max_bytes=480):
        if message_text is None:
            return []
        text = str(message_text)
        if len(text.encode("utf-8")) <= max_bytes:
            return [text]

        def split_long_token(token):
            parts = []
            current_chars = []
            current_len = 0
            for ch in token:
                ch_len = len(ch.encode("utf-8"))
                if current_chars and current_len + ch_len > max_bytes:
                    parts.append("".join(current_chars))
                    current_chars = [ch]
                    current_len = ch_len
                else:
                    current_chars.append(ch)
                    current_len += ch_len
            if current_chars:
                parts.append("".join(current_chars))
            return parts

        chunks = []
        current = ""
        current_len = 0
        tokens = re.findall(r"\S+|\s+", text)
        for token in tokens:
            token_len = len(token.encode("utf-8"))
            if not current:
                if token_len <= max_bytes:
                    current = token
                    current_len = token_len
                else:
                    chunks.extend(split_long_token(token))
                continue
            if current_len + token_len <= max_bytes:
                current += token
                current_len += token_len
                continue
            chunks.append(current)
            if token_len <= max_bytes:
                current = token
                current_len = token_len
            else:
                chunks.extend(split_long_token(token))
                current = ""
                current_len = 0
        if current:
            chunks.append(current)
        return chunks

    def privateMessage(self, user_id, message_text):
        for chunk in self._split_private_message(message_text):
            message = TextMessage()
            message.nMsgType = 1
            message.nToUserID = user_id
            message.nFromUserID = self.getMyUserID()
            message.szMessage = ttstr(chunk)
            self.doTextMessage(message)

    def send_message(self, message_text, channel_id=None):
        if channel_id is None:
            channel_id=self.getMyChannelID()
        message = TextMessage()
        message.nMsgType = TextMsgType.MSGTYPE_CHANNEL
        message.nChannelID = channel_id
        message.szMessage = ttstr(message_text)
        self.doTextMessage(message)

    def send_broadcast_message(self, message_text):
        """Send a global text broadcast using TeamTalk-safe UTF-8 chunks."""
        for chunk in self._split_private_message(message_text):
            message = TextMessage()
            message.nMsgType = TextMsgType.MSGTYPE_BROADCAST
            message.szMessage = ttstr(chunk)
            self.doTextMessage(message)

    def kick_user(self, user_id):
        user = self.getUser(user_id)
        if not user:
            return False
        user_channel_id = int(getattr(user, "nChannelID", 0) or 0)
        if user_channel_id:
            self.doKickUser(user_id, user_channel_id)
        self.doKickUser(user_id, 0)
        return True

    def queue_global_broadcast_tts(self, message_text):
        """Queue optional TTS for the same Central Global Broadcast message.

        There is intentionally no second message source or scheduler. Text and
        speech share the Web Manager SQLite message feed, while the per-instance
        ``[global_broadcast] tts_enabled`` switch controls whether this bot also
        speaks each delivered central message.
        """
        cfg = dict(getattr(self, "global_broadcast_config", {}) or {})
        if not bool(cfg.get("tts_enabled", False)):
            return False
        if not bool(getattr(self, "tts_enabled", False)) or self.tts_cog is None:
            return False
        if not self._has_other_users_in_channel():
            return False
        text = str(message_text or "").strip()
        if not text:
            return False
        self.quick_task_pool.submit(self.tts_cog.speak_global_broadcast, text)
        return True

    def _has_other_users_in_channel(self):
        channel_id = self.getMyChannelID()
        if not channel_id:
            return False
        my_id = self.getMyUserID()
        for user in self.getServerUsers():
            if user.nUserID != my_id and user.nChannelID == channel_id:
                return True
        return False
