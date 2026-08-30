import shlex
import unicodedata
import logging
from TeamTalk5 import TextMessage, TextMsgType, UserType, ttstr
from bot.utils import BotUtils as utils


class Command:
    def __init__(self, name, handler, admin_only=False, help_text=""):
        self.name = name
        self.handler = handler
        self.admin_only = admin_only
        self.help_text = help_text


class CommandHandler:
    def __init__(self, bot):
        self.bot = bot
        self.commands = {}
        self.aliases = {}

    @staticmethod
    def _incoming_text(value):
        """Decode an incoming TeamTalk field on both Linux (bytes) and Windows (str)."""
        # TeamTalkPy's ttstr() is bidirectional on Linux: applying it to an
        # already-decoded Python str can encode it back to bytes. Avoid that
        # second conversion; this was the r7.4.2 event-loop crash.
        if isinstance(value, str):
            return value
        try:
            value = ttstr(value)
        except Exception:
            pass
        return utils.ensure_text(value)

    @classmethod
    def _strip_format_chars(cls, value):
        """Remove invisible Unicode format/control characters from command tokens."""
        text = unicodedata.normalize("NFKC", cls._incoming_text(value))
        return "".join(ch for ch in text if unicodedata.category(ch) not in {"Cf", "Cc"})

    def _normalize(self, name):
        # Canonical command names never include a prefix. Commands are prefix-free
        # in both private and channel/broadcast text; '/' remains optional legacy input.
        value = self._strip_format_chars(name).strip()
        if value.startswith("/"):
            value = value[1:]
        return value.strip().lower()

    def register_command(self, name, handler, admin_only=False, help_text=""):
        normalized = self._normalize(name)
        if not normalized:
            raise ValueError("Command name cannot be empty")
        if normalized in self.commands or normalized in self.aliases:
            raise ValueError(f"Duplicate command or alias {normalized}")
        self.commands[normalized] = Command(normalized, handler, admin_only, help_text)

    def register_alias(self, alias, target):
        alias_name = self._normalize(alias)
        target_name = self._normalize(target)
        if not alias_name or not target_name:
            raise ValueError("Alias and target cannot be empty")
        if alias_name == target_name:
            raise ValueError(f"Alias {alias_name} cannot target itself")
        if alias_name in self.commands or alias_name in self.aliases:
            raise ValueError(f"Duplicate command or alias {alias_name}")
        if target_name not in self.commands:
            raise ValueError(f"Alias {alias_name} targets unknown command {target_name}")
        self.aliases[alias_name] = target_name

    def resolve_name(self, name):
        normalized = self._normalize(name)
        return self.aliases.get(normalized, normalized)

    def aliases_for(self, target):
        target_name = self.resolve_name(target)
        return sorted(alias for alias, canonical in self.aliases.items() if canonical == target_name)

    def has_name(self, name):
        normalized = self._normalize(name)
        return normalized in self.commands or normalized in self.aliases

    def _split_message(self, message_text):
        try:
            return shlex.split(message_text)
        except ValueError:
            return message_text.split()

    @staticmethod
    def _numeric(value):
        """Return an int for plain ints, ctypes scalars, and enum-like values."""
        if hasattr(value, "value"):
            value = value.value
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def is_channel_message(self, textmessage):
        """Return True for TeamTalk public channel/broadcast text.

        Prefer an explicit message type first. Some receive wrappers have exposed
        a non-zero ``nChannelID`` even on direct messages, which is why older
        private-message routing failed at runtime. Only use channel ID as a
        fallback when the message type is unavailable/unknown.
        """
        msg_type = self._numeric(getattr(textmessage, "nMsgType", None))
        channel_type = self._numeric(getattr(TextMsgType, "MSGTYPE_CHANNEL", None))
        broadcast_type = self._numeric(getattr(TextMsgType, "MSGTYPE_BROADCAST", None))
        user_type = self._numeric(getattr(TextMsgType, "MSGTYPE_USER", None))
        custom_type = self._numeric(getattr(TextMsgType, "MSGTYPE_CUSTOM", None))
        if msg_type in {value for value in (user_type, custom_type) if value is not None}:
            return False
        if msg_type in {value for value in (channel_type, broadcast_type) if value is not None}:
            return True
        channel_id = self._numeric(getattr(textmessage, "nChannelID", None))
        return channel_id is not None and channel_id > 0

    def channel_input_allowed(self, textmessage, enabled=True):
        """Private input is always allowed; channel input follows the admin toggle."""
        return bool(enabled) or not self.is_channel_message(textmessage)

    def should_reply_unknown(self, textmessage, my_user_id):
        """Return True only for an unknown direct USER message from someone else.

        Legacy TTMediaBot emitted its unknown-command hint for direct user text,
        not ordinary channel conversation.  Keep that behavior so prefix-free
        channel commands remain convenient without turning normal chat into
        a stream of command-error replies. TeamTalk CUSTOM events (e.g. typing)
        are also excluded.
        """
        msg_type = self._numeric(getattr(textmessage, "nMsgType", None))
        user_type = self._numeric(getattr(TextMsgType, "MSGTYPE_USER", None))
        from_user_id = self._numeric(getattr(textmessage, "nFromUserID", None))
        my_user_id = self._numeric(my_user_id)
        return user_type is not None and msg_type == user_type and from_user_id != my_user_id

    def _command_parts(self, message_text, textmessage=None):
        """Parse registered commands prefix-free in both private and channel text.

        This intentionally follows the working r7.3/r7.4 TTMediaBot-style path:
        every incoming message is tried directly against the canonical command/
        alias table. Unknown ordinary chat falls through untouched. A single
        leading slash is still accepted for backward compatibility, but it is
        never required in either private or channel/broadcast messages.
        """
        text = unicodedata.normalize("NFKC", self._incoming_text(message_text)).strip()
        while text and unicodedata.category(text[0]) in {"Cf", "Cc"}:
            text = text[1:].lstrip()
        if not text:
            return None, []
        parts = self._split_message(text)
        if not parts:
            return None, []
        requested_name = self._normalize(parts[0])
        if not requested_name or not self.has_name(requested_name):
            return None, []
        return requested_name, parts[1:]

    def is_command_candidate(self, message_text, textmessage=None):
        requested_name, _args = self._command_parts(message_text, textmessage)
        return requested_name is not None

    def handle_message(self, textmessage: TextMessage):
        message_text = self._incoming_text(textmessage.szMessage)
        requested_name, args = self._command_parts(message_text, textmessage)
        if requested_name is None:
            return False

        command_name = self.resolve_name(requested_name)
        command = self.commands.get(command_name)
        if command is None:
            return False

        sender_username = self._incoming_text(textmessage.szFromUsername)
        is_authorized = self.bot.is_authorized_user(sender_username)
        user = self.bot.getUser(textmessage.nFromUserID)
        if user and user.uUserType == UserType.USERTYPE_ADMIN:
            is_authorized = True

        if self.bot.commands_locked and not is_authorized:
            self.bot.privateMessage(textmessage.nFromUserID, self.bot._("Commands are locked. Admins only."))
            return True

        # Blocking the canonical command also blocks every alias that resolves to it.
        if command_name in getattr(self.bot, "blocked_commands", set()) and not is_authorized:
            self.bot.privateMessage(textmessage.nFromUserID, self.bot._("This command is currently blocked by an administrator."))
            return True

        if command.admin_only and not is_authorized:
            self.bot.privateMessage(textmessage.nFromUserID, self.bot._("Not authorized"))
            return True

        # Console logs must prove that a command reached the dispatcher.  Player
        # and ordinary commands are safe to show exactly as typed; admin-only
        # arguments are redacted because they may contain passwords, messages,
        # tokens, paths, or other operator-only data.  This is intentionally
        # separate from the bounded admin activity audit below.
        safe_message = message_text
        if command.admin_only and args:
            safe_message = f"{requested_name} <arguments redacted>"
        try:
            print(self.bot._("Message received: {message} from {username}").format(
                message=safe_message, username=sender_username
            ))
        except Exception:
            print(f"Command received: {requested_name} from {sender_username}")

        # Record only the canonical admin action name, never raw arguments. This
        # gives Manager/Full an audit trail without leaking passwords, messages,
        # tokens, or other command payloads into memory.
        if command.admin_only and is_authorized and getattr(self.bot, "server_management_enabled", False):
            try:
                nickname = self._incoming_text(getattr(user, "szNickname", "")) if user else sender_username
                self.bot.record_activity(
                    "admin", "command",
                    f"{nickname or sender_username or 'admin'} used {command_name}",
                    user_id=int(getattr(textmessage, "nFromUserID", 0) or 0),
                )
            except Exception:
                pass

        try:
            command.handler(textmessage, *args)
        except Exception as exc:
            logging.exception("Command %s failed", command_name)
            try:
                self.bot.privateMessage(
                    textmessage.nFromUserID,
                    f"Command {command_name} failed: {type(exc).__name__}: {exc}",
                )
            except Exception:
                pass
        return True
