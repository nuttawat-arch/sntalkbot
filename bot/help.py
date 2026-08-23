import gettext


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
            '/weather': self._('Get the current weather for your location or a specified user. Usage: /weather optional:nickname'),
            '/reboot': self._('Reboots the server (requires authorization)'),
            '/exec': self._('Executes a command on the server via SSH (requires authorization). Usage: /exec [command]'),
            '/search': self._('Search Wikipedia and get a summary. Usage: /search your query'),
            '/say': self._('Make the bot speak the given text. Usage: /say text'),
            '/tr': self._('Enable or disable auto-translation for channel messages. Usage: /tr <source_lang> <target_lang>'),
            '/pt': self._('Enable or disable private translate mode. Usage: /pt <source_lang> <target_lang>'),
            '/voice voiceOrLanguage': self._('Set Microsoft voice name, or Google standard language code such as th.'),
            '/rate value': self._('Set the voice rate (Microsoft mode only), value from -100 to 100.'),
            '/pitch value': self._('Set the voice pitch (Microsoft mode only), value from -100 to 100.'),
            '/volume value': self._('Set the voice volume (Microsoft mode only), value from 0.1 to 1.0.'),
            '/speed value': self._('Set the voice speed (Google TTS mode only), value from 0.25 to 4.0.'),
            '/ttsmode microsoft|google': self._('Switch TTS mode between Microsoft Edge TTS and Google standard gTTS (no API key).'),
            '/get_voices langcode': self._('List Microsoft voices, or Google standard gTTS languages in Google mode.'),
            '/ld': self._('Enable or disable language detection.'),
            '/tts on|off': self._('Admins only: Enable or disable TTS for everyone.'),
            '/rb on|off': self._('Admins only: Enable or disable Google TTS random broadcasts.'),
            '/account': self._('Start the account request flow in private messages.'),
            '/accounts on|off': self._('Admins only: Enable or disable account requests.'),
            '/db name duration': self._('Admins only: Bans someone by IP address for a specified period.'),
            '/udb name duration': self._('Admins only: Bans a username for a specified period.'),
            '/dk name duration': self._('Admins only: Kicks someone for a specified period.'),
            '/clear argument': self._('Admins only: Clears the duration ban or kick for a specified user. If sent without arguments: Clears all duration ban and kick.'),
            '/st': self._('Admins only: Stop the current speech stream.'),
            '/bm message': self._('Admins only: Sends a broadcast message to the server.'),
            '/jail <name>': self._('For authorized users only, Adds someone to the jails list and move them to the jail channel. This adds the username to the list and not the nickname.'),
            '/unjail <name>': self._('For authorized users. Removes someone from the jails list and moves them back to the root channel'),
            '/jails': self._('Admins only: Gets the list of users who are in the jails list'),
            '/cn <new name': self._("Admins only: Changes the bot's name."),
            '/cs <status>': self._('Admins only: Changes the status message'),
            '/cg mode': self._("Admins only: Changes the bot's gender. Available modes: m for male, f for female, n for neutral."),
            '/private <name>': self._('Moves you and another one to a private hidden channel where no one can see it. This channel is only limited to 2 users only and will be deleted after both users log out of the server.'),
            '/save': self._("Admins only: Saves the configuration in case you changed the bot's name and want to save it."),
            '/lock': self._('Admins only: Toggle command lock so only admins can use commands.'),
            '/channel': self._("When a video is playing, load the current video's channel and play its first video."),
            '/admins': self._('Check the list of online administrators.'),
            '/help [command]': self._('Show the command list one command per TeamTalk message. Usage: /help optional:command'),
            '/p <query>': self._('Search and play/enqueue from YouTube.'),
            '/pm <query>': self._('Search and play/enqueue from YouTube Music.'),
            '/u <link>': self._('Play/enqueue from a URL.'),
            '/s': self._('Stop playback and clear queue.'),
            '/x': self._('Pause or resume playback.'),
            '/n': self._('Play next track.'),
            '/b': self._('Play previous track.'),
            '/+': self._('Seek 10 seconds forward.'),
            '/-': self._('Seek 10 seconds backward.'),
            '/t <time>': self._('Seek to absolute time (e.g. 1:30).'),
            '/q on|off': self._('Toggle queue system.'),
            '/ql': self._('List items in current queue.'),
            '/qc': self._('Check current queue position.'),
            '/dq <index>': self._('Delete item from queue at index.'),
            '/cq': self._('Clear entire queue.'),
            '/fav': self._('Save current track to favorites.'),
            '/playfav': self._('Play/enqueue all favorite tracks.'),
            '/delfav': self._('Clear favorites list.'),
            '/l': self._('Get link of currently playing track.'),
            '/pg': self._('Show current track information and progress.'),
            '/r': self._('Show recently played tracks.'),
            '/msg <username> <message>': self._('Send a private message to a user.'),
            '/wt <source_lang> <target_lang>': self._('Enable whisper translation: translate channel/broadcast messages and send the translated text to you privately.'),
            '/v <volume>': self._('Set player volume up to the configured maximum.'),
            '/dl <link>': self._('Download audio with yt-dlp and upload it to the current TeamTalk channel.'),
            '/d': self._('Show total, elapsed, and remaining time for the current track.'),
            '/autoplay on|off': self._('Toggle automatic playback of the next item in the active search, playlist, channel, or favorites list.'),
            '/m': self._('Show the current TT Player mode.'),
            '/m1': self._('Set M1 Single mode: stop after the current non-queue item.'),
            '/m2': self._('Set M2 Auto/Next mode: automatically play the next item.'),
            '/m3': self._('Set M3 Repeat mode: repeat the current non-queue track.'),
            '/3d on|off': self._('Toggle the first stereo widening/3D audio filter.'),
            '/3d2 on|off': self._('Toggle the second stereo/echo audio filter.'),
            '/bass on|off': self._('Toggle bass boost for music playback.'),
            '/sp <speed>': self._('Set music playback speed.'),
            '/f': self._('Toggle the player fade effect.'),
            '/hide': self._('Toggle hiding the currently playing title from the bot status.'),
            '/.': self._('Select the next search result for the newest queued search item.'),
            '/,': self._('Select the previous search result for the newest queued search item.'),
            '/myinfo': self._('Show your TeamTalk account/session information.'),
            '/who': self._('Show how many currently known users are from your country.'),
            '/whoall': self._('Show country counts for currently known server users.'),
            '/users': self._('List currently connected users with account type, location, and status.'),
            '/notify <nickname> <telegram_chat_id>': self._('Send a Telegram notification when a nickname logs in.'),
            '/unotify <username> <telegram_chat_id>': self._('Send a Telegram notification when a username logs in.'),
            '/messages': self._('Show pending offline messages you have sent.'),
            '/new <username> <password> [rights]': self._('Admins only: Create a TeamTalk user account.'),
            '/join <channel>': self._('Admins only: Move the bot to a channel.'),
            '/moveall <channel>': self._('Admins only: Move users to a channel.'),
            '/k <nickname>': self._('Admins only: Kick a user from the current channel.'),
            '/ks <nickname>': self._('Admins only: Kick a user from the server.'),
            '/udk <username> <duration>': self._('Admins only: Duration-kick a TeamTalk username.'),
            '/bot <message>': self._('Admins only: Send a bot broadcast message according to the configured broadcast scope.'),
            '/sbot <message>': self._('Admins only: Send a server broadcast message.'),
            '/superbot <message>': self._('Admins only: Send a host/global broadcast message when supported.'),
            '/filter': self._('Admins only: Toggle the profanity/blacklist filter.'),
            '/welcome': self._('Admins only: Toggle the static channel-join welcome message.'),
            '/welcomebroadcast [on|off|status]': self._('Admins only: Enable, disable, or show the randomized public login welcome broadcast. The setting is saved to config.ini.'),
            '/vpn': self._('Admins only: Toggle VPN/proxy detection.'),
            '/noname': self._('Admins only: Toggle automatic handling of users named NoName.'),
            '/cm': self._('Admins only: Toggle player action messages in the TeamTalk channel.'),
            '/cc': self._('Admins only: Clear the media download/cache files.'),
            '/csize': self._('Admins only: Show the media cache size.'),
            '/clearlog': self._('Admins only: Clear the bot error/log file.'),
            '/restart': self._('Admins only: Restart the bot process in place using the main launcher loop.'),
            '/shutdown': self._('Admins only: Cleanly shut down the bot.'),
            '/about': self._('Show bot version and runtime information.'),
            '/report <message>': self._('Send a help request or problem report to online administrators.'),
            '/dr <message>': self._('Send a problem report directly to the official SNTalkBot developer report service.'),
            '/blockcmd [+|-]<command>': self._('Admins only: block or unblock one command for normal users; without an argument, list blocked commands.'),
            '/gcid [channel path]': self._('Show the TeamTalk channel ID for the current channel or a specified channel path.'),
            '/language <code>': self._('Admins only: save the bot interface language code. Restart the bot to reload every module in the new language.'),
            '/voicetx on|off': self._('Admins only: manually enable or disable TeamTalk voice transmission.'),
            '/select <index>': self._('Select and play the indexed item from the current search or active list.'),
            '/favorites': self._('List saved favorite tracks, one track per message.'),
            '/shuffle': self._('Shuffle only the unplayed part of the current queue.'),
            '/ptts [on|off|status]': self._('Admins only: Control Player track/queue TTS announcements. Also supports /ptts tracks on|off and /ptts queue on|off.'),
            '/pttsmode microsoft|google': self._('Admins only: Select Microsoft Edge TTS or Google standard gTTS for Player announcements.'),
            '/pvoice <voice_or_language>': self._('Admins only: Set Microsoft Player voice, or Google language code such as th.'),
            '/pvoices [langcode]': self._('List Microsoft Player voices or Google standard gTTS languages.'),
            '/pttsrate <-100..100>': self._('Admins only: Set Microsoft Player announcement speaking rate.'),
            '/pttsspeed <0.25..4.0>': self._('Admins only: Set Google standard Player announcement speaking speed.'),
        }
        self._by_name = {syntax[1:].split()[0].lower(): (syntax, description) for syntax, description in self.commands.items()}

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
        # Present slashless syntax as the default.  The old /command form remains
        # accepted for backward compatibility, but users no longer need to type it.
        for known_name in self._by_name:
            description = description.replace("/" + known_name, known_name)
        aliases = list(aliases or [])
        if aliases:
            alias_text = ", ".join(name for name in aliases)
            description = description + " " + self._("Short aliases: {aliases}").format(aliases=alias_text)
        return f"{syntax} : {description}"

    def registered_lines(self, command_handler):
        """Return one canonical help line per command, including its short aliases."""
        result = []
        for name in sorted(command_handler.commands, key=lambda value: value.lower()):
            command = command_handler.commands[name]
            result.append(self.line(name, command.admin_only, command_handler.aliases_for(name)))
        return result
