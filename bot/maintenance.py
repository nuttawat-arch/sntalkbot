"""Daily media cache maintenance. Queue/favorites tables are never touched."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import logging
import os
import threading
import time


def validate_schedule(clock, timezone):
    import re
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
        raise ValueError("เวลาใช้รูปแบบ HH:MM เช่น 00:00")
    ZoneInfo(timezone)
    return clock, timezone


class CacheMaintenance:
    def __init__(self, bot):
        self.bot = bot
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.sound_player = None
        self._last_error = None

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True, name="CacheMaintenance")
        self.thread.start()

    def _loop(self):
        while not self.stop.wait(15):
            try:
                self.tick()
                self._last_error = None
            except Exception as exc:
                # Invalid hand-edited config must not flood logs every 15s.
                if str(exc) != self._last_error:
                    logging.exception("Cache maintenance failed")
                    self._last_error = str(exc)

    def tick(self, now=None):
        cfg = self.bot.player.playback_config
        if not cfg.get("cache_cleanup_enabled", True):
            return False
        clock, tz = validate_schedule(cfg.get("cache_cleanup_time", "00:00"), cfg.get("cache_cleanup_timezone", "Asia/Bangkok"))
        local = (now or datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz))
        if local.strftime("%H:%M") < clock:
            return False
        day = local.date().isoformat()
        # Catch up once after downtime, persisted across process restarts.
        if self.bot.state_store.get_meta("cache_cleanup_day") == day:
            return False
        return self.run(day=day)

    def run(self, *, day=None):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            # Clear extraction caches first; a queued/in-flight prefetch cannot
            # repopulate them until Player.clear_cache releases its lock.
            prefetched, temporary = self.bot.player.clear_cache()
            if self.stop.is_set():
                return False
            stamp = datetime.now().astimezone().isoformat()
            self.bot.state_store.set_meta("cache_cleanup_result", json.dumps({
                "at": stamp, "prefetched": prefetched, "temporary": temporary,
                "playlist_preserved": True,
            }))
            if day:
                self.bot.state_store.set_meta("cache_cleanup_day", day)
            self._play_sound()
            return True
        finally:
            self.lock.release()

    def _play_sound(self):
        value = self.bot.player.playback_config.get("cache_cleanup_sound", "sounds/cache-cleanup.mp3")
        if not value:
            return
        # Never accept URLs or a path outside this instance's data directory.
        base = Path(os.getenv("TTUTIL_DATA_DIR", ".")).resolve()
        path = (base / value).resolve()
        if base not in path.parents or not path.is_file():
            logging.info("Cache cleanup complete; optional sound missing: %s", path.name)
            return
        import mpv
        voice_was_active = False
        enabled_voice = False
        try:
            cog = getattr(self.bot, "player_cog", None)
            voice_was_active = bool(cog and cog._teamtalk_voice_tx_active())
            opts = {"vo": "null", "video": False, "ytdl": False, "keep_open": False}
            ao = os.getenv("TTUTIL_MPV_AO", "").strip()
            if ao:
                opts["ao"] = ao
            sound = self.sound_player = mpv.MPV(**opts)
            output = getattr(self.bot.player, "audio_device", None)
            if output and output != "auto":
                sound.audio_device = output
            sound.volume = self.bot.player.playback_config.get("default_volume", 80)
            self.bot.enableVoiceTransmission(True)
            enabled_voice = True
            sound.play(str(path))
            # Bound malformed/looping sounds and shutdown latency. Allow startup
            # grace because idle-active may initially still describe the old state.
            started = time.monotonic()
            while not self.stop.wait(0.1) and time.monotonic() - started < 60:
                if time.monotonic() - started > 1 and sound.idle_active:
                    break
        except Exception:
            logging.exception("Cache cleared but notification sound could not play")
        finally:
            if self.sound_player:
                try:
                    self.sound_player.terminate()
                except Exception:
                    pass
                self.sound_player = None
            # Preserve live music and an already active voice transmission.
            if enabled_voice and not voice_was_active and not self.bot.player.transport_is_active():
                self.bot.enableVoiceTransmission(False)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
