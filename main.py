import argparse
import configparser
import logging
from logging.handlers import RotatingFileHandler
import os
import sys

import TeamTalk5 as teamtalk
import mpv
from TeamTalk5 import ttstr

from bot.account import Account
from bot.config_handler import ConfigHandler
from bot.help import HelpCommands
from bot.sntalkbot import SNTalkBot
from bot.utils import RestartSignal, ShutdownSignal



def configure_logging(config_file):
    """Configure rotating file logging using optional [logging] config values."""
    data_dir = os.getenv("TTUTIL_DATA_DIR", ".")
    os.makedirs(data_dir, exist_ok=True)
    parser = configparser.ConfigParser()
    if config_file and os.path.isfile(config_file):
        parser.read(config_file, encoding="utf-8")
    section = parser["logging"] if parser.has_section("logging") else {}
    level_name = str(section.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    try:
        max_bytes = max(0, int(section.get("max_bytes", 5 * 1024 * 1024)))
    except (TypeError, ValueError):
        max_bytes = 5 * 1024 * 1024
    try:
        backup_count = max(0, int(section.get("backup_count", 3)))
    except (TypeError, ValueError):
        backup_count = 3
    console = str(section.get("console", "True")).strip().lower() in {"1", "true", "yes", "on"}

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    formatter = logging.Formatter("%(levelname)s [%(asctime)s] %(threadName)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        os.path.join(data_dir, "sntalkbot.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

def list_audio_devices():
    print("--- Audio Devices ---")
    try:
        tt = teamtalk.TeamTalk()
        devices = tt.getSoundDevices()
        inputs = [d for d in devices if d.nMaxInputChannels > 0]
        tt.closeTeamTalk()
        print("\nInput Devices:")
        for device in inputs:
            print(f"{device.nDeviceID}: {ttstr(device.szDeviceName)}")
        if not inputs:
            print("  No input devices found.")
    except Exception as exc:
        print(f"  Could not list TeamTalk input devices: {exc}")

    try:
        player = mpv.MPV(vo="null", video=False)
        outputs = player.audio_device_list or []
        player.terminate()
        print("\nOutput Devices:")
        for index, device in enumerate(outputs):
            print(f"{index}: {device.get('description', device.get('name', 'N/A'))}")
        if not outputs:
            print("  No output devices found.")
    except Exception as exc:
        print(f"  Could not list output devices: {exc}")


def main():
    parser = argparse.ArgumentParser(description="SN TalkBot TeamTalk bot")
    parser.add_argument("-c", "--cookiefile", help="Path to a cookies.txt file for yt-dlp.")
    parser.add_argument("-d", "--devices", action="store_true", help="List available audio devices and exit.")
    parser.add_argument("-f", "--configfile", help="Path to a custom single-bot config.ini file.")
    args = parser.parse_args()

    if args.devices:
        list_audio_devices()
        return 0
    if args.configfile and not os.path.isfile(args.configfile):
        print(f"Error: configuration file not found: {args.configfile}")
        return 1

    active_config = args.configfile or "config.ini"
    configure_logging(active_config)

    while True:
        print("Initializing SN TalkBot...")
        try:
            config = ConfigHandler(active_config)
            help_commands = HelpCommands(config)
            bot = SNTalkBot(
                config_handler=config,
                account_creator=Account(),
                help_commands=help_commands,
                cookiefile=args.cookiefile,
            )
        except Exception as exc:
            logging.exception("Failed to initialize bot")
            print(f"FATAL: failed to initialize bot: {exc}")
            return 1

        restart = False
        while True:
            try:
                bot.runEventLoop()
            except KeyboardInterrupt:
                print("\nShutting down bot...")
                bot.shutdown()
                return 0
            except ShutdownSignal:
                print("\nShutdown requested by administrator.")
                bot.shutdown()
                return 0
            except RestartSignal:
                print("\nRestart requested by administrator.")
                bot.shutdown()
                restart = True
                break
            except Exception as exc:
                logging.exception("Error in TeamTalk event loop")
                print(f"Event-loop error logged: {exc}")

        if not restart:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
