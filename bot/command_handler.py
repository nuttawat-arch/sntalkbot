import shlex
from TeamTalk5 import TextMessage, TextMsgType, UserType, ttstr


class Command:
    def __init__(self, name, handler, admin_only=False, help_text=""):
        self.name = name
        self.handler = handler
        self.admin_only = admin_only
        self.help_text = help_text


class CommandHandler:
    def __init__(self, bot, prefix='/'):
        self.bot = bot
        self.prefix = prefix
        self.commands = {}
        self.aliases = {}

    def _normalize(self, name):
        return str(name or "").strip().lstrip(self.prefix).lower()

    def register_command(self, name, handler, admin_only=False, help_text=""):
        normalized = self._normalize(name)
        if not normalized:
            raise ValueError("Command name cannot be empty")
        if normalized in self.commands or normalized in self.aliases:
            raise ValueError(f"Duplicate command or alias /{normalized}")
        self.commands[normalized] = Command(normalized, handler, admin_only, help_text)

    def register_alias(self, alias, target):
        alias_name = self._normalize(alias)
        target_name = self._normalize(target)
        if not alias_name or not target_name:
            raise ValueError("Alias and target cannot be empty")
        if alias_name == target_name:
            raise ValueError(f"Alias /{alias_name} cannot target itself")
        if alias_name in self.commands or alias_name in self.aliases:
            raise ValueError(f"Duplicate command or alias /{alias_name}")
        if target_name not in self.commands:
            raise ValueError(f"Alias /{alias_name} targets unknown command /{target_name}")
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

    def _is_private_message(self, textmessage):
        """Return True when *textmessage* is addressed directly to this bot.

        TeamTalk's TextMessage structure gives user-to-user messages a non-zero
        ``nToUserID`` while channel messages use ``nToUserID == 0``.  Prefer this
        structural destination check because it reflects what the server actually
        delivered and is robust across Python wrapper enum representations.

        MSGTYPE_USER / MSGTYPE_CUSTOM remain a compatibility fallback for tests
        or wrappers which do not expose ``nToUserID``.
        """
        to_user_id = self._numeric(getattr(textmessage, "nToUserID", None))
        if to_user_id is not None:
            try:
                my_user_id = self._numeric(self.bot.getMyUserID())
            except Exception:
                my_user_id = None
            if to_user_id > 0:
                # Incoming direct messages should target this bot.  If the local
                # user ID is temporarily unavailable during an SDK edge case, a
                # non-zero destination is still unambiguously not a channel msg.
                return my_user_id in (None, 0, to_user_id)
            # A real nToUserID field with zero means channel/broadcast, never a
            # slashless private command.
            return False

        msg_type = self._numeric(getattr(textmessage, "nMsgType", None))
        private_types = {self._numeric(TextMsgType.MSGTYPE_USER)}
        custom_type = getattr(TextMsgType, "MSGTYPE_CUSTOM", None)
        if custom_type is not None:
            private_types.add(self._numeric(custom_type))
        return msg_type in private_types

    def is_slashless_command_candidate(self, message_text, textmessage):
        """Return True only for a known slashless command in a private message.

        Slashless commands are intentionally private-message only. Channel text
        always requires the leading slash so short aliases cannot hijack chat.
        """
        text = ttstr(message_text).strip()
        if not text or text.startswith(self.prefix):
            return False
        if not self._is_private_message(textmessage):
            return False
        parts = self._split_message(text)
        if not parts:
            return False
        return self.has_name(parts[0])

    def handle_message(self, textmessage: TextMessage):
        message_text = ttstr(textmessage.szMessage).strip()
        if not message_text:
            return False

        explicit_prefix = message_text.startswith(self.prefix)
        if explicit_prefix:
            command_text = message_text[len(self.prefix):].lstrip()
        else:
            if not self.is_slashless_command_candidate(message_text, textmessage):
                return False
            command_text = message_text

        parts = self._split_message(command_text)
        if not parts:
            return False

        requested_name = parts[0].lower()
        args = parts[1:]
        if not requested_name:
            return False

        command_name = self.resolve_name(requested_name)
        command = self.commands.get(command_name)
        if command is None:
            # Unknown plain text is never treated as a command.  Only an explicit
            # slash invocation gets an unknown-command response.
            if explicit_prefix:
                self.bot.privateMessage(textmessage.nFromUserID, self.bot._("Unknown command. Use /help to see all commands."))
                return True
            return False

        sender_username = ttstr(textmessage.szFromUsername)
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

        command.handler(textmessage, *args)
        return True
