import re
import secrets
import time
import logging
from TeamTalk5 import TextMsgType, UserType, ttstr
from bot.utils import BotUtils as utils


class AccountRequestCog:
    """Self-service TeamTalk account creation verified through Telegram.

    Password and OTP exist only in this process while the request is active. The
    persistent registry stores only identity/deduplication metadata in SQLite.
    """

    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.active_requests = {}
        self.intent_keywords = [
            "account", "accounts", "signup", "sign up", "register",
            "registration", "create account", "new account", "حساب", "تسجيل",
        ]

    def register(self, command_handler):
        command_handler.register_command("account", self.handle_account_command)
        command_handler.register_command("accounts", self.handle_accounts_command, admin_only=True)

    def on_user_parted(self, user):
        # Sensitive workflow material deliberately does not persist.
        self.active_requests.pop(user.nUserID, None)

    def handle_message(self, textmessage):
        if textmessage.nMsgType != TextMsgType.MSGTYPE_USER:
            return False
        user_id = textmessage.nFromUserID
        message_text = utils.ensure_text(ttstr(textmessage.szMessage)).strip()
        if not message_text:
            return False
        if user_id in self.active_requests:
            if not self._ensure_service_available(user_id):
                self.active_requests.pop(user_id, None)
                return True
            self._handle_flow_message(user_id, message_text)
            return True
        if self.bot.command_handler.is_command_candidate(message_text, textmessage):
            return False
        if self._is_account_intent(message_text):
            if self._ensure_service_available(user_id):
                self._start_flow(user_id)
            return True
        return False

    def handle_account_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if not self._ensure_service_available(user_id):
            return
        if user_id in self.active_requests:
            self.bot.privateMessage(
                user_id,
                self.bot._("You already have an active account request. Please continue in private messages."),
            )
            return
        self._start_flow(user_id)

    def handle_accounts_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        user = self.bot.getUser(user_id)
        value = args[0].strip().lower() if args else "status"
        if value == "status":
            state = self._("enabled") if self.bot.account_request_config.get("enabled", False) else self._("disabled")
            message = self._("Account requests are currently {state}.").format(state=state)
        elif value in ("on", "off"):
            enabled = value == "on"
            self.bot.account_request_config["enabled"] = enabled
            self.bot.config_handler.save_account_request_config({"enabled": enabled})
            state = self._("enabled") if enabled else self._("disabled")
            message = self._("Account requests have been {state}.").format(state=state)
        else:
            message = self._("Invalid value. Use accounts on, accounts off, or accounts status.")
        self.bot.privateMessage(user_id, message)
        if user and user.nChannelID == self.bot.getMyChannelID():
            self.bot.send_message(message)

    def _is_account_intent(self, message_text):
        lowered = message_text.lower()
        return any(keyword in lowered for keyword in self.intent_keywords)

    def _ensure_service_available(self, user_id):
        if not self.bot.account_request_config.get("enabled", False):
            self.bot.privateMessage(user_id, self.bot._("Account requests are disabled by the administrator."))
            return False
        if not self.bot.telegram_config.get("telegram_bot_token"):
            self.bot.privateMessage(
                user_id,
                self.bot._("Account requests are unavailable because Telegram is not configured."),
            )
            return False
        return True

    def _start_flow(self, user_id):
        user = self.bot.getUser(user_id)
        if not user:
            return
        ip_address = ttstr(user.szIPAddress)
        if self.bot.state_store.account_exists(ip_address=ip_address):
            self.bot.privateMessage(
                user_id,
                self.bot._("Only one account is allowed per person. Our records show an account for your IP."),
            )
            return
        self.active_requests[user_id] = {
            "stage": "username",
            "data": {},
            "attempts": 0,
            "ip_address": ip_address,
            "user_id": user_id,
        }
        self.bot.privateMessage(user_id, self.bot._("Sure. Please send a username for your new account."))

    def _handle_flow_message(self, user_id, message_text):
        state = self.active_requests.get(user_id)
        if not state:
            return
        stage = state["stage"]
        if stage == "username":
            self._handle_username(user_id, state, message_text)
        elif stage == "password":
            self._handle_password(user_id, state, message_text)
        elif stage == "telegram":
            self._handle_telegram(user_id, state, message_text)
        elif stage == "otp":
            self._handle_otp(user_id, state, message_text)

    def _handle_username(self, user_id, state, message_text):
        username = message_text.strip()
        if not re.match(r"^[A-Za-z0-9._-]{3,32}$", username):
            self.bot.privateMessage(
                user_id,
                self.bot._("Invalid username. Use 3-32 characters: letters, numbers, dot, underscore, or dash."),
            )
            return
        if self.bot.state_store.account_exists(username=username):
            self.bot.privateMessage(user_id, self.bot._("This username is already registered."))
            self.active_requests.pop(user_id, None)
            return
        state["data"]["username"] = username
        state["stage"] = "password"
        self.bot.privateMessage(user_id, self.bot._("Great. Now send a password for the account."))

    def _handle_password(self, user_id, state, message_text):
        password = message_text.strip()
        if len(password) < 6:
            self.bot.privateMessage(user_id, self.bot._("Password is too short. Please send at least 6 characters."))
            return
        # Never write the TeamTalk password to disk/database. It is needed only
        # once for doNewUserAccount() after OTP verification.
        state["data"]["password"] = password
        state["stage"] = "telegram"
        self.bot.privateMessage(
            user_id,
            self.bot._("Now send the Telegram chat ID that should receive your verification code."),
        )

    def _handle_telegram(self, user_id, state, message_text):
        chat_id = message_text.strip()
        if not re.match(r"^-?\d+$", chat_id):
            self.bot.privateMessage(user_id, self.bot._("Invalid Telegram chat ID. Please send the numeric chat ID."))
            return
        if self.bot.state_store.account_exists(telegram_chat_id=chat_id):
            self.bot.privateMessage(user_id, self.bot._("This Telegram account is already linked to an account request."))
            self.active_requests.pop(user_id, None)
            return
        state["data"]["telegram_chat_id"] = chat_id
        success, error_message = self._send_otp(state)
        if not success:
            self.bot.privateMessage(
                user_id,
                error_message or self.bot._("Failed to send the Telegram verification code. Please try again later."),
            )
            self.active_requests.pop(user_id, None)
            return
        state["stage"] = "otp"
        self.bot.privateMessage(user_id, self.bot._("A verification code was sent to Telegram. Please enter the 6-digit code."))

    def _send_otp(self, state):
        code = f"{secrets.randbelow(1000000):06d}"
        expiry = int(self.bot.account_request_config.get("otp_expiry_seconds", 600) or 600)
        state["otp"] = code
        state["otp_expires_at"] = time.time() + max(60, expiry)
        chat_id = state["data"].get("telegram_chat_id")
        username = state["data"].get("username", "")
        minutes = max(1, expiry // 60)
        message = self.bot._(
            "TeamTalk account verification for {username}\nCode: {code}\nExpires in {minutes} minute(s)."
        ).format(username=username, code=code, minutes=minutes)
        if not utils.send_telegram_notification(
            self.bot.telegram_config.get("telegram_bot_token"), chat_id, message
        ):
            state.pop("otp", None)
            state.pop("otp_expires_at", None)
            return False, self.bot._("Telegram could not deliver the verification code. Make sure you have started the bot and try again.")
        return True, None

    def _handle_otp(self, user_id, state, message_text):
        code = message_text.strip()
        max_attempts = int(self.bot.account_request_config.get("max_attempts", 3) or 3)
        if not re.match(r"^\d{6}$", code) or code != state.get("otp") or time.time() > state.get("otp_expires_at", 0):
            state["attempts"] += 1
            if state["attempts"] >= max_attempts:
                self.bot.privateMessage(user_id, self.bot._("Too many invalid attempts. Please start again."))
                self.active_requests.pop(user_id, None)
            else:
                self.bot.privateMessage(user_id, self.bot._("Invalid or expired code. Please enter the active 6-digit code."))
            return

        success, error_message = self._register_account(state)
        if success:
            self.bot.privateMessage(user_id, self.bot._("Success! Your account has been created."))
            self._notify_admins(state)
        else:
            self.bot.privateMessage(user_id, error_message or self.bot._("Account creation failed. Please try again later."))
        # Drop password + OTP immediately with the whole request object.
        self.active_requests.pop(user_id, None)

    def _register_account(self, state):
        username = state["data"]["username"]
        password = state["data"]["password"]
        account = self.bot.account_creator.create_user_account()
        account.szUsername = ttstr(username)
        account.szPassword = ttstr(password)
        account.uUserType = UserType.USERTYPE_DEFAULT
        account.uUserRights = 0
        if not self.bot.doNewUserAccount(account):
            return False, self.bot._("Account creation failed. Please try again later.")
        self.bot.state_store.record_account(
            username,
            telegram_chat_id=state["data"].get("telegram_chat_id"),
            ip_address=state.get("ip_address"),
        )
        return True, None

    def _notify_admins(self, state):
        ip_address = state.get("ip_address") or ""
        username = state["data"].get("username", "")
        chat_id = state["data"].get("telegram_chat_id", "")
        country, city = utils.get_user_location(ip_address)
        message = self.bot._(
            "New account created via bot.\nUsername: {username}\nTelegram chat: {chat}\nLocation: {location}"
        ).format(
            username=username,
            chat=chat_id,
            location=", ".join([value for value in [city, country] if value]) or "Unknown",
        )
        for server_user in self.bot.getServerUsers():
            if self.bot.is_authorized_user(ttstr(server_user.szUsername)) or server_user.uUserType == UserType.USERTYPE_ADMIN:
                self.bot.privateMessage(server_user.nUserID, message)
        admin_chat = self.bot.telegram_config.get("default_chat_id")
        if admin_chat and str(admin_chat) != str(chat_id):
            utils.send_telegram_notification(
                self.bot.telegram_config.get("telegram_bot_token"), admin_chat, message
            )
