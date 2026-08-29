import sys
import os
import requests
import zipfile
from tqdm import tqdm
import random
import string
import logging
import traceback
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor


class ShutdownSignal(Exception):
    """Signal a clean bot shutdown from a command handler."""


class RestartSignal(Exception):
    """Signal an in-process bot restart from a command handler."""



class BotUtils:
    """
    A class for standalone utility functions used by the bot.
    """
    VERSION = "5.1.17"

    @staticmethod
    def load_blacklist(filename="blacklist.txt"):
        """Load the multilingual blacklist, independent of process cwd.

        Normal deployments run from the project root, but service wrappers, tests,
        or future launchers may use another working directory.  Keep the historical
        relative path first, then fall back to the project root beside ``bot/``.
        """
        candidates = [filename]
        if not os.path.isabs(filename):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            fallback = os.path.join(project_root, filename)
            if fallback not in candidates:
                candidates.append(fallback)
        for candidate in candidates:
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    return [line.strip().lower() for line in f if line.strip()]
            except FileNotFoundError:
                continue
        return []

    @staticmethod
    def ensure_text(value):
        """Return readable Unicode text from TeamTalk/Python values.

        TeamTalkPy uses byte strings for TTCHAR on Linux while Windows commonly
        exposes Python ``str``. Incoming fields must therefore be decoded before
        Unicode parsing. This helper is intentionally one-way: outbound TeamTalk
        calls should continue to use TeamTalk5.ttstr().
        """
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value).decode("utf-8", errors="replace")
        inner = getattr(value, "value", None)
        if inner is not None and inner is not value and isinstance(inner, (str, bytes, bytearray, memoryview)):
            return BotUtils.ensure_text(inner)
        return str(value)

    @staticmethod
    def parse_channel_reference(value):
        """Classify a TeamTalk channel reference as an ID or a path.

        Legacy TTMediaBot stored ``teamtalk.channel`` as either an integer ID
        or a channel path.  SNTalkBot stores config.ini values as text, so a
        migrated integer arrives at runtime as ``"8"``.  Accept that textual
        form (and an explicitly quoted ``'8'``/``"8"`` pasted from a UI) as the
        same channel ID without rewriting the persisted configuration.  All
        non-numeric values keep the historical path behavior unchanged.
        """
        if isinstance(value, bool):
            # bool is a subclass of int in Python but is never a valid channel ID.
            return "path", BotUtils.ensure_text(value).strip() or "/"
        if isinstance(value, int):
            return ("id", int(value)) if int(value) > 0 else ("path", str(value))

        text = BotUtils.ensure_text(value).strip()
        if not text:
            return "path", "/"

        numeric = text
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            candidate = text[1:-1].strip()
            if candidate.isdecimal():
                numeric = candidate
        if numeric.isdecimal():
            channel_id = int(numeric)
            if channel_id > 0:
                return "id", channel_id
        return "path", text

    @staticmethod
    def normalize_moderation_text(value):
        text = unicodedata.normalize("NFKC", BotUtils.ensure_text(value)).lower()
        return "".join(ch for ch in text if unicodedata.category(ch) not in {"Cf", "Cc"}).strip()

    @staticmethod
    def contains_profanity(message_text, bad_words):
        """Match a multilingual moderation list without common false positives.

        Thai entries support joined/spaced obfuscation (for example ``ค ว ย``)
        because Thai normally has no spaces between words. Very short Thai terms
        are token-only so ``หี`` does not match ``หีบ``. Non-Thai entries use
        Unicode word boundaries, preventing short English entries such as ``ass``
        from matching innocent words such as ``class`` or ``password``.
        """
        normalized = BotUtils.normalize_moderation_text(message_text)
        if not normalized:
            return False
        token_pattern = r"""[\s,.;:!?/\\|()\[\]{}<>"'`~@#$%^&*+=_-]+"""
        thai_tokens = [token for token in re.split(token_pattern, normalized) if token]
        compact_thai_text = re.sub(r"[^\w\u0E00-\u0E7F]+", "", normalized, flags=re.UNICODE)
        for word in bad_words or []:
            bad = BotUtils.normalize_moderation_text(word)
            if not bad:
                continue
            has_thai = bool(re.search(r"[\u0E00-\u0E7F]", bad))
            if has_thai:
                compact_bad = re.sub(r"[^\w\u0E00-\u0E7F]+", "", bad, flags=re.UNICODE)
                if not compact_bad:
                    continue
                if len(compact_bad) <= 2:
                    if bad in thai_tokens:
                        return True
                elif compact_bad in compact_thai_text:
                    return True
                continue

            pieces = [re.escape(part) for part in bad.split() if part]
            if not pieces:
                continue
            phrase = r"\s+".join(pieces)
            pattern = rf"(?<!\w){phrase}(?!\w)"
            if re.search(pattern, normalized, re.IGNORECASE | re.UNICODE):
                return True
        return False

    @staticmethod
    def generate_password(length=None):
        """Generates a random password of specified length."""
        if length is None:
            length = random.randint(15, 32)
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

    @staticmethod
    def parse_duration_string(duration_str):
        """Parses a duration string like '1h:30m:10s' into seconds."""
        if not duration_str:
            raise ValueError("Duration string cannot be empty")
        duration_seconds = 0
        for part in duration_str.replace(" ", "").split(':'):
            if not part: continue
            unit = part[-1].lower()
            try:
                value = int(part[:-1])
                if unit == 's': duration_seconds += value
                elif unit == 'm': duration_seconds += value * 60
                elif unit == 'h': duration_seconds += value * 3600
                elif unit == 'd': duration_seconds += value * 86400
                elif unit == 'w': duration_seconds += value * 604800
                else: raise ValueError(f"Invalid duration unit: {unit}")
            except (ValueError, IndexError):
                raise ValueError(f"Invalid duration part: {part}")
        return duration_seconds

    @staticmethod
    def get_user_location(ip_address):
        """Fetches country and city for a given IP address."""
        if not ip_address or ip_address == "127.0.0.1":
            return "Local", "Host"
        
        base_url = f"http://ip-api.com/json/{ip_address}"
        params = {"fields": "status,message,country,city"}
        try:
            response = requests.get(base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "success":
                return data.get("country"), data.get("city")
            else:
                print(f"Error getting location for {ip_address}: {data.get('message')}")
                return None, None
        except requests.exceptions.RequestException as e:
            print(f"Error fetching location for {ip_address}: {e}")
            return None, None

    @staticmethod
    def is_vpn(ip_address):
        """Checks if an IP address is likely a VPN/proxy."""
        if not ip_address or ip_address == "127.0.0.1":
            return False
        
        base_url = f"http://ip-api.com/json/{ip_address}"
        params = {"fields": "status,message,proxy"}
        try:
            response = requests.get(base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "success":
                return data.get("proxy", False)
            return False
        except requests.exceptions.RequestException:
            return False

    @staticmethod
    def send_telegram_notification(token, chat_id, message):
        """Send a Telegram message. Returns True on success and never raises for missing config/network errors."""
        if not token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message}
        try:
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            payload = response.json() if response.content else {}
            return bool(payload.get("ok", True))
        except requests.exceptions.RequestException as e:
            # Do not print the exception URL because Telegram Bot API URLs contain the secret token.
            status = getattr(getattr(e, "response", None), "status_code", None)
            detail = f"HTTP {status}" if status else type(e).__name__
            print(f"Error sending Telegram notification: {detail}")
            return False
        except ValueError:
            print("Error sending Telegram notification: invalid JSON response")
            return False


class LoggingThreadPoolExecutor(ThreadPoolExecutor):
    """
    A ThreadPoolExecutor that automatically logs exceptions from submitted tasks.
    """
    def submit(self, fn, *args, **kwargs):
        """
        Wraps the submitted function to catch and log any exceptions.
        """
        def wrapped_fn(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                exc_info = traceback.format_exc()
                logging.error(f"Exception in thread pool for function '{fn.__name__}':\n{exc_info}")
        
        # Submit the wrapped function to the parent class's submit method
        return super().submit(wrapped_fn, *args, **kwargs)
