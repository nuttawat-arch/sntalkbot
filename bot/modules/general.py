from TeamTalk5 import ttstr, UserType
import wikipedia
import langdetect
import requests
from pathlib import Path
from datetime import datetime, timezone
import os
import time
from bot.utils import BotUtils as utils



class _NullContext:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False

DEVELOPER_REPORT_BASE_URL = "https://report.nuttawat.ddnsfree.com"
DEVELOPER_REPORT_ENDPOINT = DEVELOPER_REPORT_BASE_URL.rstrip("/") + "/api/report"
DEVELOPER_NAME = "nuttawat"
DEVELOPER_ORGANIZATION = "SN Family"
DEVELOPER_EMAIL = "nutblind2545t@gmail.com"
DEVELOPER_PHONE = "0637457797"

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
        command_handler.register_command('status', self.handle_status_command)
        command_handler.register_command('channelinput', self.handle_channel_input_command, admin_only=True)
        if self.bot.server_management_enabled:
            command_handler.register_command('weather', self.handle_weather_command)
            command_handler.register_command('events', self.handle_events_command, admin_only=True)
            command_handler.register_command('report', self.handle_report_command)
            command_handler.register_command('intercept', self.handle_intercept_command, admin_only=True)

    @staticmethod
    def _format_uptime(seconds):
        seconds = max(0, int(seconds or 0))
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _secs = divmod(rem, 60)
        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _sender_is_admin(self, textmessage):
        username = utils.ensure_text(ttstr(getattr(textmessage, "szFromUsername", "")))
        if self.bot.is_authorized_user(username):
            return True
        try:
            user = self.bot.getUser(textmessage.nFromUserID)
        except Exception:
            user = None
        return bool(user and user.uUserType == UserType.USERTYPE_ADMIN)

    def handle_status_command(self, textmessage, *args):
        """One screen-reader-friendly dashboard whose content follows the active bot role."""
        sender_id = textmessage.nFromUserID
        role = "Full Bot" if self.bot.player_enabled and self.bot.server_management_enabled else (
            "Player Bot" if self.bot.player_enabled else "Server Manager Bot"
        )
        uptime = self._format_uptime(time.time() - float(getattr(self.bot, "started_at", time.time())))
        try:
            users = [u for u in self.bot.getServerUsers() if int(getattr(u, "nUserID", 0) or 0) != int(self.bot.getMyUserID() or 0)]
        except Exception:
            users = []
        channel_id = int(self.bot.getMyChannelID() or 0)
        channel_name = str(channel_id or "-")
        try:
            channel = self.bot.getChannel(channel_id)
            if channel:
                channel_name = utils.ensure_text(ttstr(getattr(channel, "szName", ""))) or channel_name
        except Exception:
            pass

        self.bot.privateMessage(sender_id, self._("{role} | uptime {uptime} | channel {channel} | users {users}").format(
            role=role, uptime=uptime, channel=channel_name, users=len(users)
        ))

        state_counts = self.bot.runtime_state_counts() if hasattr(self.bot, "runtime_state_counts") else {}
        self.bot.privateMessage(sender_id, self._("TeamTalk activity | speaking {voice} | media {media} | video {video} | desktop {desktop}").format(
            voice=state_counts.get("voice", 0), media=state_counts.get("media", 0),
            video=state_counts.get("video", 0), desktop=state_counts.get("desktop", 0),
        ))

        if self.bot.player_enabled and self.bot.player is not None:
            player = self.bot.player
            title = str(getattr(player, "media_title", "") or "-") if getattr(player, "is_playing", False) else self._("idle")
            with getattr(player, "queue_lock", _NullContext()):
                queue_count = len(getattr(player, "queue", []) or [])
            queue_mode = "ON" if getattr(player, "queue_mode", False) else "OFF"
            autoplay = "ON" if bool(self.bot.playback_config.get("autoplay_enabled", True)) else "OFF"
            mode = f"M{int(getattr(player, 'play_mode', 2) or 2)}"
            if getattr(player, "cookiefile", None) and os.path.isfile(player.cookiefile):
                cookie_state = self._("persistent/custom")
            elif getattr(player, "bundled_cookiefile", None) and os.path.isfile(player.bundled_cookiefile):
                cookie_state = self._("bundled default")
            else:
                cookie_state = self._("none")
            self.bot.privateMessage(sender_id, self._("Player | {title} | queue {queue} | q {queue_mode} | {mode} | autoplay {autoplay} | cookies {cookies}").format(
                title=title, queue=queue_count, queue_mode=queue_mode, mode=mode, autoplay=autoplay, cookies=cookie_state
            ))

        if self.bot.server_management_enabled and self._sender_is_admin(textmessage):
            self.bot.privateMessage(sender_id, self._("Manager | filter {filter_state} | ci {ci_state} | ic {ic_state} | commands {lock_state} | welcome {welcome_state}").format(
                filter_state="ON" if self.bot.profanity_filter_enabled else "OFF",
                ci_state="ON" if self.bot.bot_config.get("channel_input_enabled", True) else "OFF",
                ic_state="ON" if self.bot.bot_config.get("intercept_channel_messages", True) else "OFF",
                lock_state=self._("locked") if self.bot.commands_locked else self._("open"),
                welcome_state="ON" if self.bot.welcome_mode > 0 else "OFF",
            ))

    def handle_events_command(self, textmessage, *args):
        """Show recent real TeamTalk/admin events kept in a bounded in-memory ring."""
        limit = 10
        if args:
            try:
                limit = int(args[0])
            except (TypeError, ValueError):
                self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: events [1-25]"))
                return
        limit = max(1, min(limit, 25))
        items = self.bot.activity.recent(limit) if hasattr(self.bot, "activity") else []
        if not items:
            self.bot.privateMessage(textmessage.nFromUserID, self._("No recent runtime events."))
            return
        self.bot.privateMessage(textmessage.nFromUserID, self._("Recent events (newest first):"))
        for item in reversed(items):
            age = self.bot.activity.format_age(item.get("timestamp", time.time()))
            self.bot.privateMessage(
                textmessage.nFromUserID,
                f"{age} | {item.get('category','event')}/{item.get('action','update')} | {item.get('message','')}"
            )

    def handle_channel_input_command(self, textmessage, *args):
        """Enable/disable normal channel features while moderation remains active."""
        current = bool(self.bot.bot_config.get("channel_input_enabled", True))
        if not args:
            enabled = not current
        else:
            value = str(args[0]).strip().lower()
            if value == "status":
                state = self._("enabled") if current else self._("disabled")
                self.bot.privateMessage(
                    textmessage.nFromUserID,
                    self._("Channel input is currently {state}. Moderation still runs for channel text the bot receives.").format(state=state),
                )
                return
            if value not in ("on", "off"):
                self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: channelinput on|off|status (short alias: ci)"))
                return
            enabled = value == "on"

        self.bot.bot_config["channel_input_enabled"] = enabled
        self.bot.config_handler.update_bot_settings({"channel_input_enabled": enabled})
        state = self._("enabled") if enabled else self._("disabled")
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Channel input is now {state}. Moderation still runs for channel text the bot receives.").format(state=state),
        )

    def handle_intercept_command(self, textmessage, *args):
        """Toggle server-wide channel interception for Manager/Full moderation."""
        current = bool(self.bot.bot_config.get("intercept_channel_messages", True))
        if not args:
            enabled = not current
        else:
            value = str(args[0]).strip().lower()
            if value == "status":
                state = self._("enabled") if current else self._("disabled")
                self.bot.privateMessage(
                    textmessage.nFromUserID,
                    self._("All-channel interception is currently {state}.").format(state=state),
                )
                return
            if value not in ("on", "off"):
                self.bot.privateMessage(
                    textmessage.nFromUserID,
                    self._("Usage: intercept on|off|status (short alias: ic)"),
                )
                return
            enabled = value == "on"

        self.bot.set_intercept_channel_messages(enabled)
        state = self._("enabled") if enabled else self._("disabled")
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("All-channel interception is now {state}.").format(state=state),
        )

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
            user = self.bot.getUser(lookup_user_id)
            sender_channel_id = int(getattr(user, "nChannelID", 0) or 0) if user else 0
            if msg_type == 1: # Private message
                self.bot.privateMessage(lookup_user_id, weather_info)
            elif sender_channel_id:
                self.bot.send_message(weather_info, sender_channel_id)
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
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: search <query>"))
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
            requested = str(command_name).lstrip("/").lower()
            name = self.bot.command_handler.resolve_name(requested)
            if name not in self.bot.command_handler.commands:
                self.bot.privateMessage(sender_id, self._("Unknown command. Use help to see all commands."))
                return
            command = self.bot.command_handler.commands[name]
            self.bot.privateMessage(
                sender_id,
                self.bot.help_commands.line(name, command.admin_only, self.bot.command_handler.aliases_for(name)),
            )
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
            self.bot.privateMessage(sender_id, self._("Usage: report <your message>"))
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
            self.bot.privateMessage(sender_id, self._("Usage: dr <your message>"))
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
        sender_id = textmessage.nFromUserID
        role = "Full Bot" if self.bot.player_enabled and self.bot.server_management_enabled else (
            "Player Bot" if self.bot.player_enabled else "Server Manager Bot" if self.bot.server_management_enabled else "SN TalkBot"
        )
        runtime = "yt-dlp + MPV + TeamTalk" if self.bot.player_enabled else "TeamTalk Server Manager"
        self.bot.privateMessage(sender_id, f"SN TalkBot {_project_version()} | {role} | Python {platform.python_version()} | Linux/Docker ready | {runtime}")
        self.bot.privateMessage(sender_id, self._("Developer: {name} from {organization}").format(name=DEVELOPER_NAME, organization=DEVELOPER_ORGANIZATION))
        self.bot.privateMessage(sender_id, self._("Contact email: {email}").format(email=DEVELOPER_EMAIL))
        self.bot.privateMessage(sender_id, self._("Contact phone: {phone}").format(phone=DEVELOPER_PHONE))
        self.bot.privateMessage(sender_id, self._("Report a bug, request a feature, or send a suggestion: dr <your message>"))

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
