import gettext
import configparser
import os
import ast
import TeamTalk5 as teamtalk
import mpv
import getpass

class ConfigHandler:
    """
    Manages reading and writing the bot's configuration file (config.ini).
    If the file doesn't exist, it guides the user through an interactive
    terminal setup process. This project is Linux/Docker only and has no GUI path.
    """

    def __init__(self, config_file="config.ini"):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.language = "en"
        self._ = gettext.gettext  # Initialize _ for default language
        self.CONFIG_STRUCTURE = self._get_config_structure()        
        self.read_config_file()

    def _get_config_structure(self):
        """
        Defines the entire structure of the config.ini file.
        This centralized structure makes validation and extension easy.
        The `_` calls are placeholders and will be replaced by the selected language.
        """
        return [
            # Each dict represents a single configuration key.
            # 'section' and 'key' are mandatory.
            # 'prompt' and 'help_text' are for user interaction.
            # 'type' determines the kind of input (text, int, float, bool, choice, device, password).
            # 'default' provides a fallback value.
            # 'required' ensures a value must be present.

            {'type': 'header', 'text': self._("Language Selection")},
            {'section': 'bot', 'key': 'language', 'type': 'language', 'prompt': self._("Setup Language"), 'help_text': self._("Choose the language for the bot and setup process."), 'default': 'en'},

            {'type': 'header', 'text': self._("TeamTalk Server Connection")},
            {'section': 'server', 'key': 'address', 'type': 'text', 'prompt': self._("Server Address"), 'help_text': self._("The IP address or hostname of the TeamTalk server (e.g., myserver.com)."), 'required': True},
            {'section': 'server', 'key': 'tcp_port', 'type': 'int', 'prompt': self._("Server TCP Port"), 'help_text': self._("The TeamTalk TCP port."), 'default': 10333},
            {'section': 'server', 'key': 'udp_port', 'type': 'int', 'prompt': self._("Server UDP Port"), 'help_text': self._("The TeamTalk UDP port. Usually the same as TCP."), 'default': 10333},
            {'section': 'server', 'key': 'encrypted', 'type': 'bool', 'prompt': self._("Is the server encrypted?"), 'help_text': self._("Set to 'yes' if the server requires an encrypted connection."), 'default': False},
            {'section': 'server', 'key': 'username', 'type': 'text', 'prompt': self._("Bot's Username"), 'help_text': self._("The username for the bot's account on the server."), 'required': True},
            {'section': 'server', 'key': 'password', 'type': 'password', 'prompt': self._("Bot's Password"), 'help_text': self._("The password for the bot's account.")},

            {'type': 'header', 'text': self._("Bot Identity and Behavior")},
            {'section': 'bot', 'key': 'nickname', 'type': 'text', 'prompt': self._("Bot's Nickname"), 'help_text': self._("The name the bot will display in the channel."), 'required': True},
            {'section': 'bot', 'key': 'client_name', 'type': 'text', 'prompt': self._("Bot's Client Name"), 'help_text': self._("The client name shown in the user info (e.g., 'SN TalkBot v2.3')."), 'default': "SN TalkBot"},
            {'section': 'bot', 'key': 'gender', 'type': 'choice', 'prompt': self._("Bot's Gender"), 'help_text': self._("This affects the bot's default icon."), 'options': {'Male': '0', 'Female': '256', 'Neutral': '4096'}, 'default': 'Male'},
            {'section': 'bot', 'key': 'default_channel', 'type': 'text', 'prompt': self._("Default Channel"), 'help_text': self._("The full path of the channel the bot should join after login (e.g., '/chatting'). The default is the root channel (/)."), 'default': "/"},
            {'section': 'bot', 'key': 'channel_password', 'type': 'text', 'prompt': self._("Channel Password"), 'help_text': self._("The password for the default channel, if required.")},
            {'section': 'bot', 'key': 'status_message', 'type': 'text', 'prompt': self._("Status Message"), 'help_text': self._("An optional status message for the bot.")},
            {'section': 'bot', 'key': 'welcome_broadcast', 'type': 'bool', 'prompt': self._("Send Welcome Broadcast?"), 'help_text': self._("Send a public welcome message when a user logs in."), 'default': True},
            {'section': 'bot', 'key': 'random_message_interval', 'type': 'int', 'prompt': self._("Random Message Interval (minutes)"), 'help_text': self._("Interval in minutes for sending random broadcast messages from messages.txt. Set to 0 to disable."), 'default': 0},

            {'type': 'header', 'text': self._("Audio and Playback Settings")},
            {'section': 'playback', 'key': 'input_device', 'type': 'device', 'device_type': 'input', 'prompt': self._("Input Device"), 'help_text': self._("The audio device for voice transmission.")},
            {'section': 'playback', 'key': 'output_device', 'type': 'device', 'device_type': 'output', 'prompt': self._("Output Device"), 'help_text': self._("The audio device for media playback.")},
            {'section': 'playback', 'key': 'seek_step', 'type': 'int', 'prompt': self._("Seek Step (seconds)"), 'help_text': self._("Default number of seconds to seek forward/backward in media playback."), 'default': 5},
            {'section': 'playback', 'key': 'default_volume', 'type': 'int', 'prompt': self._("Default Playback Volume"), 'help_text': self._("The initial volume for media playback (0-100)."), 'default': 80},
            {'section': 'playback', 'key': 'max_volume', 'type': 'int', 'prompt': self._("Maximum Playback Volume"), 'help_text': self._("The highest volume users can set (e.g., 100)."), 'default': 100},
            {'section': 'playback', 'key': 'send_channel_messages', 'type': 'bool', 'prompt': self._("Send Playback Messages to Channel?"), 'help_text': self._("Announce playback actions (play/pause/stop/volume) in the channel."), 'default': True},
            {'section': 'playback', 'key': 'channel_messages_mode', 'type': 'choice', 'prompt': self._("If Disabled, Send Playback Messages By"), 'help_text': self._("Choose whether to send playback messages privately or stay silent when channel announcements are disabled."), 'options': {'Private messages': 'private', 'Silent': 'silent'}, 'default': 'Private messages'},
            {'section': 'playback', 'key': 'volume_fading', 'type': 'float', 'prompt': self._("Volume Fading (seconds)"), 'help_text': self._("Fade audio when seeking or changing volume. Set to 0 to disable."), 'default': 0.0},
            {'section': 'playback', 'key': 'cookiefile_path', 'type': 'text', 'prompt': self._("Cookies File Path"), 'help_text': self._("Optional path to a cookies file (e.g., cookies.txt) for yt-dlp to access private or restricted videos.")},

            {'type': 'header', 'text': self._("Moderation and Security")},
            {'section': 'bot', 'key': 'vpn_detection', 'type': 'bool', 'prompt': self._("Enable VPN/Proxy Detection?"), 'help_text': self._("Check if users are connecting via a known VPN or proxy service."), 'default': True},
            {'section': 'bot', 'key': 'prevent_noname', 'type': 'bool', 'prompt': self._("Kick 'NoName' users?"), 'help_text': self._("Automatically kick users who log in with the default 'NoName' nickname."), 'default': True},
            {'section': 'bot', 'key': 'noname_note', 'type': 'text', 'prompt': self._("Message for 'NoName' users"), 'help_text': self._("The private message sent to a user before they are kicked for having no name."), 'default': "Hello. Please set your nickname first by pressing F4 (On windows) or Options, > settings, > General, > Nickname  (On Android), then reconnect. Thank you."},
            {'section': 'bot', 'key': 'intercept_channel_messages', 'type': 'bool', 'prompt': self._("Intercept All Channel Messages?"), 'help_text': self._("Allows the bot to 'see' messages in all channels for features like word blacklisting and general bot commands, such as weather and other commands, even if it's not in that channel. Highly recommended."), 'default': True},
            {'section': 'bot', 'key': 'char_limit', 'type': 'int', 'prompt': self._("Nickname Character Limit"), 'help_text': self._("Maximum allowed characters in a user's nickname. Set to 0 to disable."), 'default': 0},
            {'section': 'bot', 'key': 'char_limit_mode', 'type': 'choice', 'prompt': self._("Action for Long Nicknames"), 'help_text': self._("What to do when a user's nickname exceeds the character limit."), 'options': {'Kick the user': '1', 'Ban the user': '2'}, 'default': 'Kick the user'},
            {'section': 'bot', 'key': 'blacklist_mode', 'type': 'choice', 'prompt': self._("Action for Blacklisted Words"), 'help_text': self._("What to do when a user uses a word from blacklist.txt in their name or messages."), 'options': {'Kick the user': '1', 'Ban the user': '2'}, 'default': 'Kick the user'},
            {'section': 'bot', 'key': 'banned_countries', 'type': 'text', 'prompt': self._("Banned Countries"), 'help_text': self._("A comma-separated list of country names to ban from the server (e.g., North Korea,Israel).")},
            {'section': 'bot', 'key': 'video_deletion_timer', 'type': 'int', 'prompt': self._("Uploaded Video Deletion Timer (minutes)"), 'help_text': self._("Time in minutes before a downloaded/uploaded video is automatically deleted from the server channel. Set to 0 to disable."), 'default': 15},

            {'type': 'header', 'text': self._("Jail System")},
            {'section': 'bot', 'key': 'jail_users', 'type': 'text', 'prompt': self._("Jailed Usernames"), 'help_text': self._("A comma-separated list of usernames to automatically confine to the jail channel upon login.")},
            {'section': 'bot', 'key': 'jail_names', 'type': 'text', 'prompt': self._("Jailed Nicknames"), 'help_text': self._("A comma-separated list of nicknames to confine to the jail channel.")},
            {'section': 'bot', 'key': 'jail_channel', 'type': 'text', 'prompt': self._("Jail Channel Path"), 'help_text': self._("The full path to the channel where jailed users will be moved."), 'default': "/jail"},
            {'section': 'bot', 'key': 'jail_timer_seconds', 'type': 'int', 'prompt': self._("Jail Flood Timer (seconds)"), 'help_text': self._("The time window in seconds to monitor a jailed user for spamming join attempts."), 'default': 10},
            {'section': 'bot', 'key': 'jail_flood_count', 'type': 'int', 'prompt': self._("Jail Flood Count"), 'help_text': self._("Number of join attempts within the timer window that will trigger a ban."), 'default': 5},

            {'type': 'header', 'text': self._("Exclusions (Immunity)")},
            {'section': 'exclusion', 'key': 'ips', 'type': 'text', 'prompt': self._("Excluded IP Addresses"), 'help_text': self._("Comma-separated list of IP addresses immune to moderation rules. The stats IP is excluded by default."), 'default': '139.144.24.23'},
            {'section': 'exclusion', 'key': 'usernames', 'type': 'text', 'prompt': self._("Excluded Usernames"), 'help_text': self._("Comma-separated list of usernames immune to moderation rules.")},
            {'section': 'exclusion', 'key': 'nicknames', 'type': 'text', 'prompt': self._("Excluded Nicknames"), 'help_text': self._("Comma-separated list of nicknames immune to moderation rules.")},

            {'type': 'header', 'text': self._("Administrator and Account Settings")},
            {'section': 'accounts', 'key': 'authorized_users', 'type': 'text', 'prompt': self._("Authorized Users"), 'help_text': self._("Comma-separated list of usernames who can use the bot's admin commands.")},
            {'section': 'accounts', 'key': 'detect_server_admins', 'type': 'bool', 'prompt': self._("Auto-authorize Server Admins?"), 'help_text': self._("Should users with the 'Administrator' user type on the server automatically get bot admin privileges?"), 'default': True},
            {'section': 'accounts', 'key': 'detection_mode', 'type': 'choice', 'prompt': self._("Account Detection Mode"), 'help_text': self._("Which type of accounts should trigger the bot's actions, such as VPN detection, welcome messages, and other actions?"), 'options': {'Guest accounts only': '1', 'All new accounts': '2', 'Accounts with a specific username': '3'}, 'default': 'Guest accounts only'},
            {'section': 'accounts', 'key': 'custom_username', 'type': 'text', 'prompt': self._("Custom Username for Detection"), 'help_text': self._("If you chose option 3 above, enter the specific username to watch for here.")},
            
            {'type': 'header', 'text': self._("Optional Integrations")},
            {'section': 'telegram', 'key': 'telegram_bot_token', 'type': 'password', 'prompt': self._("Telegram Bot Token"), 'help_text': self._("Token for your Telegram bot to enable notifications. Leave blank to disable.")},
            {'section': 'telegram', 'key': 'report_chat_id', 'type': 'text', 'prompt': self._("Telegram Report Chat ID"), 'help_text': self._("Destination chat ID for /dr direct reports. Leave blank to disable direct Telegram reports.")},
            {'section': 'weather', 'key': 'api_key', 'type': 'text', 'prompt': self._("weatherapi.com API Key"), 'help_text': self._("API key for the weather command. See the README for instructions on how to get one.")},
            {'section': 'ssh', 'key': 'hostname', 'type': 'text', 'prompt': self._("SSH Hostname"), 'help_text': self._("Hostname or IP for the SSH server for the /exec and /reboot commands. Leave blank to disable.")},
            {'section': 'ssh', 'key': 'port', 'type': 'int', 'prompt': self._("SSH Port"), 'default': 22},
            {'section': 'ssh', 'key': 'username', 'type': 'text', 'prompt': self._("SSH Username")},
            {'section': 'ssh', 'key': 'password', 'type': 'password', 'prompt': self._("SSH Password")},
            {'section': 'ssh', 'key': 'allowed_ips', 'type': 'text', 'prompt': self._("SSH Allowed IPs"), 'help_text': self._("Comma-separated list of user IP addresses allowed to use SSH commands via the bot.")},

            {'type': 'header', 'text': self._("TeamTalk License (Optional)")},
            {'section': 'teamtalk_license', 'key': 'license_name', 'type': 'text', 'prompt': self._("License Name"), 'help_text': self._("Your TeamTalk SDK license name, if you have one.")},
            {'section': 'teamtalk_license', 'key': 'license_key', 'type': 'text', 'prompt': self._("License Key"), 'help_text': self._("Your TeamTalk SDK license key.")},
        ]
                
    def _select_language_and_translate_structure(self, ask_in_terminal=True):
        """
        Sets the language and translates the prompts in CONFIG_STRUCTURE.
        The `ask_in_terminal` flag controls whether language selection is prompted in the terminal.
        """
        if ask_in_terminal:
            self.select_language()
        
        gettext.bindtextdomain("messages", "locales")
        gettext.textdomain("messages")
        try:
            translation = gettext.translation("messages", "locales", [self.language])
            self._ = translation.gettext
        except FileNotFoundError:
            self._ = gettext.gettext

        self.CONFIG_STRUCTURE = self._get_config_structure()
    
    def select_language(self):
        """Allows the user to select a language for the setup process."""
        locales_dir = "locales"
        try:
            available_langs = [d for d in os.listdir(locales_dir) if os.path.isdir(os.path.join(locales_dir, d))]
        except FileNotFoundError:
            print("Warning: 'locales' directory not found. Defaulting to English.")
            available_langs = []

        if available_langs:
            print("\nPlease choose the language for the setup process.")
            for i, lang in enumerate(available_langs):
                print(f"{i + 1}. {lang}")

            while True:
                try:
                    choice = int(input("Select language number: ")) - 1
                    if 0 <= choice < len(available_langs):
                        self.language = available_langs[choice]
                        break
                    else:
                        print("Invalid choice.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
        
        # Install the selected language for gettext
        gettext.bindtextdomain("messages", locales_dir)
        gettext.textdomain("messages")
        try:
            translation = gettext.translation("messages", locales_dir, [self.language])
            translation.install()
            self._ = translation.gettext
        except FileNotFoundError:
            print(f"Language '{self.language}' not found, defaulting to English.")
            self._ = gettext.gettext

    def read_config_file(self):
        """Read config.ini and use the terminal wizard for missing configuration."""
        if not os.path.isfile(self.config_file):
            self.select_language()
            self.create_config_file_terminal(self.CONFIG_STRUCTURE)

        self.config.read(self.config_file, encoding="utf-8")
        self._migrate_legacy_server_port()
        self._migrate_google_standard_tts()

        missing_items = self._validate_config()
        if missing_items:
            print(self._("Warning: Your config.ini is missing some settings."))
            if self.config.has_option('bot', 'language'):
                self.language = self.config.get('bot', 'language')
            self._select_language_and_translate_structure(ask_in_terminal=True)
            self._prompt_for_missing(missing_items)
            self.config.read(self.config_file, encoding="utf-8")

    def _migrate_legacy_server_port(self):
        """Migrate old single [server] port to tcp_port/udp_port without breaking existing configs."""
        if not self.config.has_section("server"):
            return
        sec = self.config["server"]
        changed = False
        legacy = sec.get("port", "10333")
        if not sec.get("tcp_port", "").strip():
            sec["tcp_port"] = legacy
            changed = True
        if not sec.get("udp_port", "").strip():
            sec["udp_port"] = legacy
            changed = True
        if changed:
            with open(self.config_file, "w", encoding="utf-8") as configfile:
                self.config.write(configfile)

    def _migrate_google_standard_tts(self):
        """Migrate pre-r3 Cloud/Microsoft defaults to Google standard gTTS once."""
        changed = False

        if not self.config.has_section("tts"):
            self.config.add_section("tts")
            changed = True
        tts = self.config["tts"]
        provider = tts.get("provider", "").strip().lower()
        if provider != "gtts":
            # r2 and older used Google Cloud keys and defaulted to Microsoft.
            # r3 intentionally makes no-key Google standard gTTS the default.
            tts["provider"] = "gtts"
            tts["mode"] = "google"
            tts.setdefault("google_lang", "th")
            tts.setdefault("google_tld", "com")
            tts.setdefault("google_slow", "False")
            tts.setdefault("google_speed", "1.0")
            for legacy_key in ("google_api_key", "google_base_url", "google_voice_name"):
                if legacy_key in tts:
                    del tts[legacy_key]
            changed = True

        if not self.config.has_section("playback"):
            self.config.add_section("playback")
            changed = True
        playback = self.config["playback"]
        if playback.get("announcement_provider", "").strip().lower() != "gtts":
            playback["announcement_provider"] = "gtts"
            playback["announcement_tts_mode"] = "google"
            playback.setdefault("announcement_google_lang", "th")
            playback.setdefault("announcement_google_tld", "com")
            playback.setdefault("announcement_google_slow", "False")
            playback.setdefault("announcement_google_speed", "1.0")
            if "announcement_google_voice" in playback:
                del playback["announcement_google_voice"]
            changed = True

        if changed:
            with open(self.config_file, "w", encoding="utf-8") as configfile:
                self.config.write(configfile)

    def _validate_config(self):
        """
        Checks the loaded config against the defined structure.
        Returns a list of missing item definitions.
        """
        missing = []
        for item in self.CONFIG_STRUCTURE:
            if 'section' not in item or 'key' not in item:
                continue
            if not self.config.has_section(item['section']) or not self.config.has_option(item['section'], item['key']):
                missing.append(item)
        return missing

    def _prompt_for_missing(self, missing_items):
        """Ask for missing values in the terminal."""
        print(self._("I'll ask you for the required values now."))
        self.create_config_file_terminal(missing_items)

    def _print_header(self, text):
        """Prints a formatted section header."""
        print(f"--- {text} ---")

    def _ask_text(self, prompt, help_text, required=False, default=None):
        """Asks for a simple text input."""
        while True:
            print(f"\n? {self._(prompt)}")
            if help_text:
                print(f"  > {self._(help_text)}")
            
            default_str = f" [Default: {default}]" if default is not None else ""
            user_input = input(f"Enter value{default_str}: ").strip()

            if user_input:
                return user_input
            if default is not None:
                return default
            if not required:
                return ""
            
            print(self._("This field is required. Please enter a value."))
    
    def _ask_password(self, prompt, help_text):
        """Asks for a password input securely."""
        print(f"\n? {self._(prompt)}")
        if help_text:
            print(f"  > {self._(help_text)}")
        return getpass.getpass("Enter value: ")

    def _ask_int(self, prompt, help_text, default=None):
        """Asks for an integer input."""
        while True:
            val_str = self._ask_text(prompt, help_text, default=str(default) if default is not None else None)
            try:
                return int(val_str)
            except ValueError:
                print(self._("Invalid input. Please enter a whole number."))

    def _ask_float(self, prompt, help_text, default=None):
        """Asks for a float input."""
        while True:
            val_str = self._ask_text(prompt, help_text, default=str(default) if default is not None else None)
            try:
                return float(val_str)
            except ValueError:
                print(self._("Invalid input. Please enter a number."))

    def _ask_bool(self, prompt, help_text, default=True):
        """Asks a yes/no question."""
        while True:
            print(f"\n? {self._(prompt)}")
            if help_text:
                print(f"  > {self._(help_text)}")

            default_str = "(Y/n)" if default else "(y/N)"
            user_input = input(f"Enter choice {default_str}: ").strip().lower()

            if user_input == 'y':
                return True
            if user_input == 'n':
                return False
            if user_input == '':
                return default
            
            print(self._("Invalid choice. Please enter 'y' or 'n'."))

    def _ask_choice(self, prompt, help_text, options, default=None):
        """Asks the user to choose from a list of options."""
        print(f"\n? {self._(prompt)}")
        if help_text:
            print(f"  > {self._(help_text)}")
        
        option_keys = list(options.keys())
        for i, key in enumerate(option_keys):
            print(f"  {i + 1}. {self._(key)}")
        
        while True:
            default_str = f" [Default: {default}]" if default is not None else ""
            choice_str = input(f"Enter choice number{default_str}: ").strip()
            
            if choice_str == '' and default is not None:
                # Find the key corresponding to the default value for display
                default_key_index = option_keys.index(default) + 1
                print(f"Selected default: {default_key_index}")
                return options[default]

            try:
                choice_idx = int(choice_str) - 1
                if 0 <= choice_idx < len(option_keys):
                    selected_key = option_keys[choice_idx]
                    return options[selected_key]
                else:
                    print(self._("Invalid choice number."))
            except ValueError:
                print(self._("Invalid input. Please enter a number."))

    def _get_devices(self, type):
        """Helper to get audio devices from TeamTalk or MPV."""
        if type == 'input':
            try:
                tt = teamtalk.TeamTalk()
                devices = tt.getSoundDevices()
                tt.closeTeamTalk()
                return [d for d in devices if d.nMaxInputChannels > 0]
            except Exception:
                return []
        elif type == 'output':
            try:
                player = mpv.MPV(vo='null', video=False)
                devices = player.audio_device_list
                player.terminate()
                return devices
            except Exception:
                return []

    def create_config_file_terminal(self, items_to_ask):
        """
        Guides the user through creating a config.ini file via a data-driven
        terminal interface. This replaces the old, hardcoded method.
        """
        if len(items_to_ask) == len(self.CONFIG_STRUCTURE):
            print(self._("Welcome to the SN TalkBot setup wizard!"))
            print(self._("I'll ask a few questions to create your configuration file."))
        
        collected_values = {}
        for item in items_to_ask:
            # The header is only useful in the full setup wizard
            if item.get('type') in ['header', 'language']:
                if item.get('type') == 'header' and len(items_to_ask) == len(self.CONFIG_STRUCTURE):
                    self._print_header(item['text'])
                continue

            section, key = item['section'], item['key']
            prompt, help_text = item['prompt'], item.get('help_text', '')
            default = item.get('default')
            item_type = item['type']

            value = None
            if item_type == 'text':
                value = self._ask_text(prompt, help_text, item.get('required', False), default)
            elif item_type == 'password':
                value = self._ask_password(prompt, help_text)
            elif item_type == 'int':
                value = self._ask_int(prompt, help_text, default)
            elif item_type == 'float':
                value = self._ask_float(prompt, help_text, default)
            elif item_type == 'bool':
                value = self._ask_bool(prompt, help_text, default)
            elif item_type == 'choice':
                value = self._ask_choice(prompt, help_text, item['options'], default)
            elif item_type == 'device':
                devices = self._get_devices(item['device_type'])
                if not devices:
                    print(self._("Could not find any {type} devices. You may need to set this manually in config.ini.").format(type=item['device_type']))
                    value = -1 # Default to an invalid ID
                else:
                    if item['device_type'] == 'input':
                        options = {teamtalk.ttstr(d.szDeviceName): d.nDeviceID for d in devices}
                    else: # output
                        options = {d['description']: i for i, d in enumerate(devices)}
                    
                    value = self._ask_choice(self._("Select {type} Device").format(type=item['device_type'].title()), "", options)

            # Store the collected value
            if (section, key) not in collected_values:
                collected_values[(section, key)] = value

        self._write_config(collected_values)

    def _write_config(self, values):
        """Merge collected values into the active config and write UTF-8 safely."""
        # Do not rebuild the file from scratch when only a few keys are missing.
        # Keeping the existing parser prevents unrelated settings from being lost.
        target = self.config
        for (section, key), value in values.items():
            if not target.has_section(section):
                target.add_section(section)
            target.set(section, key, str(value))

        with open(self.config_file, "w", encoding="utf-8") as configfile:
            target.write(configfile)
            print(self._("\nConfiguration saved to config.ini! You can now start the bot normally."))

        self.config = target

    # These methods safely retrieve values from the loaded config file.


    @staticmethod
    def _csv(value):
        return [part.strip() for part in (value or "").split(",") if part.strip()]

    def _ensure_section(self, section):
        if not self.config.has_section(section):
            self.config.add_section(section)
        return self.config[section]

    def _save(self):
        with open(self.config_file, "w", encoding="utf-8") as configfile:
            self.config.write(configfile)

    def _update_section(self, section, values):
        target = self._ensure_section(section)
        for key, value in values.items():
            if value is None:
                value = ""
            elif isinstance(value, (list, tuple, set)):
                value = ",".join(str(x) for x in value)
            target[str(key)] = str(value)
        self._save()

    def get_features_config(self):
        sec = self._ensure_section("features")
        return {
            "player_enabled": sec.getboolean("player_enabled", True),
            "server_management_enabled": sec.getboolean("server_management_enabled", True),
        }

    def get_server_config(self):
        sec = self._ensure_section("server")
        legacy_port = sec.getint("port", 10333)
        tcp_port = sec.getint("tcp_port", legacy_port)
        udp_port = sec.getint("udp_port", legacy_port)
        return {
            "address": sec.get("address", ""),
            "port": tcp_port,  # compatibility for older call sites
            "tcp_port": tcp_port,
            "udp_port": udp_port,
            "encrypted": sec.getboolean("encrypted", False),
            "username": sec.get("username", ""),
            "password": sec.get("password", ""),
        }

    def get_bot_config(self):
        sec = self._ensure_section("bot")
        return {
            "nickname": sec.get("nickname", "SN TalkBot"),
            "client_name": sec.get("client_name", "SN TalkBot"),
            "gender": sec.getint("gender", 0),
            "language": sec.get("language", "th"),
            "default_channel": sec.get("default_channel", "/"),
            "channel_password": sec.get("channel_password", ""),
            "status_message": sec.get("status_message", ""),
            "welcome_broadcast": sec.getboolean("welcome_broadcast", True),
            "vpn_detection": sec.getboolean("vpn_detection", False),
            "prevent_noname": sec.getboolean("prevent_noname", False),
            "noname_note": sec.get("noname_note", "Please set your nickname, then reconnect."),
            "intercept_channel_messages": sec.getboolean("intercept_channel_messages", True),
            "jail_users": self._csv(sec.get("jail_users", "")),
            "jail_names": self._csv(sec.get("jail_names", "")),
            "jail_channel": sec.get("jail_channel", "/jail/"),
            "jail_timer_seconds": sec.getint("jail_timer_seconds", 10),
            "jail_flood_count": sec.getint("jail_flood_count", 5),
            "random_message_interval": sec.getint("random_message_interval", 0),
            "char_limit": sec.getint("char_limit", 0),
            "char_limit_mode": sec.getint("char_limit_mode", 1),
            "blacklist_mode": sec.getint("blacklist_mode", 1),
            "video_deletion_timer": sec.getint("video_deletion_timer", 15),
            "banned_countries": self._csv(sec.get("banned_countries", "")),
            "profanity_filter_enabled": sec.getboolean("profanity_filter_enabled", False),
            "tts_enabled": sec.getboolean("tts_enabled", True),
            "welcome_mode": sec.getint("welcome_mode", 0),
            "welcome_msg": sec.get("welcome_msg", "ยินดีต้อนรับคุณ ชื่อ เข้าสู่ห้องครับ"),
            "is_locked": sec.getboolean("is_locked", False),
            "blocked_commands": self._csv(sec.get("blocked_commands", "")),
            "reconnection_attempts": sec.getint("reconnection_attempts", -1),
            "reconnection_timeout": max(1, sec.getint("reconnection_timeout", 10)),
        }

    def get_playback_config(self):
        sec = self._ensure_section("playback")
        output_raw = sec.get("output_device", "auto")
        try:
            output_device = int(output_raw)
        except (TypeError, ValueError):
            output_device = output_raw or "auto"
        input_raw = sec.get("input_device", "auto")
        try:
            input_device = int(input_raw)
        except (TypeError, ValueError):
            input_device = input_raw or "auto"
        return {
            "input_device": input_device,
            "output_device": output_device,
            "seek_step": sec.getint("seek_step", 5),
            "default_volume": sec.getint("default_volume", 80),
            "max_volume": sec.getint("max_volume", 150),
            "send_channel_messages": sec.getboolean("send_channel_messages", True),
            "channel_messages_mode": sec.get("channel_messages_mode", "private"),
            "volume_fading": sec.getfloat("volume_fading", 0.0),
            "cookiefile_path": sec.get("cookiefile_path", "") or None,
            "audio_quality": sec.get("audio_quality", "High"),
            "audio_buffer": sec.get("audio_buffer", "0.5"),
            "is_stereo_wide": sec.getboolean("is_stereo_wide", False),
            "is_stereo_echo": sec.getboolean("is_stereo_echo", False),
            "is_bass_boosted": sec.getboolean("is_bass_boosted", False),
            "speed": sec.getfloat("speed", 1.0),
            "fade_enabled": sec.getboolean("fade_enabled", True),
            "queue_mode": sec.getboolean("queue_mode", False),
            "play_mode": sec.getint("play_mode", 2),
            "autoplay_enabled": sec.getboolean("autoplay_enabled", True),
            "announce_tracks": sec.getboolean("announce_tracks", True),
            "announce_queue": sec.getboolean("announce_queue", True),
            "announcement_tts_mode": sec.get("announcement_tts_mode", "google"),
            # announcement_voice remains as a backward-compatible alias for old configs.
            "announcement_voice": sec.get("announcement_voice", "th-TH-PremwadeeNeural"),
            "announcement_microsoft_voice": sec.get("announcement_microsoft_voice", sec.get("announcement_voice", "th-TH-PremwadeeNeural")),
            "announcement_google_lang": sec.get("announcement_google_lang", "th"),
            "announcement_google_tld": sec.get("announcement_google_tld", "com"),
            "announcement_google_slow": sec.getboolean("announcement_google_slow", False),
            "announcement_rate": sec.getint("announcement_rate", 0),
            "announcement_google_speed": sec.getfloat("announcement_google_speed", 1.0),
            "announcement_volume": sec.getfloat("announcement_volume", 1.0),
        }

    def get_ytdlp_config(self):
        sec = self._ensure_section("ytdlp")
        return {
            "format": sec.get("format", "bestaudio/best"),
            "timeout": sec.getint("timeout", 20),
            "retries": sec.getint("retries", 5),
            "fragment_retries": sec.getint("fragment_retries", 5),
            "concurrent_fragment_downloads": sec.getint("concurrent_fragment_downloads", 4),
            "impersonate": sec.get("impersonate", ""),
        }

    def save_playback_config(self, playback_config):
        self._update_section("playback", playback_config)

    def update_playback_settings(self, updates):
        self._update_section("playback", updates)

    def save_bot_config(self, bot_config):
        self._update_section("bot", bot_config)

    def update_bot_settings(self, updates):
        self._update_section("bot", updates)

    def get_telegram_config(self):
        # Environment variables are intentionally supported so Docker/helper deployments
        # can keep secrets out of GitHub, Docker images, and per-instance config files.
        token = os.getenv("SNTALKBOT_TELEGRAM_BOT_TOKEN") or self.config.get("telegram", "telegram_bot_token", fallback="")
        report_chat_id = os.getenv("SNTALKBOT_TELEGRAM_REPORT_CHAT_ID") or self.config.get("telegram", "report_chat_id", fallback="")
        return {
            "telegram_bot_token": str(token or "").strip(),
            "report_chat_id": str(report_chat_id or "").strip(),
        }

    def get_exclusion_config(self):
        return {
            "ips": self._csv(self.config.get("exclusion", "ips", fallback="")),
            "usernames": self._csv(self.config.get("exclusion", "usernames", fallback="")),
            "nicknames": self._csv(self.config.get("exclusion", "nicknames", fallback="")),
        }

    def get_accounts_config(self):
        return {
            "detection_mode": self.config.getint("accounts", "detection_mode", fallback=1),
            "custom_username": self.config.get("accounts", "custom_username", fallback=""),
            "authorized_users": self._csv(self.config.get("accounts", "authorized_users", fallback="")),
            "detect_server_admins": self.config.getboolean("accounts", "detect_server_admins", fallback=True),
        }

    def get_account_request_config(self):
        if not self.config.has_section("account_requests"):
            return {"enabled": False}
        sec = self.config["account_requests"]
        int_keys = {"smtp_port": 587, "smtp_timeout": 15, "otp_expiry_seconds": 600, "max_attempts": 3}
        bool_keys = {"enabled": False, "smtp_use_tls": True, "smtp_use_ssl": False, "smtp_tls_verify": True}
        result = {k: v for k, v in sec.items()}
        for key, default in int_keys.items():
            result[key] = sec.getint(key, default)
        for key, default in bool_keys.items():
            result[key] = sec.getboolean(key, default)
        return result

    def save_account_request_config(self, values):
        self._update_section("account_requests", values)

    def get_weather_config(self):
        return self.config.get("weather", "api_key", fallback="")

    def get_groq_config(self):
        return {
            "api_key": self.config.get("groq", "api_key", fallback=""),
            "model": self.config.get("groq", "model", fallback="llama-3.1-8b-instant"),
            "base_url": self.config.get("groq", "base_url", fallback="https://api.groq.com/openai/v1"),
        }

    def get_tts_config(self):
        if not self.config.has_section("tts"):
            return {"mode": "google", "google_lang": "th", "google_tld": "com", "google_slow": False, "google_speed": 1.0, "random_broadcast_enabled": False}
        sec = self.config["tts"]
        result = {k: v for k, v in sec.items()}
        result["mode"] = sec.get("mode", "google")
        result["google_lang"] = sec.get("google_lang", "th")
        result["google_tld"] = sec.get("google_tld", "com")
        result["google_slow"] = sec.getboolean("google_slow", False)
        result["google_speed"] = sec.getfloat("google_speed", 1.0)
        result["random_broadcast_enabled"] = sec.getboolean("random_broadcast_enabled", False)
        return result

    def save_tts_config(self, values):
        self._update_section("tts", values)

    def get_ssh_config(self):
        return {
            "hostname": self.config.get("ssh", "hostname", fallback=""),
            "port": self.config.getint("ssh", "port", fallback=22),
            "username": self.config.get("ssh", "username", fallback=""),
            "password": self.config.get("ssh", "password", fallback=""),
            "allowed_ips": self._csv(self.config.get("ssh", "allowed_ips", fallback="")),
        }

    def get_teamtalk_license_config(self):
        return {
            "license_name": self.config.get("teamtalk_license", "license_name", fallback=""),
            "license_key": self.config.get("teamtalk_license", "license_key", fallback=""),
        }
