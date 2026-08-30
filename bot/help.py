import gettext


HELP_CATEGORY_ORDER = (
    "general",
    "player",
    "queue",
    "tts",
    "translation",
    "users",
    "moderation",
    "system",
)

HELP_CATEGORY_COMMANDS = {
    "general": {"help", "about", "status", "myinfo", "admins", "gcid", "search", "weather", "dr", "report"},
    "player": {
        "p", "pm", "u", "pp", "s", "x", "n", "b", "+", "-", "t", "v", "l", "pg", "d", "r", "dl",
        "autoplay", "channel", "m", "m1", "m2", "m3", "3d", "3d2", "bass", "sp", "f", "hide", "select", ".", ",",
    },
    "queue": {"q", "ql", "qc", "dq", "cq", "fav", "playfav", "delfav", "favorites", "shuffle"},
    "tts": {
        "say", "rate", "pitch", "volume", "voice", "speed", "st", "ld", "get_voices", "ttsmode", "tts", "rb",
        "ptts", "pttsmode", "pvoice", "pvoices", "pttsrate", "pttsspeed",
    },
    "translation": {"tr", "pt", "wt"},
    "users": {"private", "who", "whoall", "users", "msg", "messages", "notify", "unotify", "account", "accounts", "new"},
    "moderation": {
        "db", "udb", "dk", "udk", "clear", "jail", "unjail", "jails", "k", "ks", "moveall", "join",
        "filter", "welcome", "welcomebroadcast", "noname", "vpn", "lock", "blockcmd", "channelinput", "intercept",
        "cm", "events", "globalbroadcast", "bm", "cn", "cs", "cg",
    },
    "system": {"restart", "shutdown", "reboot", "exec", "save", "clearlog", "language", "voicetx", "cc", "csize"},
}



