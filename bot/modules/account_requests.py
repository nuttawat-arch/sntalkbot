import csv
import os
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
import logging
from TeamTalk5 import TextMsgType, UserType, ttstr
from bot.utils import BotUtils as utils


class AccountRequestCog:
    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.active_requests = {}
        self.intent_keywords = [
            "account",
            "accounts",
            "signup",
            "sign up",
            "register",
            "registration",
            "create account",
            "new account",
            "حساب",
            "تسجيل",
        ]

    def register(self, command_handler):
        command_handler.register_command("account", self.handle_account_command)
        command_handler.register_command("accounts", self.handle_accounts_command, admin_only=True)

    def on_user_parted(self, user):
        self.active_requests.pop(user.nUserID, None)

    def handle_message(self, textmessage):
        if textmessage.nMsgType != TextMsgType.MSGTYPE_USER:
            return False

        user_id = textmessage.nFromUserID
        message_text = ttstr(textmessage.szMessage).strip()
        if not message_text:
            return False
        if message_text.startswith(self.bot.command_handler.prefix):
            return False

        if user_id in self.active_requests:
            if not self._ensure_service_available(user_id):
                self.active_requests.pop(user_id, None)
                return True
            self._handle_flow_message(user_id, message_text)
            return True

        if self._is_account_intent(message_text):
            if not self._ensure_service_available(user_id):
                return True
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
        if not args:
            state = self._("enabled") if self.bot.account_request_config.get("enabled", False) else self._("disabled")
            message = self._("Account requests are currently {state}.").format(state=state)
            self.bot.privateMessage(user_id, message)
            if user and user.nChannelID == self.bot.getMyChannelID():
                self.bot.send_message(message)
            return
        value = args[0].strip().lower()
        if value not in ("on", "off"):
            message = self._("Invalid value. Use /accounts on or /accounts off.")
            self.bot.privateMessage(user_id, message)
            if user and user.nChannelID == self.bot.getMyChannelID():
                self.bot.send_message(message)
            return
        enabled = value == "on"
        self.bot.account_request_config["enabled"] = enabled
        if hasattr(self.bot.config_handler, "save_account_request_config"):
            self.bot.config_handler.save_account_request_config(self.bot.account_request_config)
        state = self._("enabled") if enabled else self._("disabled")
        message = self._("Account requests have been {state}.").format(state=state)
        self.bot.privateMessage(user_id, message)
        if user and user.nChannelID == self.bot.getMyChannelID():
            self.bot.send_message(message)

    def _is_account_intent(self, message_text):
        lowered = message_text.lower()
        if not any(keyword in lowered for keyword in self.intent_keywords):
            return False

        return True

    def _ensure_service_available(self, user_id):
        if not self.bot.account_request_config.get("enabled", False):
            self.bot.privateMessage(user_id, self.bot._("Account requests are disabled by the administrator."))
            return False
        if not self._smtp_is_configured():
            self.bot.account_request_config["enabled"] = False
            self.bot.privateMessage(
                user_id,
                self.bot._("Account requests are unavailable because email (SMTP) is not configured."),
            )
            return False
        return True

    def _smtp_is_configured(self):
        smtp_host = self.bot.account_request_config.get("smtp_host", "").strip()
        smtp_username = self.bot.account_request_config.get("smtp_username", "").strip()
        smtp_from = self.bot.account_request_config.get("smtp_from", "").strip()
        if not smtp_host:
            return False
        if not (smtp_from or smtp_username):
            return False
        return True

    def _start_flow(self, user_id):
        user = self.bot.getUser(user_id)
        if not user:
            return
        ip_address = ttstr(user.szIPAddress)
        reason = self._check_existing_account(ip_address=ip_address)
        if reason:
            self.bot.privateMessage(user_id, reason)
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
        elif stage == "email":
            self._handle_email(user_id, state, message_text)
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
        state["data"]["username"] = username
        state["stage"] = "password"
        self.bot.privateMessage(user_id, self.bot._("Great. Now send a password for the account."))

    def _handle_password(self, user_id, state, message_text):
        password = message_text.strip()
        if len(password) < 6:
            self.bot.privateMessage(user_id, self.bot._("Password is too short. Please send at least 6 characters."))
            return
        state["data"]["password"] = password
        state["stage"] = "email"
        self.bot.privateMessage(user_id, self.bot._("Thanks. Now send your email address."))

    def _handle_email(self, user_id, state, message_text):
        email = message_text.strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            self.bot.privateMessage(user_id, self.bot._("Invalid email address. Please send a valid email."))
            return

        username = state["data"].get("username")
        ip_address = state.get("ip_address")
        reason = self._check_existing_account(username=username, email=email, ip_address=ip_address)
        if reason:
            self.bot.privateMessage(user_id, reason)
            self.active_requests.pop(user_id, None)
            return

        state["data"]["email"] = email
        success, error_message = self._send_otp(state)
        if not success:
            self.bot.privateMessage(
                user_id,
                error_message or self.bot._("Failed to send verification email. Please try again later."),
            )
            self.active_requests.pop(user_id, None)
            return
        state["stage"] = "otp"
        self.bot.privateMessage(user_id, self.bot._("A verification code has been sent. Please enter the 6-digit code."))

    def _handle_otp(self, user_id, state, message_text):
        code = message_text.strip()
        max_attempts = self.bot.account_request_config.get("max_attempts", 3)
        if not re.match(r"^\d{6}$", code):
            state["attempts"] += 1
            if state["attempts"] >= max_attempts:
                self.bot.privateMessage(user_id, self.bot._("Too many invalid attempts. Please start again."))
                self.active_requests.pop(user_id, None)
                return
            self.bot.privateMessage(user_id, self.bot._("Invalid code. Please enter the 6-digit code."))
            return

        verified, error_message = self._verify_otp(state, code)
        if not verified:
            state["attempts"] += 1
            if state["attempts"] >= max_attempts:
                self.bot.privateMessage(user_id, self.bot._("Too many invalid attempts. Please start again."))
                self.active_requests.pop(user_id, None)
                return
            self.bot.privateMessage(
                user_id,
                error_message or self.bot._("Invalid code. Please enter the 6-digit code."),
            )
            return

        success, error_message = self._register_account(state)
        if success:
            self.bot.privateMessage(user_id, self.bot._("Success! Your account has been created."))
            self._notify_admins(state)
        else:
            self.bot.privateMessage(
                user_id,
                error_message or self.bot._("Account creation failed. Please try again later."),
            )
        self.active_requests.pop(user_id, None)

    def _send_otp(self, state):
        smtp_host = self.bot.account_request_config.get("smtp_host", "").strip()
        smtp_port = self.bot.account_request_config.get("smtp_port", 587)
        smtp_username = self.bot.account_request_config.get("smtp_username", "").strip()
        smtp_password = self.bot.account_request_config.get("smtp_password", "")
        smtp_use_tls = self.bot.account_request_config.get("smtp_use_tls", True)
        smtp_use_ssl = self.bot.account_request_config.get("smtp_use_ssl", False)
        smtp_tls_verify = self.bot.account_request_config.get("smtp_tls_verify", True)
        smtp_from = self.bot.account_request_config.get("smtp_from", "").strip() or smtp_username
        smtp_from_name = self.bot.account_request_config.get("smtp_from_name", "").strip()
        smtp_subject = self.bot.account_request_config.get("smtp_subject", "").strip() or self.bot._("Your verification code")
        smtp_timeout = self.bot.account_request_config.get("smtp_timeout", 15)
        otp_expiry_seconds = self.bot.account_request_config.get("otp_expiry_seconds", 600)

        if not smtp_host or not smtp_from:
            return False, self.bot._("Email service is not configured.")

        email = state["data"]["email"]
        code = f"{secrets.randbelow(1000000):06d}"
        expires_at = time.time() + otp_expiry_seconds
        state["otp"] = code
        state["otp_expires_at"] = expires_at

        message = self._build_verification_email(
            to_address=email,
            from_address=smtp_from,
            from_name=smtp_from_name,
            subject=smtp_subject,
            code=code,
            expires_in_seconds=otp_expiry_seconds,
            username=state["data"].get("username", "there"),
        )
        try:
            if smtp_tls_verify:
                context = ssl.create_default_context()
            else:
                context = ssl._create_unverified_context()
            if smtp_use_ssl:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=smtp_timeout, context=context) as smtp:
                    if smtp_username:
                        smtp.login(smtp_username, smtp_password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout) as smtp:
                    smtp.ehlo()
                    if smtp_use_tls:
                        smtp.starttls(context=context)
                        smtp.ehlo()
                    if smtp_username:
                        smtp.login(smtp_username, smtp_password)
                    smtp.send_message(message)
        except Exception as exc:
            logging.error(
                "SMTP send failed: host=%s port=%s user=%s from=%s to=%s tls=%s ssl=%s error=%s",
                smtp_host,
                smtp_port,
                smtp_username or "",
                smtp_from,
                email,
                smtp_use_tls,
                smtp_use_ssl,
                exc,
            )
            return False, self.bot._("Failed to send verification email. Please try again later.")
        return True, None

    def _verify_otp(self, state, code):
        expected = state.get("otp")
        expires_at = state.get("otp_expires_at", 0)
        if not expected:
            return False, self.bot._("No verification code is active. Please start again.")
        if time.time() > expires_at:
            return False, self.bot._("Verification code expired. Please start again.")
        if code != expected:
            return False, self.bot._("Invalid code. Please enter the 6-digit code.")
        return True, None

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
        self._record_new_account(state)
        return True, None

    def _record_new_account(self, state):
        user_data_file = self.bot.account_request_config.get("user_data_file", "")
        if not user_data_file:
            return
        try:
            directory = os.path.dirname(user_data_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(user_data_file, "a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        state["data"].get("username", ""),
                        state["data"].get("password", ""),
                        state["data"].get("email", ""),
                        state.get("ip_address", ""),
                    ]
                )
        except OSError:
            return

    def _build_verification_email(self, to_address, from_address, from_name, subject, code, expires_in_seconds, username):
        minutes = max(1, int(expires_in_seconds // 60))
        message = EmailMessage()
        message["To"] = to_address
        if from_name:
            message["From"] = f"{from_name} <{from_address}>"
        else:
            message["From"] = from_address
        message["Subject"] = subject
        message.set_content(
            self.bot._(
                "Dear {username},\n\n"
                "Thank you for your request to create a Blindmasters account. "
                "Your verification code is:\n\n"
                "{code}\n\n"
                "This code expires in {minutes} minute(s). If you did not request this, "
                "you can safely ignore this email.\n\n"
                "Best regards,\n"
                "Blindmasters"
            ).format(code=code, minutes=minutes, username=username)
        )
        return message


    def _check_existing_account(self, username=None, email=None, ip_address=None):
        user_data_file = self.bot.account_request_config.get("user_data_file", "")
        if not user_data_file or not os.path.isfile(user_data_file):
            return None
        try:
            with open(user_data_file, newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                for row in reader:
                    if username and len(row) > 0 and row[0].strip().lower() == username.lower():
                        return self.bot._("This username is already registered.")
                    if email and len(row) > 2 and row[2].strip().lower() == email.lower():
                        return self.bot._("This email address is already registered.")
                    if ip_address and len(row) > 3 and row[3].strip() == ip_address:
                        return self.bot._("Only one account is allowed per person. Our records show an account for your IP.")
        except OSError:
            return None
        return None

    def _notify_admins(self, state):
        ip_address = state.get("ip_address") or ""
        username = state["data"].get("username", "")
        email = state["data"].get("email", "")
        country, city = utils.get_user_location(ip_address)
        user = self.bot.getUserByUsername(ttstr(username))
        nickname = ttstr(user.szNickname) if user else ""
        message = self.bot._(
            "New account created via bot.\nUsername: {username}\nEmail: {email}\nIP: {ip}\nLocation: {location}\nNickname: {nickname}"
        ).format(
            username=username,
            email=email,
            ip=ip_address,
            location=", ".join([value for value in [city, country] if value]) or "Unknown",
            nickname=nickname or "Unknown",
        )
        for server_user in self.bot.getServerUsers():
            if self.bot.is_authorized_user(ttstr(server_user.szUsername)) or server_user.uUserType == UserType.USERTYPE_ADMIN:
                self.bot.privateMessage(server_user.nUserID, message)
        token = self.bot.account_request_config.get("telegram_bot_token")
        chat_id = self.bot.account_request_config.get("telegram_chat_id")
        utils.send_telegram_notification(token, chat_id, message)
