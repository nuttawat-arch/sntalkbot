from TeamTalk5 import BanType, BannedUser, UserAccount, UserType, TextMsgType, TextMessage, ttstr
from bot.utils import BotUtils as utils, RestartSignal, ShutdownSignal
import TeamTalk5 as teamtalk
import time
from threading import Thread
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
        self.duration_kicks = {}
        self.pending_kicks = {}
        self.banned_users = {}
        self.duration_bans = {}
        self.user_strikes = {}
        self.pending_admin_alerts = []

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
        command_handler.register_command('cn', self.handle_change_name_command, admin_only=True)
        command_handler.register_command('save', self.save_bot_config, admin_only=True)
        command_handler.register_command('cs', self.handle_change_status, admin_only=True)
        command_handler.register_command('cg', self.handle_change_gender, admin_only=True)
        command_handler.register_command('new', self.handle_new_account_command, admin_only=True)
        command_handler.register_command('lock', self.handle_lock_command, admin_only=True)
        command_handler.register_command('join', self.handle_join_command, admin_only=True)
        command_handler.register_command('moveall', self.handle_moveall_command, admin_only=True)
        command_handler.register_command('k', self.handle_kick_channel_command, admin_only=True)
        command_handler.register_command('ks', self.handle_kick_server_command, admin_only=True)
        command_handler.register_command('bot', self.handle_global_broadcast_command, admin_only=True)
        command_handler.register_command('sbot', self.handle_server_broadcast_command, admin_only=True)
        command_handler.register_command('superbot', self.handle_host_broadcast_command, admin_only=True)
        command_handler.register_command('filter', self.handle_filter_toggle_command, admin_only=True)
        command_handler.register_command('welcome', self.handle_welcome_toggle_command, admin_only=True)
        command_handler.register_command('welcomebroadcast', self.handle_welcome_broadcast_toggle_command, admin_only=True)
        command_handler.register_command('restart', self.handle_restart_command, admin_only=True)
        command_handler.register_command('clearlog', self.handle_clear_log_command, admin_only=True)
        command_handler.register_command('vpn', self.handle_vpn_toggle_command, admin_only=True)
        command_handler.register_command('noname', self.handle_noname_toggle_command, admin_only=True)
        command_handler.register_command('shutdown', self.handle_shutdown_command, admin_only=True)
        command_handler.register_command('blockcmd', self.handle_block_command, admin_only=True)
        command_handler.register_command('language', self.handle_language_command, admin_only=True)
        command_handler.register_command('voicetx', self.handle_voice_tx_command, admin_only=True)

    def handle_block_command(self, textmessage, *args):
        if not args:
            value = ", ".join(x for x in sorted(self.bot.blocked_commands)) or self._("The list is empty")
            self.bot.privateMessage(textmessage.nFromUserID, value)
            return
        token = args[0].strip().lower()
        action = token[:1]
        requested_name = token[1:].lstrip("/") if action in "+-" else token.lstrip("/")
        name = self.bot.command_handler.resolve_name(requested_name)
        if name not in self.bot.command_handler.commands:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Unknown command."))
            return
        if action == "+":
            self.bot.blocked_commands.add(name)
            message = self._("Command blocked: {command}").format(command=name)
        elif action == "-":
            self.bot.blocked_commands.discard(name)
            message = self._("Command unblocked: {command}").format(command=name)
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: blockcmd +command or blockcmd -command"))
            return
        self.bot.bot_config["blocked_commands"] = sorted(self.bot.blocked_commands)
        self.bot.config_handler.update_bot_settings({"blocked_commands": sorted(self.bot.blocked_commands)})
        self.bot.privateMessage(textmessage.nFromUserID, message)

    def handle_language_command(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Current language: {language}").format(language=self.bot.bot_config.get("language", "en")))
            return
        language = args[0].strip()
        locale_dir = os.path.join("locales", language, "LC_MESSAGES")
        if not os.path.isdir(locale_dir):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Language folder not found: {language}").format(language=language))
            return
        self.bot.bot_config["language"] = language
        self.bot.config_handler.update_bot_settings({"language": language})
        self.bot.privateMessage(textmessage.nFromUserID, self._("Language saved as {language}. Use restart to reload all modules.").format(language=language))

    def handle_voice_tx_command(self, textmessage, *args):
        if not args or args[0].lower() not in ("on", "off"):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: voicetx on|off"))
            return
        enabled = args[0].lower() == "on"
        ok = self.bot.enableVoiceTransmission(enabled)
        self.bot.privateMessage(textmessage.nFromUserID, self._("Voice transmission: {state}").format(state="ON" if enabled else "OFF"))

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

        # 2. Check for pending duration kicks (by nickname and username)
        if nickname.lower() in self.pending_kicks:
            _, duration, end_time = self.pending_kicks[nickname.lower()]
            if time.time() < end_time:
                self.bot.kick_user(user_id)
                user_data = (nickname, ip_address, username)
                self.duration_kicks[user_data] = (duration, end_time)
            del self.pending_kicks[nickname.lower()]
            return # User was kicked, stop processing

        if username.lower() in self.pending_kicks:
            _, duration, end_time = self.pending_kicks[username.lower()]
            if time.time() < end_time:
                self.bot.kick_user(user_id)
                user_data = (nickname, ip_address, username)
                self.duration_kicks[user_data] = (duration, end_time)
            del self.pending_kicks[username.lower()]
            return # User was kicked, stop processing

        # 3. Check for active duration kicks
        for user_data, (duration, end_time) in list(self.duration_kicks.items()):
            if time.time() < end_time:
                if user_data[0] == nickname or user_data[1] == ip_address or (user_data[2] and user_data[2] == username):
                    self.bot.kick_user(user_id)
                    return # User was kicked, stop processing
            else:
                del self.duration_kicks[user_data] # Clean up expired kick

        # 4. Check for active duration bans
        if ip_address in self.duration_bans:
            _, end_time = self.duration_bans[ip_address]
            if time.time() < end_time:
                self.bot.kick_user(user_id)
                return
            else:
                del self.duration_bans[ip_address]
    
        if username in self.duration_bans:
            _, end_time = self.duration_bans[username]
            if time.time() < end_time:
                self.bot.kick_user(user_id)
                return
            else:
                del self.duration_bans[username]
            
        # 5. Check the canonical multilingual blacklist only while the master
        # word filter is enabled. Thai/English/other languages share this path.
        if self.bot.profanity_filter_enabled:
            blacklist = utils.load_blacklist("blacklist.txt")
            if utils.contains_profanity(nickname, blacklist):
                if self.bot.bot_config["blacklist_mode"] == 1:
                    self.bot.kick_user(user_id)
                elif self.bot.bot_config["blacklist_mode"] == 2:
                    self.ban_user(user_id, BanType.BANTYPE_IPADDR)
                    self.bot.kick_user(user_id)
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
        if not self.pending_admin_alerts:
            return
        username = utils.ensure_text(ttstr(user.szUsername)).lower()
        authorized = [u.strip().lower() for u in self.bot.accounts_config["authorized_users"]]
        if user.uUserType != UserType.USERTYPE_ADMIN and username not in authorized:
            return
        for notice in self.pending_admin_alerts:
            self.bot.privateMessage(user.nUserID, notice)
        self.pending_admin_alerts = []

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
            user = self.bot.getUserByName(nickname)
            if user:
                self.ban_user(user.nUserID, ban_type)
                self.bot.send_message(self._("{nickname} has been banned for {duration}.").format(nickname=ttstr(user.szNickname), duration=duration_str))
                Thread(target=self.remove_ban_after_duration, args=(user, duration_seconds, ban_type)).start()
                self.bot.kick_user(user.nUserID)
            else:
                self.bot.privateMessage(textmessage.nFromUserID, self._("User '{nickname}' not found.").format(nickname=nickname))
        except (ValueError, IndexError):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid format. Usage: db <nickname> <duration> (e.g., 1h:30m:10s)"))

    def handle_duration_kick_nickname(self, textmessage, *args):
        try:
            args_str = " ".join(args)
            parts = args_str.rsplit(" ", 1)
            if len(parts) != 2:
                raise ValueError("Invalid format")
            nickname, duration_str = parts[0], parts[1]
            duration_seconds = self.parse_duration_string(duration_str)
            user = self.bot.getUserByName(nickname)
            if user:
                self.bot.kick_user(user.nUserID)
                self.bot.send_message(self._("{nickname} has been kicked for {duration}.").format(nickname=ttstr(user.szNickname), duration=duration_str))
                user_data = (ttstr(user.szNickname), ttstr(user.szIPAddress), ttstr(user.szUsername))
                self.duration_kicks[user_data] = (duration_seconds, time.time() + duration_seconds)
            else:
                self.pending_kicks[nickname.lower()] = ("nickname", duration_seconds, time.time() + duration_seconds)
                self.bot.send_message(self._("User '{nickname}' not found. They will be kicked when they log in for {duration}.").format(nickname=nickname, duration=duration_str))
        except (ValueError, IndexError):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid format. Usage: dk <nickname> <duration>"))

    def handle_duration_kick_by_username(self, textmessage, *args):
        try:
            args_str = " ".join(args)
            parts = args_str.rsplit(" ", 1)
            if len(parts) != 2:
                raise ValueError("Invalid format")
            username, duration_str = parts[0], parts[1]
            duration_seconds = self.parse_duration_string(duration_str)
            user = self.bot.getUserByUsername(ttstr(username))
            if user and user.nUserID != 0:
                self.bot.kick_user(user.nUserID)
                self.bot.send_message(self._("User with username '{username}' has been kicked for {duration}.").format(username=username, duration=duration_str))
                user_data = (ttstr(user.szNickname), ttstr(user.szIPAddress), ttstr(user.szUsername))
                self.duration_kicks[user_data] = (duration_seconds, time.time() + duration_seconds)
            else:
                self.pending_kicks[username.lower()] = ("username", duration_seconds, time.time() + duration_seconds)
                self.bot.send_message(self._("User with username '{username}' not found. They will be kicked when they log in for {duration}.").format(username=username, duration=duration_str))
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

    def remove_ban_after_duration(self, user, duration_seconds, ban_type):
        time.sleep(duration_seconds)
        if ban_type == BanType.BANTYPE_IPADDR:
            self.bot.doUnBanUser(user.szIPAddress, 0)
            self.bot.send_message(self._("{nickname} (IP ban) has been unbanned.").format(nickname=ttstr(user.szNickname)))
        else:
            banned_user = BannedUser()
            banned_user.szUsername = user.szUsername
            banned_user.uBanTypes = BanType.BANTYPE_USERNAME
            self.bot.doUnbanUserEx(banned_user)
            self.bot.send_message(self._("{nickname} (Username ban) has been unbanned.").format(nickname=ttstr(user.szNickname)))


    def handle_change_name_command(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: cn <new_name>"))
            return
        new_name = " ".join(args)
        self.bot.bot_config["nickname"] = new_name
        self.bot.doChangeNickname(ttstr(new_name))
        self.bot.privateMessage(textmessage.nFromUserID, self._("Bot name changed to '{new_name}'.").format(new_name=new_name))

    def handle_change_status(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: cs <new_status>"))
            return
        status_message = " ".join(args)
        self.bot.bot_config["status_message"] = status_message
        self.bot.doChangeStatus(
            self.bot.bot_config['gender'],
            ttstr(self.bot.get_idle_status_message()),
        )
        self.bot.privateMessage(textmessage.nFromUserID, self._("Success"))

    def handle_change_gender(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: cg <m|f|n>"))
            return
        gender_mode = args[0].lower()
        gender_map = {'m': 0, 'f': 256, 'n': 4096}
        if gender_mode in gender_map:
            self.bot.bot_config["gender"] = gender_map[gender_mode]
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self.bot.get_idle_status_message()))
            self.bot.privateMessage(textmessage.nFromUserID, self._("Success"))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Available modes are: m for male, f for female, n for neutral."))
            
    def save_bot_config(self, textmessage, *args):
        self.bot.config_handler.save_bot_config(self.bot.bot_config)
        self.bot.config_handler.save_playback_config(self.bot.playback_config)
        self.bot.privateMessage(textmessage.nFromUserID, self._("Bot configuration saved."))

    def handle_shutdown_command(self, textmessage, *args):
        self.bot.privateMessage(textmessage.nFromUserID, self._("Shutting down..."))
        raise ShutdownSignal()

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

    def handle_lock_command(self, textmessage, *args):
        self.bot.commands_locked = not self.bot.commands_locked
        if self.bot.commands_locked:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Commands locked. Only admins can use commands."))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Commands unlocked. Commands available to everyone."))

    def handle_clear_command(self, textmessage, *args):
        target = " ".join(args)
        if target:
            self.clear_for_target(target)
        else:
            self.clear_all()

    def clear_for_target(self, target):
        found = False
        target_lower = target.lower()
        if target in self.banned_users:
            self.unban_user(self.banned_users[target])
            self.bot.send_message(self._("Cleared ban for {target}.").format(target=target))
            found = True
        
        for user_data, (duration, end_time) in list(self.duration_kicks.items()):
            nickname, ip_address, username = user_data
            if target in (nickname, ip_address, username):
                del self.duration_kicks[user_data]
                self.bot.send_message(self._("Cleared duration kick for {target}.").format(target=target))
                found = True
        
        if target_lower in self.pending_kicks:
            del self.pending_kicks[target_lower]
            self.bot.send_message(self._("Cleared pending kick for {target}.").format(target=target))
            found = True
            
        if not found:
            self.bot.send_message(self._("Target '{target}' not found in active bans or kicks.").format(target=target))

    def clear_all(self):
        if not self.banned_users and not self.duration_kicks and not self.pending_kicks:
            self.bot.send_message(self._("There are no active bans or kicks to clear."))
            return
        
        for ban_key in list(self.banned_users.keys()):
            self.unban_user(self.banned_users[ban_key])
        
        self.duration_kicks.clear()
        self.pending_kicks.clear()
        self.bot.send_message(self._("Cleared all bans and duration kicks."))

    def unban_user(self, banned_user_obj):
        try:
            if banned_user_obj.uBanTypes == BanType.BANTYPE_IPADDR:
                self.bot.doUnBanUser(banned_user_obj.szIPAddress, 0)
                if banned_user_obj.szIPAddress in self.banned_users:
                    del self.banned_users[banned_user_obj.szIPAddress]
            elif banned_user_obj.uBanTypes == BanType.BANTYPE_USERNAME:
                self.bot.doUnbanUserEx(banned_user_obj)
                if banned_user_obj.szUsername in self.banned_users:
                    del self.banned_users[banned_user_obj.szUsername]
        except Exception as e:
            print(f"Error during unban: {e}")

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

    def handle_global_broadcast_command(self, textmessage, *args):
        if not args: return
        msg = " ".join(args)
        self.bot.send_broadcast_message(f"[GLOBAL] {msg}")

    def handle_server_broadcast_command(self, textmessage, *args):
        if not args: return
        msg = " ".join(args)
        self.bot.send_broadcast_message(f"[SERVER] {msg}")

    def handle_host_broadcast_command(self, textmessage, *args):
        if not args: return
        msg = " ".join(args)
        self.bot.send_broadcast_message(f"[HOST] {msg}")

    def handle_tts_toggle_command(self, textmessage, *args):
        arg = args[0] if args else ""
        if arg == "on": self.bot.tts_enabled = True
        elif arg == "off": self.bot.tts_enabled = False
        else: self.bot.tts_enabled = not self.bot.tts_enabled
        self.bot.config_handler.update_bot_settings({"tts_enabled": self.bot.tts_enabled})
        self.bot.send_message(self._("TTS: {state}").format(state="ON" if self.bot.tts_enabled else "OFF"))

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

    def handle_restart_command(self, textmessage, *args):
        self.bot.privateMessage(textmessage.nFromUserID, self._("Restarting..."))
        raise RestartSignal()

    def handle_clear_log_command(self, textmessage, *args):
        data_dir = os.getenv("TTUTIL_DATA_DIR", ".")
        log_file = os.path.join(data_dir, "sntalkbot.log")
        if os.path.exists(log_file):
            with open(log_file, "w", encoding="utf-8"):
                pass
            self.bot.privateMessage(textmessage.nFromUserID, self._("Log cleared."))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Log file not found."))

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
