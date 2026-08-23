from TeamTalk5 import ttstr, UserType
import wikipedia
import langdetect
import requests
from pathlib import Path
from datetime import datetime, timezone
from bot.utils import BotUtils as utils

DEVELOPER_REPORT_BASE_URL = "https://report.nuttawat.ddnsfree.com"
DEVELOPER_REPORT_ENDPOINT = DEVELOPER_REPORT_BASE_URL.rstrip("/") + "/api/report"

def _project_version():
    try:
        return (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"

class GeneralCog:
    """
    A module for handling general utility commands available to all users.
    """
    def __init__(self, bot):
        self.bot = bot
        self._ = bot._

    def register(self, command_handler):
        """Register common commands plus server-only utilities for Manager/Full modes."""
        command_handler.register_command('search', self.handle_search_command)
        command_handler.register_command('help', self.handle_help_command)
        command_handler.register_command('myinfo', self.handle_myinfo_command)
        command_handler.register_command('admins', self.handle_admins_command)
        command_handler.register_command('about', self.handle_about_command)
        command_handler.register_command('dr', self.handle_direct_report_command)
        command_handler.register_command('gcid', self.handle_gcid_command)
        if self.bot.server_management_enabled:
            command_handler.register_command('weather', self.handle_weather_command)
            command_handler.register_command('report', self.handle_report_command)

    def handle_weather_command(self, textmessage, *args):
        sender_user_id = textmessage.nFromUserID
        if self.bot.user_manager is None:
            self.bot.privateMessage(sender_user_id, self._("The weather feature is unavailable in this bot mode."))
            return
        
        # Determine the user to look up
        if args:
            target_nickname = " ".join(args)
            target_user = self.bot.getUserByName(target_nickname)
            if not target_user:
                self.bot.privateMessage(sender_user_id, self._("User '{user}' not found.").format(user=target_nickname))
                return
            lookup_user_id = target_user.nUserID
        else:
            lookup_user_id = sender_user_id
        
        self.bot.io_pool.submit(self._weather_task, lookup_user_id, textmessage.nMsgType)

    def _weather_task(self, lookup_user_id, msg_type):
        """Task to get user location and weather info."""
        country, city = self.bot.user_manager.get_user_location(lookup_user_id)

        if country and city:
            weather_info = self.get_weather_from_api(country, city)
            sender_channel_id = self.bot.getUser(lookup_user_id).nChannelID
            if msg_type == 1: # Private message
                self.bot.privateMessage(lookup_user_id, weather_info)
            else:
                self.bot.send_message(weather_info, sender_channel_id or 0)
        else:
            self.bot.privateMessage(lookup_user_id, self._("Could not retrieve location information."))

    def get_weather_from_api(self, country_name, city):
        """Fetches and formats weather data from the API."""
        base_url = "https://api.weatherapi.com/v1/forecast.json"
        params = { "key": self.bot.weather_config, "q": f"{city}, {country_name}", "days": 1 }
        try:
            response = requests.get(base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            current = data["current"]
            forecast = data["forecast"]["forecastday"][0]["day"]
            current_time_str = data["location"]["localtime"]
            current_hour = int(current_time_str.split(" ")[1].split(":")[0])
            forecast_hour = data["forecast"]["forecastday"][0]["hour"][current_hour]
            
            return self._("The current weather in {city}, {country_name} is {temperature}°C, {condition}. "
                          "The perceived temperature is {feels_like} degrees C, the wind speed is at {wind_speed} kph, "
                          "The wind gusts are at {gust_kph} kph, The windchill is {windchill_c}°C.\n"
                          "The Precipitation is {precip_mm} MM, The cloudiness is of {cloudiness}%, "
                          "With a {chance_of_rain}% chance of rain.\n"
                          "The visibility is up to {visibility} km. The humidity is {humidity}%, "
                          "The current time is {time}.").format(
                city=city, country_name=country_name, temperature=current["temp_c"], condition=current["condition"]["text"],
                feels_like=current["feelslike_c"], wind_speed=current["wind_kph"], gust_kph=current["gust_kph"],
                windchill_c=forecast_hour["windchill_c"], precip_mm=current["precip_mm"], cloudiness=current["cloud"],
                chance_of_rain=forecast["daily_chance_of_rain"], visibility=current["vis_km"], humidity=current["humidity"],
                time=data["location"]["localtime"])

        except (requests.exceptions.RequestException, KeyError) as e:
            print(f"Error fetching weather data: {e}")
            return self._("Error fetching weather data.")

    def handle_search_command(self, textmessage, *args):
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: /search <query>"))
            return
        query = " ".join(args)
        self.bot.io_pool.submit(self._wikipedia_summary_task, query, textmessage.nFromUserID)

    def _wikipedia_summary_task(self, query, user_id):
        try:
            lang = langdetect.detect(query)
            wikipedia.set_lang(lang)
            summary = wikipedia.summary(query, sentences=10)
            
            for chunk in self.bot.split_long_message(summary):
                self.bot.privateMessage(user_id, chunk)
            
            page_url = wikipedia.page(query).url
            self.bot.privateMessage(user_id, self._("Wikipedia link: {page_url}").format(page_url=page_url))
        except wikipedia.exceptions.PageError:
            self.bot.privateMessage(user_id, self._("Page not found on Wikipedia."))
        except wikipedia.exceptions.DisambiguationError:
            self.bot.privateMessage(user_id, self._("Multiple pages found for '{query}'. Please be more specific.").format(query=query))
        except Exception as e:
            self.bot.privateMessage(user_id, self._("An error occurred: {e}").format(e=e))

    def _send_help(self, sender_id, command_name=None):
        if command_name:
            name = str(command_name).lstrip("/").lower()
            if name not in self.bot.command_handler.commands:
                self.bot.privateMessage(sender_id, self._("Unknown command. Use /help to see all commands."))
                return
            command = self.bot.command_handler.commands[name]
            self.bot.privateMessage(sender_id, self.bot.help_commands.line(name, command.admin_only))
            return
        self.bot.privateMessage(sender_id, self._("Available Commands:"))
        # Deliberately one TeamTalk message per command to avoid truncation.
        for line in self.bot.help_commands.registered_lines(self.bot.command_handler):
            self.bot.privateMessage(sender_id, line)

    def handle_help_command(self, textmessage, *args):
        self._send_help(textmessage.nFromUserID, args[0] if args else None)

    def handle_help_list_command(self, textmessage, *args):
        self._send_help(textmessage.nFromUserID, args[0] if args else None)

    def handle_report_command(self, textmessage, *args):
        sender_id = textmessage.nFromUserID
        if not args:
            self.bot.privateMessage(sender_id, self._("Usage: /report <your message>"))
            return
        report_msg = " ".join(args)
        sender_user = self.bot.getUser(sender_id)
        sender_nickname = ttstr(sender_user.szNickname) if sender_user else self._("Unknown")
        report_full = self._("Help Request from {nickname}: {message}").format(nickname=sender_nickname, message=report_msg)
        sent_to_any = False
        for user in self.bot.getServerUsers():
            if (self.bot.is_authorized_user(ttstr(user.szUsername)) or user.uUserType == UserType.USERTYPE_ADMIN) and user.nUserID != self.bot.getMyUserID():
                self.bot.privateMessage(user.nUserID, report_full)
                sent_to_any = True
        self.bot.privateMessage(sender_id, self._("Your message has been sent to online admins.") if sent_to_any else self._("No admins online to receive your message."))

    def handle_direct_report_command(self, textmessage, *args):
        """Send an explicit user-submitted bug report to the official developer relay."""
        sender_id = textmessage.nFromUserID
        if not args:
            self.bot.privateMessage(sender_id, self._("Usage: /dr <your message>"))
            return

        report_message = " ".join(args).strip()
        if len(report_message) > 2000:
            self.bot.privateMessage(sender_id, self._("The direct report is too long. Please keep it under 2000 characters."))
            return

        sender_user = self.bot.getUser(sender_id)
        nickname = ttstr(sender_user.szNickname) if sender_user else self._("Unknown")
        username = ttstr(textmessage.szFromUsername) or "-"
        channel_id = getattr(sender_user, "nChannelID", 0) if sender_user else 0
        channel_name = "-"
        try:
            channel = self.bot.getChannel(channel_id)
            if channel:
                channel_name = ttstr(channel.szName) or str(channel_id)
        except Exception:
            channel_name = str(channel_id or "-")

        server_address = str(self.bot.server_config.get("address", "") or "-")
        server_port = int(self.bot.server_config.get("tcp_port", 0) or 0)
        server_name = "-"
        try:
            props = self.bot.getServerProperties()
            server_name = ttstr(getattr(props, "szServerName", "")) or "-"
        except Exception:
            pass

        mode = "full" if self.bot.player_enabled and self.bot.server_management_enabled else (
            "player" if self.bot.player_enabled else "manager"
        )
        payload = {
            "product": "SNTalkBot",
            "version": _project_version(),
            "mode": mode,
            "server_name": server_name,
            "server_host": server_address,
            "server_port": server_port,
            "bot_nickname": str(self.bot.bot_config.get("nickname", "SN TalkBot") or "SN TalkBot"),
            "nickname": nickname,
            "username": username,
            "channel": channel_name,
            "channel_id": int(channel_id or 0),
            "message": report_message,
            "client_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.bot.io_pool.submit(self._send_direct_report_task, sender_id, payload)

    def _send_direct_report_task(self, sender_id, payload):
        try:
            response = requests.post(
                DEVELOPER_REPORT_ENDPOINT,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "User-Agent": f"SNTalkBot/{payload.get('version', 'unknown')}",
                    "X-SNTalkBot-Report": "1",
                },
                timeout=(5, 15),
            )
            data = {}
            try:
                data = response.json()
            except Exception:
                pass
            if response.status_code in (200, 201, 202) and bool(data.get("accepted", data.get("ok", False))):
                self.bot.privateMessage(sender_id, self._("Your report was sent directly to the SNTalkBot developer."))
            elif response.status_code == 429:
                self.bot.privateMessage(sender_id, self._("Too many reports were sent recently. Please wait a little and try again."))
            else:
                self.bot.privateMessage(sender_id, self._("The developer report service is temporarily unavailable. Please try again later."))
        except requests.exceptions.RequestException as exc:
            print(f"Developer report relay error: {exc}")
            self.bot.privateMessage(sender_id, self._("The developer report service is temporarily unavailable. Please try again later."))

    def handle_about_command(self, textmessage, *args):
        import platform
        self.bot.privateMessage(textmessage.nFromUserID, f"SN TalkBot {_project_version()} | Python {platform.python_version()} | Linux/Docker ready | yt-dlp + MPV + TeamTalk | Developer reports: {DEVELOPER_REPORT_BASE_URL}")

    def handle_gcid_command(self, textmessage, *args):
        if args:
            path = " ".join(args)
            channel_id = self.bot.getChannelIDFromPath(ttstr(path))
            self.bot.privateMessage(textmessage.nFromUserID, self._("Channel ID for {path}: {channel_id}").format(path=path, channel_id=channel_id))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Current channel ID: {channel_id}").format(channel_id=self.bot.getMyChannelID()))

    def handle_admins_command(self, textmessage, *args):
        sender_id = textmessage.nFromUserID
        admins = []
        for user in self.bot.getServerUsers():
            if (self.bot.is_authorized_user(ttstr(user.szUsername)) or user.uUserType == UserType.USERTYPE_ADMIN) and user.nUserID != self.bot.getMyUserID():
                admins.append(ttstr(user.szNickname))
        
        if admins:
            self.bot.privateMessage(sender_id, self._("Online Admins: {admins}").format(admins=", ".join(admins)))
        else:
            self.bot.privateMessage(sender_id, self._("No admins online."))

    def handle_myinfo_command(self, textmessage, *args):
        self.bot.last_command_sender_id = textmessage.nFromUserID
        self.bot.last_command_sender_username = ttstr(textmessage.szFromUsername)
        self.bot.doListUserAccounts(0, 100)