class HelpCommands:
    """Localized command help catalog. Command syntax itself is never translated."""

    def __init__(self, config_handler):
        self.config_handler = config_handler
        self.bot_config = self.config_handler.get_bot_config()
        self.language = self.bot_config.get("language", "en")

        gettext.bindtextdomain("messages", "locales")
        gettext.textdomain("messages")
        try:
            translation = gettext.translation("messages", "locales", [self.language])
            translation.install()
            self._ = translation.gettext
        except FileNotFoundError:
            translation = gettext.translation("messages", "locales", ["en"], fallback=True)
            translation.install()
            self._ = translation.gettext

        self.commands = {
            'weather': self._('Get the current weather for your location or a specified user. Usage: weather optional:nickname'),
            'reboot': self._('Reboots the server (requires authorization)'),
            'exec': self._('Executes a command on the server via SSH (requires authorization). Usage: exec [command]'),
            'search': self._('Search Wikipedia and get a summary. Usage: search your query'),
            'say': self._('Make the bot speak the given text. Usage: say text'),
            'tr': self._('Enable or disable auto-translation for channel messages. Usage: tr <source_lang> <target_lang>'),
            'pt': self._('Enable or disable private translate mode. Usage: pt <source_lang> <target_lang>'),
            'voice voiceOrLanguage': self._('Set Microsoft voice name, or Google standard language code such as th.'),
            'rate value': self._('Set the voice rate (Microsoft mode only), value from -100 to 100.'),
            'pitch value': self._('Set the voice pitch (Microsoft mode only), value from -100 to 100.'),
            'volume value': self._('Set the voice volume (Microsoft mode only), value from 0.1 to 1.0.'),
            'speed value': self._('Set the voice speed (Google TTS mode only), value from 0.25 to 4.0.'),
            'ttsmode microsoft|google': self._('Switch TTS mode between Microsoft Edge TTS and Google standard gTTS (no API key).'),
            'get_voices langcode': self._('List Microsoft voices, or Google standard gTTS languages in Google mode.'),
            'ld': self._('Enable or disable language detection.'),
            'tts on|off': self._('Admins only: Enable or disable TTS for everyone.'),
            'account': self._('Start the account request flow in private messages.'),
            'accounts on|off': self._('Admins only: Enable or disable account requests.'),
            'db name duration': self._('Admins only: Bans someone by IP address for a specified period.'),
            'udb name duration': self._('Admins only: Bans a username for a specified period.'),
            'dk name duration': self._('Admins only: Kicks someone for a specified period.'),
            'clear argument': self._('Admins only: Clears the duration ban or kick for a specified user. If sent without arguments: Clears all duration ban and kick.'),
            'st': self._('Admins only: Stop the current speech stream.'),
            'bm message': self._('Admins only: Sends a broadcast message to the server.'),
            'jail <name>': self._('For authorized users only, Adds someone to the jails list and move them to the jail channel. This adds the username to the list and not the nickname.'),
            'unjail <name>': self._('For authorized users. Removes someone from the jails list and moves them back to the root channel'),
            'jails': self._('Admins only: Gets the list of users who are in the jails list'),
            'cn <new name': self._("Admins only: Changes the bot's name."),
            'cs <status>': self._('Admins only: Changes the status message'),
            'cg mode': self._("Admins only: Changes the bot's gender. Available modes: m for male, f for female, n for neutral."),
            'private <name>': self._('Moves you and another one to a private hidden channel where no one can see it. This channel is only limited to 2 users only and will be deleted after both users log out of the server.'),
            'save': self._("Admins only: Saves the configuration in case you changed the bot's name and want to save it."),
            'lock': self._('Admins only: Toggle command lock so only admins can use commands.'),
            'channel': self._("When a video is playing, load the current video's channel and play its first video."),
            'admins': self._('Check the list of online administrators.'),
            'help [command]': self._('Show the command list one command per TeamTalk message. Usage: help optional:command'),
            'p <query>': self._('Search and play/enqueue from YouTube.'),
            'pm <query>': self._('Search and play/enqueue from YouTube Music.'),
            'u <link>': self._('Play a URL or start the first playlist. In Queue Mode, enqueue the URL/playlist.'),
            'pp <playlist_link>': self._('Player/Full: append another YouTube or YouTube Music playlist without interrupting the current track. In Queue Mode, append the whole playlist to FIFO queue.'),
            's': self._('Stop playback only; keep queue, playlist, and current item.'),
            'x': self._('Pause or resume playback.'),
            'n': self._('Queue mode: play next queued item. Normal mode: play the next related Radio track.'),
            'b': self._('Queue mode: play the previous queued-history item. Normal mode: go back in related Radio history.'),
            '+': self._('Seek 10 seconds forward.'),
            '-': self._('Seek 10 seconds backward.'),
            't <time>': self._('Seek to absolute time (e.g. 1:30).'),
            'q on|off': self._('Toggle queue system.'),
            'ql [page]': self._('List the queue in pages of 50 items; omit page to show the current queue page.'),
            'qc': self._('Check current queue position.'),
            'dq <index|title>': self._('Delete one queued item by number or song title.'),
            'cq': self._('Clear entire queue.'),
            'fav': self._('Save current track to favorites.'),
            'playfav': self._('Play/enqueue all favorite tracks.'),
            'delfav': self._('Clear favorites list.'),
            'l': self._('Get link of currently playing track.'),
            'pg': self._('Show current track information and progress.'),
            'r': self._('Show recently played tracks.'),
            'msg <username> <message>': self._('Send a private message to a user.'),
            'wt <source_lang> <target_lang>': self._('Enable whisper translation: translate channel/broadcast messages and send the translated text to you privately.'),
            'v <volume>': self._('Set player volume up to the configured maximum.'),
            'dl <link>': self._('Download audio with yt-dlp and upload it to the current TeamTalk channel.'),
            'd': self._('Show total, elapsed, and remaining time for the current track.'),
            'autoplay on|off': self._('Normal search: continue with related YouTube/YouTube Music Radio. Explicit playlists/channels/favorites keep their own order.'),
            'm': self._('Show the current TT Player mode.'),
            'm1': self._('Set M1 Single mode: stop after the current non-queue item.'),
            'm2': self._('Set M2 Auto/Next mode: automatically play the next item.'),
            'm3': self._('Set M3 Repeat mode: repeat the current non-queue track.'),
            '3d on|off': self._('Toggle the first stereo widening/3D audio filter.'),
            '3d2 on|off': self._('Toggle the second Extra Stereo depth filter.'),
            'bass on|off': self._('Toggle bass boost for music playback.'),
            'sp <speed>': self._('Set music playback speed.'),
            'f': self._('Toggle the player fade effect.'),
            'hide': self._('Toggle hiding the currently playing title from the bot status.'),
            '. [queue_position]': self._('Next search result. In Queue Mode, optionally change the search result of the specified 1-based queue position; without a number, change the newest queued search item.'),
            ', [queue_position]': self._('Previous search result. In Queue Mode, optionally change the search result of the specified 1-based queue position; without a number, change the newest queued search item.'),
            'myinfo': self._('Show your TeamTalk account/session information.'),
            'who': self._('Show how many currently known users are from your country.'),
            'whoall': self._('Show country counts for currently known server users.'),
            'users': self._('List currently connected users with account type, location, and status.'),
            'notify <nickname> <telegram_chat_id>': self._('Send a Telegram notification when a nickname logs in.'),
            'unotify <username> <telegram_chat_id>': self._('Send a Telegram notification when a username logs in.'),
            'messages': self._('Show pending offline messages you have sent.'),
            'new <username> <password> [rights]': self._('Admins only: Create a TeamTalk user account.'),
            'join <channel>': self._('Admins only: Move the bot to a channel.'),
            'moveall <channel>': self._('Admins only: Move users to a channel.'),
            'k <nickname>': self._('Admins only: Kick a user from the current channel.'),
            'ks <nickname>': self._('Admins only: Kick a user from the server.'),
            'udk <username> <duration>': self._('Admins only: Duration-kick a TeamTalk username.'),
            'globalbroadcast on|off|status|interval <minutes>|tts on|off': self._('Admins only (Manager/Full): Enable/disable the central Web Manager broadcast feed, set this bot interval from 1 to 10080 minutes, or speak the same central messages with TTS. Short alias: gb.'),
            'filter on|off|status': self._('Admins only: Enable, disable, or show the master multilingual word filter. OFF disables blacklist/badword checks together; ON enables them together, including channel moderation before channel-input gating.'),
            'welcome': self._('Admins only: Toggle the static channel-join welcome message.'),
            'welcomebroadcast [on|off|status]': self._('Admins only: Enable, disable, or show the randomized public login welcome broadcast. The setting is saved to config.ini.'),
            'vpn': self._('Admins only: Toggle VPN/proxy detection.'),
            'noname': self._('Admins only: Toggle automatic handling of users named NoName.'),
            'cm [on|off|status]': self._('Admins only: Enable, disable, or show Player announcements in the TeamTalk channel. With no argument, toggle the current setting.'),
            'cc': self._('Admins only: Clear the media download/cache files.'),
            'csize': self._('Admins only: Show the media cache size.'),
            'clearlog': self._('Admins only: Clear the bot error/log file.'),
            'restart': self._('Admins only: Restart the bot process in place using the main launcher loop.'),
            'shutdown': self._('Admins only: Cleanly shut down the bot.'),
            'about': self._('Show bot version and runtime information.'),
            'report <message>': self._('Send a help request or problem report to online administrators.'),
            'dr <message>': self._('Report a bug, report a problem, request a feature, or send a feature suggestion directly to the SNTalkBot developer.'),
            'blockcmd [+|-]<command>': self._('Admins only: block or unblock one command for normal users; without an argument, list blocked commands.'),
            'gcid [channel path]': self._('Show the TeamTalk channel ID for the current channel or a specified channel path.'),
            'status': self._('Show a role-aware runtime dashboard. Player shows playback/queue/autoplay/cookie state; Manager shows moderation/input controls to admins; Full combines both.'),
            'channelinput on|off|status': self._('Admins only: Enable, disable, or show normal channel input. When off, commands/TTS/player/translation stop reacting to channel text, but moderation still runs. Short alias: ci.'),
            'intercept on|off|status': self._('Admins only (Manager/Full): Enable, disable, or show interception of channel messages from users in all server channels. Short alias: ic.'),
            'events [1-25]': self._('Admins only (Manager/Full): Show recent real TeamTalk/admin activity from the bounded in-memory audit ring; command arguments/secrets are never stored.'),
            'language <code>': self._('Admins only: save the bot interface language code. Restart the bot to reload every module in the new language.'),
            'voicetx on|off': self._('Admins only: manually enable or disable TeamTalk voice transmission.'),
            'select <index>': self._('Select and play the indexed item from the active queue or playlist. Use . and , for search results.'),
            'favorites': self._('List saved favorite tracks, one track per message.'),
            'shuffle': self._('Shuffle only the unplayed part of the current queue.'),
            'ptts [on|off|status]': self._('Admins only: Control Player track/queue TTS announcements. Also supports ptts tracks on|off and ptts queue on|off.'),
            'pttsmode microsoft|google': self._('Admins only: Select Microsoft Edge TTS or Google standard gTTS for Player announcements.'),
            'pvoice <voice_or_language>': self._('Admins only: Set Microsoft Player voice, or Google language code such as th.'),
            'pvoices [langcode]': self._('List Microsoft Player voices or Google standard gTTS languages.'),
            'pttsrate <-100..100>': self._('Admins only: Set Microsoft Player announcement speaking rate.'),
            'pttsspeed <0.25..4.0>': self._('Admins only: Set Google standard Player announcement speaking speed.'),
        }
        self._by_name = {syntax.lstrip('/').split()[0].lower(): (syntax, description) for syntax, description in self.commands.items()}

    def get(self, command_name):
        return self._by_name.get((command_name or "").lstrip("/").lower())

    def line(self, command_name, admin_only=False, aliases=None):
        item = self.get(command_name)
        if item:
            syntax, description = item
            syntax = syntax.lstrip("/")
        else:
            syntax = (command_name or "unknown").lstrip("/")
            description = self._("No help text is available for this command.")
        if admin_only and "admin" not in description.lower() and "ผู้ดูแล" not in description:
            description = self._("Admins only") + ". " + description
        # Help shows the canonical prefix-free syntax used in both Private and
        # Channel/Broadcast. A leading '/' is accepted only for compatibility.
        for known_name in self._by_name:
            description = description.replace("/" + known_name, known_name)
        aliases = list(aliases or [])
        if aliases:
            alias_text = ", ".join(name for name in aliases)
            description = description + " " + self._("Short aliases: {aliases}").format(aliases=alias_text)
        return f"{syntax} : {description}"

    def category_for(self, command_name):
        name = (command_name or "").lower()
        for category in HELP_CATEGORY_ORDER:
            if name in HELP_CATEGORY_COMMANDS.get(category, set()):
                return category
        return "general"

    def category_label(self, category):
        # Thai is the primary deployment language. Other locales get stable
        # English headings even when their catalog has not translated these
        # structural labels yet; command descriptions remain fully localized.
        thai = {
            "general": "ทั่วไปและข้อมูล",
            "player": "เครื่องเล่นเพลง",
            "queue": "คิวและรายการโปรด",
            "tts": "เสียงพูดและ TTS",
            "translation": "การแปลภาษา",
            "users": "ผู้ใช้ ข้อความ และบัญชี",
            "moderation": "ผู้ดูแลและการกลั่นกรอง",
            "system": "ระบบและการดูแลบอต",
        }
        english = {
            "general": "General and information",
            "player": "Music player",
            "queue": "Queue and favorites",
            "tts": "Speech and TTS",
            "translation": "Translation",
            "users": "Users, messages, and accounts",
            "moderation": "Administration and moderation",
            "system": "System and bot lifecycle",
        }
        if str(self.language or "").lower().startswith("th"):
            return thai.get(category, category)
        return english.get(category, category)

    def registered_groups(self, command_handler):
        """Return active commands grouped by intent, preserving one handler per command."""
        groups = []
        for category in HELP_CATEGORY_ORDER:
            names = [
                name for name in command_handler.commands
                if self.category_for(name) == category
            ]
            if not names:
                continue
            lines = []
            for name in sorted(names, key=lambda value: value.lower()):
                command = command_handler.commands[name]
                lines.append(self.line(name, command.admin_only, command_handler.aliases_for(name)))
            groups.append((self.category_label(category), lines))
        return groups

    def registered_lines(self, command_handler):
        """Return active help lines in the same category order used by runtime help."""
        return [line for _category, lines in self.registered_groups(command_handler) for line in lines]
