# -*- coding: utf-8 -*-
from TeamTalk5 import TeamTalk, User, UserType, UserAccount, UserRight, TextMessage, ttstr, TextMsgType, Subscription, TTMessage, VideoCodec, Channel, ChannelType, AudioCodec, OpusCodec, Codec, OPUS_APPLICATION_VOIP, BanType, StreamType
import TeamTalk5
from bot.command_handler import CommandHandler
from bot.command_aliases import COMMAND_ALIASES
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
        self.player = Player(self.config_handler, cookiefile=self.cookiefile) if self.player_enabled else None
        self.command_handler = CommandHandler(self, prefix='/')
        self.commands_locked = self.bot_config.get("is_locked", False)
        self.tts_enabled = self.bot_config.get("tts_enabled", True)
        self.profanity_filter_enabled = self.bot_config.get("profanity_filter_enabled", False)
        self.welcome_mode = self.bot_config.get("welcome_mode", 0)
        self.welcome_broadcast = self.bot_config.get("welcome_broadcast", True)
        self.welcome_msg = self.bot_config.get("welcome_msg", "ยินดีต้อนรับคุณ ชื่อ เข้าสู่ห้องครับ")
        self.user_warnings = {}
        self.bad_words = []
        try:
            os.makedirs("files", exist_ok=True)
            badword_candidates = [os.path.join("files", "badword.txt"), "badword.txt"]
            badword_file = next((path for path in badword_candidates if os.path.exists(path)), None)
            if badword_file:
                with open(badword_file, "r", encoding="utf-8") as f:
                    self.bad_words = [line.strip().lower() for line in f if line.strip()]
        except Exception as e:
            print(f"Error loading bad words: {e}")
            
        self.random_tts_thread = None
        self.random_tts_messages = []
        self.initialize_connection()
        self._register_cogs()

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

       # utils.check_for_updates(self._)
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
            if self.player is not None:
                self.player.close_player()            
            self.disconnect()            
            self.closeTeamTalk()
            self.io_pool.shutdown(wait=False)
            self.quick_task_pool.shutdown(wait=False)
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

        # Register intentional short aliases only when their canonical command is
        # available in this feature mode. Aliases resolve to one canonical handler
        # rather than registering duplicate command handlers.
        for alias, target in COMMAND_ALIASES.items():
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

    def onConnectSuccess(self):
        print(self._("Connected successfully!"))
        self._reconnect_attempt = 0
        self._event_bootstrap_lock = threading.Lock()
        self._event_bootstrap_ready = False
        self._initial_login_user_ids = set()
        self._event_bootstrap_timer = None
        self.doLogin(ttstr(self.bot_config["nickname"]), ttstr(self.server_config["username"]), ttstr(self.server_config["password"]), ttstr(self.bot_config["client_name"]))

    def onConnectFailed(self):
        print(self._("Could not connect to server {server_address} port={port}").format(server_address=self.server_config["address"], port=self.server_config["tcp_port"]))
        print(self._("Trying to reconnect."))
        self.reconnect()

    def onConnectionLost(self):
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
        self._begin_event_bootstrap()
        channel_id = self.getChannelIDFromPath(ttstr(self.bot_config['default_channel']))

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
        self._maybe_start_random_tts_broadcast()

    def onCmdMyselfKickedFromChannel(self, channelid, user):
        # Never sleep inside TeamTalk's event callback. Reuse the non-blocking
        # reconnect worker so the event loop remains responsive.
        print(self._("I've been kicked from the channel. Scheduling reconnect..."))
        self.reconnect()

    def _subscribe_user(self, user):
        if not user or int(getattr(user, "nUserID", 0) or 0) == int(self.getMyUserID() or 0):
            return
        self.doSubscribe(user.nUserID, Subscription.SUBSCRIBE_USER_MSG)
        if self.server_management_enabled and self.bot_config['intercept_channel_messages'] is True:
            self.doSubscribe(user.nUserID, 131072)
            print(self._("intercepting channel messages for user {user}").format(user=ttstr(user.szNickname)))

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

    def onCmdUserJoinedChannel(self, user: User):
        if self.jail_cog is not None:
            self.jail_cog.handle_user_join_channel(user)
        self._maybe_start_random_tts_broadcast()
        
        # New Welcome logic
        if self.server_management_enabled and self.welcome_mode > 0 and self._is_live_join_event(user):
            nm = ttstr(user.szNickname)
            msg = self.welcome_msg.replace("ชื่อ", nm)
            self.send_message(msg)

    def onCmdUserLeftChannel(self, channelid: int, user: User):
        if self.user_manager is not None:
            self.user_manager.on_user_parted(user)
        if self.translator_cog is not None:
            self.translator_cog.on_user_parted(user)
        if self.tts_cog is not None:
            self.tts_cog.on_user_parted(user)

    def onCmdUserLoggedOut(self, user: User):
        with self._event_bootstrap_lock:
            self._initial_login_user_ids.discard(int(getattr(user, "nUserID", 0) or 0))
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
        message_text = ttstr(textmessage.szMessage)
        from_uid = textmessage.nFromUserID
        from_username = ttstr(textmessage.szFromUsername)
        sender_user = self.getUser(from_uid)
        from_nickname = ttstr(sender_user.szNickname) if sender_user else "Unknown"

        # Profanity Filter
        if self.server_management_enabled and self.profanity_filter_enabled and from_uid != self.getMyUserID():
            text_lower = message_text.lower()
            is_bad = False
            for bw in self.bad_words:
                if bw in text_lower:
                    is_bad = True
                    break
            if is_bad:
                self.user_warnings[from_uid] = self.user_warnings.get(from_uid, 0) + 1
                count = self.user_warnings[from_uid]
                if count >= 3:
                    self.kick_user(from_uid)
                    self.send_broadcast_message(f"เตะคุณ {from_nickname} ออกจากเซิร์ฟเวอร์เนื่องจากพิมพ์คำหยาบเกินกำหนด")
                    self.user_warnings[from_uid] = 0
                else:
                    self.privateMessage(from_uid, f"กรุณาอย่าพิมพ์คำหยาบนะครับ เตือนครั้งที่ {count}/3")
                return

        print(self._("Message received: {message} from {username}").format(message=message_text, username=from_username))
        
        if self.admin_cog is not None and self.admin_cog.check_message_for_blacklist(textmessage):
            return

        if self.account_request_cog is not None and self.account_request_cog.handle_message(textmessage):
            return

        if self.tts_cog is not None and self.tts_cog.handle_prefixed_message(textmessage):
            return
        if self.player_cog is not None and self.player_cog.handle_prefixed_message(textmessage):
            return

        # Commands may be written with or without the leading slash.  Slashless
        # commands are accepted only in private messages by CommandHandler, so
        # ordinary channel chat cannot be mistaken for short commands.
        if self.command_handler.handle_message(textmessage):
            return

        # Auto-play links
        if re.match(r'^https?://[^\s]+$', message_text.strip()):
            if self.player_cog is not None:
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
        super().onCmdUserTextMessage(textmessage)

    def onUserAudioBlock(self, nUserID: int, nStreamType: StreamType):
        pass

    def onCmdChannelNew(self, channel: Channel):
        if not self.server_management_enabled:
            return
        blacklist = utils.load_blacklist("blacklist.txt")
        if not blacklist:
            return
        channel_name = ttstr(channel.szName).lower()
        channel_topic = ttstr(channel.szTopic).lower()
        if any(word for word in blacklist if word and (word in channel_name or word in channel_topic)):
            self.doRemoveChannel(channel.nChannelID)
            return

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
        return ttstr(username).lower() in authorized_users

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
        message = TextMessage()
        message.nMsgType = TextMsgType.MSGTYPE_BROADCAST
        message.szMessage = ttstr(message_text)
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

    def send_broadcast_messages_at_intervals(self, messages):
        random.seed()
        while True:
            if self.bot_config["random_message_interval"] > 0:
                message = random.choice(messages)
                nickname = self.get_random_nickname()

                message = message.format(name=ttstr(nickname))
                self.send_broadcast_message(message)
                time.sleep(self.bot_config["random_message_interval"] * 60)

    def get_random_nickname(self):
        online_users = [u for u in self.getServerUsers() if u.nUserID != self.getMyUserID()]
        if online_users:
            random_user = random.choice(online_users)
            return random_user.szNickname
        else:
            return "Someone"

    def _maybe_start_random_tts_broadcast(self):
        if not self.server_management_enabled:
            return
        if self.tts_cog is None:
            return
        if self.random_tts_thread and self.random_tts_thread.is_alive():
            return
        if self.bot_config.get("random_message_interval", 0) <= 0:
            return
        if not self.tts_enabled:
            return
        if not self.tts_config.get("random_broadcast_enabled", False):
            return
        if (self.tts_config.get("mode") or "microsoft").strip().lower() not in ("microsoft", "google"):
            return
        if not self.random_tts_messages:
            self.random_tts_messages = utils.load_messages("messages.txt")
        if not self.random_tts_messages:
            return
        self.random_tts_thread = threading.Thread(
            target=self._random_tts_broadcast_loop,
            daemon=True,
            name="TTBot_RandomTTSBroadcast",
        )
        self.random_tts_thread.start()

    def _random_tts_broadcast_loop(self):
        random.seed()
        interval_minutes = self.bot_config.get("random_message_interval", 0)
        if interval_minutes <= 0:
            return
        while True:
            if not self.tts_enabled:
                time.sleep(5)
                continue
            if not self._has_other_users_in_channel():
                time.sleep(5)
                continue
            message = random.choice(self.random_tts_messages)
            nickname = self.get_random_nickname()
            message = message.format(name=ttstr(nickname))
            if self.tts_cog is not None:
                self.tts_cog.speak_random_broadcast(message)
            time.sleep(interval_minutes * 60)

    def _has_other_users_in_channel(self):
        channel_id = self.getMyChannelID()
        if not channel_id:
            return False
        my_id = self.getMyUserID()
        for user in self.getServerUsers():
            if user.nUserID != my_id and user.nChannelID == channel_id:
                return True
        return False
