import shlex
from TeamTalk5 import TextMessage, UserType, ttstr


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

    def register_command(self, name, handler, admin_only=False, help_text=""):
        normalized = str(name).strip().lstrip(self.prefix).lower()
        if not normalized:
            raise ValueError("Command name cannot be empty")
        if normalized in self.commands:
            previous = self.commands[normalized]
            raise ValueError(f"Duplicate command /{normalized}: {previous.handler} and {handler}")
        self.commands[normalized] = Command(normalized, handler, admin_only, help_text)

    def handle_message(self, textmessage: TextMessage):
        message_text = ttstr(textmessage.szMessage).strip()
        # All commands are slash commands. Plain text is never parsed as a command.
        if not message_text.startswith(self.prefix):
            return False

        try:
            parts = shlex.split(message_text)
        except ValueError:
            parts = message_text.split()
        if not parts:
            return False

        command_name = parts[0][len(self.prefix):].lower()
        args = parts[1:]
        if not command_name:
            return False

        sender_username = ttstr(textmessage.szFromUsername)
        is_authorized = self.bot.is_authorized_user(sender_username)
        user = self.bot.getUser(textmessage.nFromUserID)
        if user and user.uUserType == UserType.USERTYPE_ADMIN:
            is_authorized = True

        if self.bot.commands_locked and not is_authorized:
            self.bot.privateMessage(textmessage.nFromUserID, self.bot._("Commands are locked. Admins only."))
            return True

        command = self.commands.get(command_name)
        if command is None:
            self.bot.privateMessage(textmessage.nFromUserID, self.bot._("Unknown command. Use /help to see all commands."))
            return True

        if command_name in getattr(self.bot, "blocked_commands", set()) and not is_authorized:
            self.bot.privateMessage(textmessage.nFromUserID, self.bot._("This command is currently blocked by an administrator."))
            return True

        if command.admin_only and not is_authorized:
            self.bot.privateMessage(textmessage.nFromUserID, self.bot._("Not authorized"))
            return True

        command.handler(textmessage, *args)
        return True
