from TeamTalk5 import BanType, BannedUser, UserAccount, UserType, TextMsgType, TextMessage, ttstr
from bot.utils import BotUtils as utils
import TeamTalk5 as teamtalk
import time
from threading import Thread, Event
import paramiko
import re
import os

class AdminCog:
    """
    A module for handling all administrator-level commands.
    """
    def __init__(self, bot):
        self.bot = bot
        self._ = bot._        
        # Timed moderation is persistent. A single scheduler handles all
        # expiry work; no per-user sleep threads or RAM-only ban/kick maps.
        self._moderation_stop = Event()
        self._moderation_wakeup = Event()
        self._moderation_thread = None
        if getattr(bot, "state_store", None) is not None:
            self._moderation_thread = Thread(
                target=self._moderation_scheduler_loop,
                name="sntalkbot-moderation-scheduler",
                daemon=True,
            )
            self._moderation_thread.start()

    def shutdown(self):
        self._moderation_stop.set()
        self._moderation_wakeup.set()
        thread = getattr(self, "_moderation_thread", None)
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _unban_rule(self, rule):
        """Remove a persisted server-side ban. Return True only when queued."""
        subject_type = str(rule.get("subject_type") or "")
        subject_value = str(rule.get("subject_value") or "")
        try:
            if subject_type == "ip":
                result = self.bot.doUnBanUser(ttstr(subject_value), 0)
            elif subject_type == "username":
                banned_user = BannedUser()
                banned_user.szUsername = ttstr(subject_value)
                banned_user.uBanTypes = BanType.BANTYPE_USERNAME
                result = self.bot.doUnbanUserEx(banned_user)
            else:
                return True
            return result != -1
        except Exception as exc:
            print(f"Timed moderation unban failed for {subject_type}:{subject_value}: {exc}")
            return False

    def _expire_moderation_rules(self):
        expired = self.bot.state_store.expired_moderation()
        delete_ids = []
        retry_needed = False
        for rule in expired:
            if rule["action"] != "ban":
                delete_ids.append(rule["id"])
                continue
            if self._unban_rule(rule):
                delete_ids.append(rule["id"])
                self.bot.send_message(
                    self._("Timed ban expired for {target}.").format(
                        target=rule["subject_value"]
                    )
                )
            else:
                # Keep the row so a reconnect/restart can retry rather than
                # silently turning a temporary server ban into a permanent one.
                retry_needed = True
        self.bot.state_store.delete_moderation_ids(delete_ids)
        return retry_needed

    def _moderation_scheduler_loop(self):
        while not self._moderation_stop.is_set():
            retry_needed = False
            try:
                retry_needed = self._expire_moderation_rules()
                next_expiry = self.bot.state_store.next_moderation_expiry()
            except Exception as exc:
                print(f"Timed moderation scheduler error: {exc}")
                next_expiry = None
                retry_needed = True

            if retry_needed:
                wait_for = 5.0
            elif next_expiry is None:
                wait_for = 60.0
            else:
                wait_for = max(0.1, min(60.0, next_expiry - time.time()))
            self._moderation_wakeup.wait(wait_for)
            self._moderation_wakeup.clear()

    def _save_moderation_rule(self, action, subject_type, subject_value, duration_seconds, ban_type=0):
        if duration_seconds <= 0:
            raise ValueError("duration must be greater than zero")
        self.bot.state_store.upsert_moderation(
            action, subject_type, subject_value, time.time() + duration_seconds, int(ban_type or 0)
        )
        self._moderation_wakeup.set()

    def register(self, command_handler):
        """Registers all the admin commands."""
        command_handler.register_command('reboot', self.handle_reboot_command, admin_only=True)
        command_handler.register_command('exec', self.handle_exec_command, admin_only=True)
        command_handler.register_command('db', self.handle_duration_ban_ip, admin_only=True)
        command_handler.register_command('udb', self.handle_duration_ban_user, admin_only=True)
        command_handler.register_command('dk', self.handle_duration_kick_nickname, admin_only=True)
        command_handler.register_command('udk', self.handle_duration_kick_by_username, admin_only=True)
        command_handler.register_command('bm', self.handle_admin_broadcast, admin_only=True)
        command_handler.register_command('clear', self.handle_clear_command, admin_only=True)
        command_handler.register_command('new', self.handle_new_account_command, admin_only=True)
        command_handler.register_command('join', self.handle_join_command, admin_only=True)
        command_handler.register_command('moveall', self.handle_moveall_command, admin_only=True)
        command_handler.register_command('k', self.handle_kick_channel_command, admin_only=True)
        command_handler.register_command('ks', self.handle_kick_server_command, admin_only=True)
        command_handler.register_command('globalbroadcast', self.handle_central_global_broadcast_command, admin_only=True)
        command_handler.register_command('filter', self.handle_filter_toggle_command, admin_only=True)
        command_handler.register_command('welcome', self.handle_welcome_toggle_command, admin_only=True)
        command_handler.register_command('welcomebroadcast', self.handle_welcome_broadcast_toggle_command, admin_only=True)
        command_handler.register_command('vpn', self.handle_vpn_toggle_command, admin_only=True)
        command_handler.register_command('noname', self.handle_noname_toggle_command, admin_only=True)

    def handle_user_login_checks(self, user):
        """Handles all administrative checks when a user logs in."""
        nickname = ttstr(user.szNickname)
        username = ttstr(user.szUsername)
        ip_address = ttstr(user.szIPAddress)
        user_id = user.nUserID

        # 1. Check for auto-jailing
        if username in self.bot.bot_config["jail_users"] or nickname in self.bot.bot_config["jail_names"]:
            jail_channel_id = self.bot.getChannelIDFromPath(ttstr(self.bot.bot_config["jail_channel"]))
            if jail_channel_id:
                self.bot.doMoveUser(user_id, jail_channel_id)

        # 2. Persistent timed moderation. Rules are keyed by the stable
        # nickname/username/IP selectors used by the original commands.
        rules = self.bot.state_store.matching_moderation(
            nickname=nickname, username=username, ip_address=ip_address
        )
        if rules:
            self.bot.kick_user(user_id)
            return

        # 3. Check the canonical multilingual blacklist only while the master
        # word filter is enabled. The same helper is also reused by the real
        # TeamTalk USER_UPDATE event so renaming after login cannot bypass it.
        if self.check_user_profile_for_blacklist(user):
            return

        # 6. Check for "NoName"
        if self.bot.bot_config['prevent_noname']:
            if not nickname or re.match(r"^NoName\s*(?:-\s*#\d+)?$", nickname):
                self.bot.privateMessage(user_id, self.bot.bot_config['noname_note'])
                self.bot.kick_user(user_id)
                return

        # 7. Check for character limit
        char_limit = self.bot.bot_config["char_limit"]
        if char_limit > 0 and len(nickname) > char_limit:
            if self.bot.bot_config["char_limit_mode"] == 1:
                self.bot.privateMessage(user_id, self._("You have been kicked due to username exceeding {chars} characters.").format(chars=char_limit))
                self.bot.kick_user(user_id)
            elif self.bot.bot_config["char_limit_mode"] == 2:
                self.ban_user(user_id, BanType.BANTYPE_IPADDR)
                self.bot.kick_user(user_id)
            return

    def check_user_profile_for_blacklist(self, user):
        """Moderate nickname/status text using the one canonical multilingual list."""
        if not self.bot.profanity_filter_enabled or not user:
            return False
        user_id = int(getattr(user, "nUserID", 0) or 0)
        if not user_id or user_id == int(self.bot.getMyUserID() or 0):
            return False
        nickname = utils.ensure_text(ttstr(getattr(user, "szNickname", "")))
        status_message = utils.ensure_text(ttstr(getattr(user, "szStatusMsg", "")))
        blacklist = getattr(self.bot, "bad_words", None) or utils.load_blacklist("blacklist.txt")
        if not blacklist or not utils.contains_profanity(f"{nickname} {status_message}", blacklist):
            return False
        if self.bot.bot_config.get("blacklist_mode", 1) == 2:
            self.ban_user(user_id, BanType.BANTYPE_IPADDR)
        self.bot.kick_user(user_id)
        if hasattr(self.bot, "record_activity"):
            self.bot.record_activity(
                "moderation", "profile",
                f"Blocked user profile text: {nickname or user_id}",
                user_id=user_id,
            )
        return True

    def check_message_for_blacklist(self, textmessage: TextMessage):
        """Check the canonical multilingual blacklist and apply its legacy action.

        `filter` is the master switch. Missing blacklist.wav is deliberately
        non-fatal because release packages have historically not shipped it.
        """
        if not self.bot.profanity_filter_enabled:
            return False
        message_text = utils.ensure_text(ttstr(textmessage.szMessage))
        blacklist = utils.load_blacklist("blacklist.txt")
        if blacklist and utils.contains_profanity(message_text, blacklist):
            audio_path = os.path.join("files", "blacklist.wav")
            if os.path.exists(audio_path):
                try:
                    streamer = teamtalk.VideoCodec()
                    streamer.nCodec = 1
                    self.bot.startStreamingMediaFileToChannel(ttstr(audio_path), streamer)
                except Exception as exc:
                    print(f"Warning: unable to play blacklist alert audio: {exc}")

            if self.bot.bot_config['blacklist_mode'] == 1:
                self.bot.kick_user(textmessage.nFromUserID)
            elif self.bot.bot_config['blacklist_mode'] == 2:
                self.ban_user(textmessage.nFromUserID)
                self.bot.kick_user(textmessage.nFromUserID)
            return True
        return False

    def _get_online_admins(self):
        authorized = [u.strip().lower() for u in self.bot.accounts_config["authorized_users"]]
        admins = []
        for user in self.bot.getServerUsers():
            username = utils.ensure_text(ttstr(user.szUsername)).lower()
            if user.uUserType == UserType.USERTYPE_ADMIN or username in authorized:
                admins.append(user.nUserID)
        return admins

    def handle_admin_login(self, user):
        # Kept as an event-compatible no-op. The old pending_admin_alerts list
        # had no producer and therefore was dead RAM-only state.
        return

    def handle_reboot_command(self, textmessage, *args):
        self.bot.send_broadcast_message(self._("Attention, The server is rebooting..."))
        self._execute_ssh_command("reboot", textmessage.nFromUserID)

    def handle_exec_command(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: exec <command>"))
            return
        command = " ".join(args)
        self._execute_ssh_command(command, textmessage.nFromUserID)

    def _execute_ssh_command(self, command, user_id):
        user = self.bot.getUser(user_id)
        if not user:
            return
        user_ip = ttstr(user.szIPAddress)
        if user_ip not in self.bot.ssh_config.get('allowed_ips', []):
            self.bot.privateMessage(user_id, self._("Not authorized for this IP address."))
            return
        
        def ssh_task():
            try:
                with paramiko.SSHClient() as ssh_client:
                    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh_client.connect(
                        hostname=self.bot.ssh_config["hostname"],
                        port=self.bot.ssh_config["port"],
                        username=self.bot.ssh_config["username"],
                        password=self.bot.ssh_config["password"],
                        timeout=10
                    )
                    _, stdout, stderr = ssh_client.exec_command(command, timeout=30)
                    output = stdout.read().decode('utf-8', errors='ignore')
                    error = stderr.read().decode('utf-8', errors='ignore')

                    if error: self.bot.privateMessage(user_id, f"Error: {error}")
                    if output:
                        for chunk in self.bot.split_long_message(output):
                            self.bot.privateMessage(user_id, chunk)
            except Exception as e:
                self.bot.privateMessage(user_id, self._("SSH connection error: {e}").format(e=e))
        
        self.bot.quick_task_pool.submit(ssh_task)


    def handle_duration_ban_ip(self, textmessage, *args):
        self._handle_duration_ban(textmessage, BanType.BANTYPE_IPADDR, " ".join(args))

    def handle_duration_ban_user(self, textmessage, *args):
        self._handle_duration_ban(textmessage, BanType.BANTYPE_USERNAME, " ".join(args))

    def _handle_duration_ban(self, textmessage, ban_type, args_str):
        try:
            parts = args_str.rsplit(" ", 1)
            if len(parts) != 2:
                raise ValueError("Invalid format")
            nickname, duration_str = parts[0], parts[1]
            duration_seconds = self.parse_duration_string(duration_str)
            if duration_seconds <= 0:
                raise ValueError("Duration must be positive")
            user = self.bot.getUserByName(nickname)
            if not user:
                self.bot.privateMessage(
                    textmessage.nFromUserID,
                    self._("User '{nickname}' not found.").format(nickname=nickname),
                )
                return
            if not self.ban_user(user.nUserID, ban_type):
                self.bot.privateMessage(textmessage.nFromUserID, self._("Unable to create the ban."))
                return
            if ban_type == BanType.BANTYPE_IPADDR:
                subject_type, subject_value = "ip", ttstr(user.szIPAddress)
            else:
                subject_type, subject_value = "username", ttstr(user.szUsername)
            self._save_moderation_rule(
                "ban", subject_type, subject_value, duration_seconds, ban_type
            )
            self.bot.send_message(
                self._("{nickname} has been banned for {duration}.").format(
                    nickname=ttstr(user.szNickname), duration=duration_str
                )
            )
            self.bot.kick_user(user.nUserID)
        except (ValueError, IndexError):
            self.bot.privateMessage(
                textmessage.nFromUserID,
                self._("Invalid format. Usage: db <nickname> <duration> (e.g., 1h:30m:10s)"),
            )

    def handle_duration_kick_nickname(self, textmessage, *args):
        try:
            parts = " ".join(args).rsplit(" ", 1)
            if len(parts) != 2:
                raise ValueError("Invalid format")
            nickname, duration_str = parts[0], parts[1]
            duration_seconds = self.parse_duration_string(duration_str)
            self._save_moderation_rule("kick", "nickname", nickname, duration_seconds)
            user = self.bot.getUserByName(nickname)
            if user:
                self.bot.kick_user(user.nUserID)
                self.bot.send_message(
                    self._("{nickname} has been kicked for {duration}.").format(
                        nickname=ttstr(user.szNickname), duration=duration_str
                    )
                )
            else:
                self.bot.send_message(
                    self._("User '{nickname}' not found. They will be kicked when they log in for {duration}.").format(
                        nickname=nickname, duration=duration_str
                    )
                )
        except (ValueError, IndexError):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid format. Usage: dk <nickname> <duration>"))

    def handle_duration_kick_by_username(self, textmessage, *args):
        try:
            parts = " ".join(args).rsplit(" ", 1)
            if len(parts) != 2:
                raise ValueError("Invalid format")
            username, duration_str = parts[0], parts[1]
            duration_seconds = self.parse_duration_string(duration_str)
            self._save_moderation_rule("kick", "username", username, duration_seconds)
            user = self.bot.getUserByUsername(ttstr(username))
            if user and user.nUserID != 0:
                self.bot.kick_user(user.nUserID)
                self.bot.send_message(
                    self._("User with username '{username}' has been kicked for {duration}.").format(
                        username=username, duration=duration_str
                    )
                )
            else:
                self.bot.send_message(
                    self._("User with username '{username}' not found. They will be kicked when they log in for {duration}.").format(
                        username=username, duration=duration_str
                    )
                )
        except (ValueError, IndexError):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid format. Usage: udk <username> <duration>"))

    def parse_duration_string(self, duration_str):
        duration_seconds = 0
        for part in duration_str.replace(" ", "").split(':'):
            if not part: continue
            unit = part[-1].lower()
            try:
                value = int(part[:-1])
                if unit == 's': duration_seconds += value
                elif unit == 'm': duration_seconds += value * 60
                elif unit == 'h': duration_seconds += value * 3600
                elif unit == 'd': duration_seconds += value * 86400
                elif unit == 'w': duration_seconds += value * 604800
                else: raise ValueError(f"Invalid duration unit: {unit}")
            except (ValueError, IndexError):
                raise ValueError(f"Invalid duration part: {part}")
        return duration_seconds

    def handle_new_account_command(self, textmessage, *args):
        try:
            if len(args) < 2:
                raise ValueError("Not enough arguments")
            
            username = args[0]
            password = args[1]
            rights = [int(r) for r in args[2:]]
            
            account = self.bot.account_creator.create_user_account()
            account.szUsername = ttstr(username)
            account.szPassword = ttstr(password)
            account.uUserType = UserType.USERTYPE_DEFAULT
            account.uUserRights = self.bot.account_creator.calculate_user_rights(rights)

            self.bot.doNewUserAccount(account)
            self.bot.privateMessage(textmessage.nFromUserID, self._("Account '{username}' created successfully.").format(username=username))
        except ValueError:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command format. Usage: new <username> <password> [rights separated by space]"))

    def handle_clear_command(self, textmessage, *args):
        target = " ".join(args)
        if target:
            self.clear_for_target(target)
        else:
            self.clear_all()

    def clear_for_target(self, target):
        target_key = self.bot.state_store.normalize_key(target)
        rules = [
            rule for rule in self.bot.state_store.list_moderation()
            if rule["subject_value"] == target_key
        ]
        if not rules:
            self.bot.send_message(
                self._("Target '{target}' not found in active bans or kicks.").format(target=target)
            )
            return
        delete_ids = []
        for rule in rules:
            if rule["action"] == "ban" and not self._unban_rule(rule):
                continue
            delete_ids.append(rule["id"])
        self.bot.state_store.delete_moderation_ids(delete_ids)
        self._moderation_wakeup.set()
        if delete_ids:
            self.bot.send_message(self._("Cleared timed moderation for {target}.").format(target=target))
        if len(delete_ids) != len(rules):
            self.bot.send_message(self._("Some server bans could not be cleared yet and will be retried."))

    def clear_all(self):
        rules = self.bot.state_store.list_moderation()
        if not rules:
            self.bot.send_message(self._("There are no active bans or kicks to clear."))
            return
        delete_ids = []
        for rule in rules:
            if rule["action"] == "ban" and not self._unban_rule(rule):
                continue
            delete_ids.append(rule["id"])
        self.bot.state_store.delete_moderation_ids(delete_ids)
        self._moderation_wakeup.set()
        self.bot.send_message(self._("Cleared all timed bans and duration kicks that could be removed."))

    def handle_admin_broadcast(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: bm <message>"))
            return
        message = " ".join(args)
        self.bot.send_broadcast_message(self._("Message from administrators: {message}").format(message=message))

    def ban_user(self, user_id, ban_type=BanType.BANTYPE_USERNAME):
        """Ban a currently connected user without relying on a placeholder stub.

        Prefer TeamTalk's BannedUser API so username/IP bans apply at server login.
        Fall back to doBanUserEx/doBanUser for older Python bindings.
        """
        user = self.bot.getUser(user_id)
        if not user:
            return False
        try:
            if hasattr(self.bot, "doBan"):
                banned = BannedUser()
                banned.uBanTypes = ban_type
                if ban_type & BanType.BANTYPE_IPADDR:
                    banned.szIPAddress = user.szIPAddress
                if ban_type & BanType.BANTYPE_USERNAME:
                    banned.szUsername = user.szUsername
                result = self.bot.doBan(banned)
                return result != -1
            if hasattr(self.bot, "doBanUserEx"):
                result = self.bot.doBanUserEx(user_id, ban_type)
                return result != -1
            if hasattr(self.bot, "doBanUser") and (ban_type & BanType.BANTYPE_IPADDR):
                result = self.bot.doBanUser(user_id, 0)
                return result != -1
        except Exception as exc:
            print(f"Error banning user {user_id}: {exc}")
        return False

    def handle_join_command(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: join <channel_path>"))
            return
        path = " ".join(args)
        chan_id = self.bot.getChannelIDFromPath(ttstr(path))
        if chan_id:
            self.bot.doJoinChannelByID(chan_id, ttstr(""))
            self.bot.privateMessage(textmessage.nFromUserID, self._("Joined channel: {path}").format(path=path))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Channel not found."))

    def handle_moveall_command(self, textmessage, *args):
        my_chan = self.bot.getMyChannelID()
        target_chan = my_chan
        if args:
            path = " ".join(args)
            target_chan = self.bot.getChannelIDFromPath(ttstr(path))
        
        if not target_chan:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Target channel not found."))
            return

        users = self.bot.getServerUsers()
        count = 0
        for u in users:
            if u.nUserID != self.bot.getMyUserID():
                self.bot.doMoveUser(u.nUserID, target_chan)
                count += 1
        self.bot.send_message(self._("Moved {count} users to target channel.").format(count=count))

    def handle_kick_channel_command(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: k <nickname>"))
            return
        nick = " ".join(args)
        user = self.bot.getUserByName(nick)
        if user:
            self.bot.doKickUser(user.nUserID, user.nChannelID)
            self.bot.send_message(self._("Kicked {nick} from channel.").format(nick=nick))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("User not found."))

    def handle_kick_server_command(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: ks <nickname>"))
            return
        nick = " ".join(args)
        user = self.bot.getUserByName(nick)
        if user:
            self.bot.doKickUser(user.nUserID, 0)
            self.bot.send_message(self._("Kicked {nick} from server.").format(nick=nick))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("User not found."))

    def handle_central_global_broadcast_command(self, textmessage, *args):
        """Configure the per-instance gate for Web Manager central broadcasts."""
        cfg = dict(getattr(self.bot, "global_broadcast_config", {}) or {})
        cfg.setdefault("enabled", False)
        cfg.setdefault("interval_minutes", 60)
        cfg.setdefault("tts_enabled", False)
        arg = str(args[0] if args else "status").strip().lower()
        if arg in ("on", "off"):
            cfg["enabled"] = arg == "on"
        elif arg == "interval":
            if len(args) < 2:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: globalbroadcast interval <1-10080>"))
                return
            try:
                minutes = int(str(args[1]).strip())
            except ValueError:
                minutes = 0
            if minutes < 1 or minutes > 10080:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Global Broadcast interval must be 1-10080 minutes."))
                return
            cfg["interval_minutes"] = minutes
        elif arg == "tts":
            if len(args) < 2 or str(args[1]).strip().lower() not in ("on", "off"):
                self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: globalbroadcast tts on|off"))
                return
            cfg["tts_enabled"] = str(args[1]).strip().lower() == "on"
        elif arg != "status":
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: globalbroadcast on|off|status|interval <minutes>|tts on|off"))
            return
        self.bot.global_broadcast_config = cfg
        self.bot.config_handler.save_global_broadcast_config(cfg)
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Central Global Broadcast: {state}; interval: {minutes} minute(s); TTS: {tts}.").format(
                state="ON" if cfg["enabled"] else "OFF",
                minutes=cfg["interval_minutes"],
                tts="ON" if cfg["tts_enabled"] else "OFF",
            ),
        )

    def handle_filter_toggle_command(self, textmessage, *args):
        arg = args[0].strip().lower() if args else ""
        if arg == "status":
            self.bot.privateMessage(
                textmessage.nFromUserID,
                self._("Word Filter (all languages): {state}").format(state="ON" if self.bot.profanity_filter_enabled else "OFF"),
            )
            return
        if arg == "on":
            self.bot.profanity_filter_enabled = True
        elif arg == "off":
            self.bot.profanity_filter_enabled = False
        elif arg == "":
            self.bot.profanity_filter_enabled = not self.bot.profanity_filter_enabled
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: filter on|off|status"))
            return
        self.bot.config_handler.update_bot_settings({"profanity_filter_enabled": self.bot.profanity_filter_enabled})
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Word Filter (all languages): {state}").format(state="ON" if self.bot.profanity_filter_enabled else "OFF"),
        )

    def handle_welcome_toggle_command(self, textmessage, *args):
        arg = args[0] if args else ""
        if arg == "on": self.bot.welcome_mode = 1
        elif arg == "off": self.bot.welcome_mode = 0
        else: self.bot.welcome_mode = 1 if self.bot.welcome_mode == 0 else 0
        self.bot.config_handler.update_bot_settings({"welcome_mode": self.bot.welcome_mode})
        self.bot.send_message(self._("Welcome Message: {state}").format(state="ON" if self.bot.welcome_mode > 0 else "OFF"))

    def handle_welcome_broadcast_toggle_command(self, textmessage, *args):
        """Enable/disable randomized public login welcome broadcasts persistently."""
        arg = args[0].strip().lower() if args else ""
        if arg == "on":
            self.bot.welcome_broadcast = True
        elif arg == "off":
            self.bot.welcome_broadcast = False
        elif arg not in ("", "status"):
            self.bot.privateMessage(
                textmessage.nFromUserID,
                self._("Usage: welcomebroadcast on|off|status"),
            )
            return
        elif arg == "":
            self.bot.welcome_broadcast = not self.bot.welcome_broadcast

        self.bot.bot_config["welcome_broadcast"] = self.bot.welcome_broadcast
        self.bot.config_handler.update_bot_settings({"welcome_broadcast": self.bot.welcome_broadcast})
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Welcome Broadcast: {state}").format(
                state=self._("enabled") if self.bot.welcome_broadcast else self._("disabled")
            ),
        )

    def handle_vpn_toggle_command(self, textmessage, *args):
        arg = args[0] if args else ""
        if arg == "on": self.bot.bot_config["vpn_detection"] = True
        elif arg == "off": self.bot.bot_config["vpn_detection"] = False
        else: self.bot.bot_config["vpn_detection"] = not self.bot.bot_config.get("vpn_detection", False)
        self.bot.config_handler.update_bot_settings({"vpn_detection": self.bot.bot_config["vpn_detection"]})
        self.bot.send_message(self._("VPN Detection: {state}").format(state="ON" if self.bot.bot_config["vpn_detection"] else "OFF"))

    def handle_noname_toggle_command(self, textmessage, *args):
        arg = args[0] if args else ""
        if arg == "on": self.bot.bot_config["prevent_noname"] = True
        elif arg == "off": self.bot.bot_config["prevent_noname"] = False
        else: self.bot.bot_config["prevent_noname"] = not self.bot.bot_config.get("prevent_noname", False)
        self.bot.config_handler.update_bot_settings({"prevent_noname": self.bot.bot_config["prevent_noname"]})
        self.bot.send_message(self._("Noname Prevention: {state}").format(state="ON" if self.bot.bot_config["prevent_noname"] else "OFF"))
