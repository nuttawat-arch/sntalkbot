from TeamTalk5 import ttstr
import os
import asyncio
import langdetect
import random
import threading
import time
import queue
from gtts import gTTS
from gtts.lang import tts_langs
import TeamTalk5 as teamtalk
import edge_tts
import mpv
import tempfile
import subprocess



class EdgeTTSWrapper:
    """Small compatibility layer around the current edge-tts Python API."""
    def __init__(self):
        self.voice = "en-US-JennyNeural"
        self.rate = "+0%"
        self.pitch = "+0Hz"
        self.volume = "+0%"

    async def get_voices_list(self):
        voices = await edge_tts.list_voices()
        return [{
            "FriendlyName": v.get("FriendlyName") or v.get("Name") or v.get("ShortName"),
            "ShortName": v.get("ShortName") or v.get("Name"),
            "Locale": v.get("Locale") or "",
        } for v in voices]

    async def set_voice(self, voice_name):
        if voice_name:
            self.voice = voice_name

    async def set_rate(self, rate):
        try: value = max(-100, min(100, int(rate)))
        except (TypeError, ValueError): value = 0
        self.rate = f"{value:+d}%"

    async def set_pitch(self, pitch):
        try: value = max(-100, min(100, int(pitch)))
        except (TypeError, ValueError): value = 0
        self.pitch = f"{value:+d}Hz"

    async def set_volume(self, volume):
        try: value = max(0.0, min(1.0, float(volume)))
        except (TypeError, ValueError): value = 1.0
        self.volume = f"{int(round((value - 1.0) * 100)):+d}%"

    async def synthesize(self, text, filepath):
        communicate = edge_tts.Communicate(
            text, voice=self.voice, rate=self.rate, pitch=self.pitch, volume=self.volume
        )
        await communicate.save(filepath)
        return os.path.getsize(filepath) if os.path.exists(filepath) else 0


class TTSCog:
    """
    A module for handling all Text-to-Speech (TTS) related commands.
    """
    def __init__(self, bot):
        self.bot = bot
        self._ = bot._
        self.speech_engine = EdgeTTSWrapper()

        # Google mode uses gTTS (Google Translate TTS), not Google Cloud TTS.
        # It needs no API key and matches the standard Google speech path.
        self.user_speech_settings = {}
        self.speech_thread = None
        self.voice_thread = None
        self.speech_synthesis_in_progress = False

        self.broadcast_speech_lock = threading.Lock()
        self.broadcast_queue = queue.Queue()
        self.broadcast_worker = None
        self.broadcast_worker_lock = threading.Lock()

        # Serialize Player announcements so queue/track messages never overlap.
        self.player_announcement_queue = queue.Queue()
        self.player_announcement_worker = None
        self.player_announcement_worker_lock = threading.Lock()

    def announce_player(self, text):
        """Queue a short player/queue announcement for sequential playback."""
        if not text:
            return
        self.player_announcement_queue.put(str(text))
        self._ensure_player_announcement_worker()

    def _ensure_player_announcement_worker(self):
        with self.player_announcement_worker_lock:
            if self.player_announcement_worker and self.player_announcement_worker.is_alive():
                return
            self.player_announcement_worker = threading.Thread(
                target=self._player_announcement_worker_loop,
                daemon=True,
                name="SNTalkBot_PlayerAnnouncements",
            )
            self.player_announcement_worker.start()

    def _player_announcement_worker_loop(self):
        while True:
            try:
                text = self.player_announcement_queue.get(timeout=1.0)
            except queue.Empty:
                with self.player_announcement_worker_lock:
                    if self.player_announcement_queue.empty():
                        self.player_announcement_worker = None
                        return
                continue
            try:
                self._run_player_announcement(text)
            finally:
                self.player_announcement_queue.task_done()

    def get_player_tts_mode(self):
        mode = str(self.bot.playback_config.get("announcement_tts_mode", "google") or "google").strip().lower()
        return mode if mode in ("microsoft", "google") else "google"

    def player_google_ready(self):
        # gTTS needs no Cloud API key. Network availability is checked at synthesis time.
        return True

    def list_player_voices(self, user_id, lang_code=None):
        """List voices for the Player announcement engine without registering Manager TTS commands."""
        self.bot.quick_task_pool.submit(self._list_player_voices_task, user_id, lang_code)

    def _list_player_voices_task(self, user_id, lang_code=None):
        try:
            lang = (lang_code or "").strip()
            if self.get_player_tts_mode() == "google":
                languages = tts_langs()
                if lang:
                    resolved = self._resolve_google_lang(lang)
                    if not resolved:
                        self.bot.privateMessage(user_id, self._("No Google standard TTS language found for {lang}.").format(lang=lang))
                        return
                    self.bot.privateMessage(
                        user_id,
                        self._("Google standard TTS language: {name} ({code})").format(
                            name=languages.get(resolved, resolved), code=resolved
                        ),
                    )
                    return
                items = [f"{name} ({code})" for code, name in sorted(languages.items(), key=lambda item: item[1].lower())]
                for i in range(0, len(items), 8):
                    self.bot.privateMessage(user_id, "\n".join(items[i:i+8]))
                return

            voices = asyncio.run(self.speech_engine.get_voices_list())
            if lang:
                voices = [v for v in voices if str(v.get("Locale", "")).lower().startswith(lang.lower())]
            if not voices:
                self.bot.privateMessage(user_id, self._("No voices found for the specified language code."))
                return
            lines = [self._("Name: {voice_name}, ShortName: {short_name}, Locale: {locale}").format(
                voice_name=voice.get("FriendlyName", ""),
                short_name=voice.get("ShortName", ""),
                locale=voice.get("Locale", ""),
            ) for voice in voices]
            for i in range(0, len(lines), 4):
                self.bot.privateMessage(user_id, "\n".join(lines[i:i+4]))
        except Exception as exc:
            self.bot.privateMessage(user_id, self._("Error listing voices: {e}").format(e=exc))

    def _run_player_announcement(self, text):
        playback = self.bot.playback_config
        mode = self.get_player_tts_mode()
        volume_value = playback.get("announcement_volume", 1.0)
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(prefix="sntalkbot_announce_", suffix=".mp3")
            os.close(fd)

            if mode == "google":
                lang = playback.get("announcement_google_lang") or self.bot.tts_config.get("google_lang") or "th"
                tld = playback.get("announcement_google_tld") or self.bot.tts_config.get("google_tld") or "com"
                slow = self._as_bool(playback.get("announcement_google_slow", self.bot.tts_config.get("google_slow", False)))
                try:
                    speed = max(0.25, min(4.0, float(playback.get("announcement_google_speed", 1.0))))
                except (TypeError, ValueError):
                    speed = 1.0
                self._synthesize_google_standard(text, temp_path, lang=lang, tld=tld, slow=slow, speed=speed)
            else:
                voice = playback.get("announcement_microsoft_voice") or playback.get("announcement_voice") or "th-TH-PremwadeeNeural"
                rate_value = playback.get("announcement_rate", 0)
                try:
                    rate = f"{max(-100, min(100, int(rate_value))):+d}%"
                except (TypeError, ValueError):
                    rate = "+0%"
                try:
                    vol = max(0.0, min(1.0, float(volume_value)))
                except (TypeError, ValueError):
                    vol = 1.0
                volume = f"{int(round((vol - 1.0) * 100)):+d}%"
                asyncio.run(edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume).save(temp_path))

            self._play_local_announcement(temp_path)
        except Exception as exc:
            print(f"Player TTS announcement failed: {exc}")
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _play_local_announcement(self, filepath):
        """Mix a TTS announcement with music without ducking or pausing playback.

        The announcer uses its own libmpv instance and the same PulseAudio sink as
        the music player.  TeamTalk captures the sink monitor, so both streams are
        mixed by PulseAudio.  Never modify ``player.volume`` here: announcements
        must not make the song quieter, pause it, or restore/fade its volume later.
        """
        player = getattr(self.bot, "player", None)
        announcer = None
        try:
            mpv_kwargs = {"vo": "null", "video": False, "keep_open": False}
            mpv_ao = os.getenv("TTUTIL_MPV_AO", "").strip()
            if mpv_ao:
                mpv_kwargs["ao"] = mpv_ao
            announcer = mpv.MPV(**mpv_kwargs)

            # Reuse an explicitly selected output device when the Player has one.
            # This changes only the announcer stream; the music stream is untouched.
            output_device = getattr(player, "audio_device", None) if player is not None else None
            if output_device and output_device != "auto":
                announcer.audio_device = output_device

            announcer.play(filepath)
            try:
                announcer.wait_until_playing()
                announcer.wait_for_playback()
            except Exception:
                # Older libmpv builds may not expose both helpers; keep a bounded fallback.
                deadline = time.time() + 30
                while time.time() < deadline:
                    try:
                        if announcer.idle_active:
                            break
                    except Exception:
                        pass
                    time.sleep(0.05)
        finally:
            if announcer is not None:
                try:
                    announcer.terminate()
                except Exception:
                    pass

    def register(self, command_handler):
        """Registers all the TTS commands with the command handler."""
        command_handler.register_command('say', self.handle_say_command)
        command_handler.register_command('rate', self.handle_rate_command)
        command_handler.register_command('pitch', self.handle_pitch_command)
        command_handler.register_command('volume', self.handle_volume_command)
        command_handler.register_command('voice', self.handle_voice_command)
        command_handler.register_command('speed', self.handle_speed_command) # คงไว้เพราะ Google รองรับ speakingRate
        command_handler.register_command('st', self.handle_stop_speech_command, admin_only=True)
        command_handler.register_command('ld', self.handle_ld_command)
        command_handler.register_command('get_voices', self.list_voices_thread)
        command_handler.register_command('ttsmode', self.handle_ttsmode_command)
        command_handler.register_command('tts', self.handle_tts_command, admin_only=True)
        command_handler.register_command('rb', self.handle_rb_command, admin_only=True)

    def on_user_parted(self, user):
        """Cleans up TTS state when a user leaves."""
        user_id = user.nUserID
        settings_key = self._get_user_settings_key(user_id)
        if settings_key.startswith("id:") and settings_key in self.user_speech_settings:
            del self.user_speech_settings[settings_key]

    def handle_prefixed_message(self, textmessage):
        """Legacy non-slash TTS shortcuts are disabled; use /say."""
        return False

    def handle_say_command(self, textmessage, *args):
        if not self.bot.tts_enabled:
            self.bot.privateMessage(textmessage.nFromUserID, self._("TTS is currently disabled by an admin."))
            return
        user = self.bot.getUser(textmessage.nFromUserID)
        if user.nChannelID != self.bot.getMyChannelID():
            self.bot.privateMessage(textmessage.nFromUserID, self._("Sorry, You are not in the same channel"))
            return

        if self.speech_synthesis_in_progress:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Another speech synthesis is already in progress. Please wait."))
            return

        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Please provide some text to speak."))
            return
            
        text_to_speak = " ".join(args)
        self.bot.quick_task_pool.submit(self._run_async_speak, text_to_speak, textmessage.nFromUserID)

    def _run_async_speak(self, text_to_speak, user_id):
        """Wrapper to run the async _speak method using asyncio."""
        self.speech_synthesis_in_progress = True
        try:
            asyncio.run(self._speak(text_to_speak, user_id))
        finally:
            self.speech_synthesis_in_progress = False

    async def _speak(self, text_to_speak, user_id, filename="speech.mp3"):
        """Asynchronous speech synthesis logic."""
        filepath = os.path.join("files", filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            user_settings = self._get_user_settings(user_id)
            lang_detection = user_settings.get("lang_detection", False)

            if self._get_tts_mode() == "google":
                lang = user_settings.get("google_lang") or self.bot.tts_config.get("google_lang") or "th"
                if lang_detection:
                    try:
                        lang = langdetect.detect(text_to_speak)
                    except langdetect.lang_detect_exception.LangDetectException:
                        pass
                try:
                    speed = max(0.25, min(4.0, float(user_settings.get("speed", self.bot.tts_config.get("google_speed", 1.0)))))
                except (TypeError, ValueError):
                    speed = 1.0
                self._synthesize_google_standard(
                    text_to_speak,
                    filepath,
                    lang=lang,
                    tld=self.bot.tts_config.get("google_tld", "com"),
                    slow=self._as_bool(self.bot.tts_config.get("google_slow", False)),
                    speed=speed,
                )
                self._stream_file(user_id, filepath)
                return

            voice_name = user_settings.get("voice")
            rate = user_settings.get("rate", 0)
            pitch = user_settings.get("pitch", 0)
            volume = user_settings.get("volume", 1.0)

            if lang_detection:
                try:
                    detected_lang = langdetect.detect(text_to_speak)
                    voices = await self.speech_engine.get_voices_list()
                    matching_voices = [v for v in voices if v["Locale"].lower().startswith(detected_lang)]
                    if matching_voices:
                        voice_name = random.choice(matching_voices)["ShortName"]
                        self.bot.privateMessage(user_id, self._("Using voice {voice_name} for {detected_lang}").format(
                            voice_name=voice_name, detected_lang=detected_lang))
                    else:
                        self._synthesize_google_standard(text_to_speak, filepath, lang=detected_lang)
                        self._stream_file(user_id, filepath)
                        return
                except langdetect.lang_detect_exception.LangDetectException:
                    self.bot.privateMessage(user_id, self._("Language detection failed. Using default voice."))

            await self.speech_engine.set_voice(voice_name or "en-US-JennyNeural")
            await self.speech_engine.set_rate(rate)
            await self.speech_engine.set_pitch(pitch)
            await self.speech_engine.set_volume(volume)

            bytes_written = await self.speech_engine.synthesize(text_to_speak, filepath)
            if bytes_written > 0:
                self._stream_file(user_id, filepath)

        except Exception as e:
            self.bot.privateMessage(user_id, self._("Error during speech synthesis: {e}").format(e=e))

    def _stream_file(self, user_id, filepath):
        """Helper to stream the generated audio file."""
        streamer = teamtalk.VideoCodec()
        streamer.nCodec = 1
        user = self.bot.getUser(user_id)
        if user and user.nChannelID == self.bot.getMyChannelID():
            self.bot.startStreamingMediaFileToChannel(ttstr(filepath), streamer)

    def speak_random_broadcast(self, text_to_speak, filename="random_broadcast.mp3"):
        """Speak random broadcasts using Google standard gTTS or Edge TTS."""
        if self.speech_synthesis_in_progress:
            return 0
        if self._get_tts_mode() == "google":
            with self.broadcast_speech_lock:
                filepath = os.path.join("files", filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                try:
                    bytes_written = self._speak_google(text_to_speak, filepath, self.bot.getMyUserID())
                except Exception as exc:
                    print(f"Google standard TTS broadcast failed: {exc}")
                    return 0
                if bytes_written > 0:
                    self._stream_file(self.bot.getMyUserID(), filepath)
                return bytes_written

        self._run_player_announcement(text_to_speak)
        return 1

    def speak_broadcast(self, text_to_speak, filename="broadcast.mp3", voice_name=None):
        if self._get_tts_mode() != "google":
            return 0
        if self.speech_synthesis_in_progress:
            return 0
        with self.broadcast_speech_lock:
            filepath = os.path.join("files", filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            try:
                if voice_name:
                    bytes_written = self._speak_google_with_voice_name(text_to_speak, filepath, voice_name)
                else:
                    bytes_written = self._speak_google(text_to_speak, filepath, self.bot.getMyUserID())
            except Exception as exc:
                print(f"Google standard TTS broadcast failed: {exc}")
                return 0
            if bytes_written > 0:
                self._stream_file(self.bot.getMyUserID(), filepath)
            return bytes_written

    def enqueue_broadcast(self, text_to_speak, filename="broadcast.mp3", voice_name=None):
        if self._get_tts_mode() != "google":
            return
        self.broadcast_queue.put((text_to_speak, filename, voice_name))
        with self.broadcast_worker_lock:
            if not self.broadcast_worker or not self.broadcast_worker.is_alive():
                self.broadcast_worker = threading.Thread(
                    target=self._broadcast_worker_loop,
                    daemon=True,
                    name="TTBot_BroadcastQueue",
                )
                self.broadcast_worker.start()

    def _broadcast_worker_loop(self):
        while True:
            try:
                text_to_speak, filename, voice_name = self.broadcast_queue.get(timeout=2)
            except queue.Empty:
                return

            if not text_to_speak:
                self.broadcast_queue.task_done()
                continue

            with self.broadcast_speech_lock:
                filepath = os.path.join("files", filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                try:
                    if voice_name:
                        bytes_written = self._speak_google_with_voice_name(text_to_speak, filepath, voice_name)
                    else:
                        bytes_written = self._speak_google(text_to_speak, filepath, self.bot.getMyUserID())
                    if bytes_written > 0:
                        self._stream_file(self.bot.getMyUserID(), filepath)
                        self._wait_for_broadcast_finish(filepath, text_to_speak)
                except Exception as exc:
                    print(f"Google standard TTS queue failed: {exc}")

            self.broadcast_queue.task_done()

    def handle_rate_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if self._get_tts_mode() == "google":
            self.bot.privateMessage(user_id, self._("Rate is only available in Microsoft mode. For Google TTS, please use /speed"))
            return
        if not args:
            self.bot.privateMessage(user_id, self._("Invalid command. Usage: /rate <rate_value>."))
            return
        try:
            rate_value = int(args[0])
            if -100 <= rate_value <= 100:
                self._get_user_settings(user_id, create=True)["rate"] = rate_value
                self.bot.privateMessage(user_id, self._("Rate set to {rate}.").format(rate=rate_value))
            else:
                self.bot.privateMessage(user_id, self._("Invalid rate value. Rate should be between -100 and 100."))
        except ValueError:
            self.bot.privateMessage(user_id, self._("Invalid command. Usage: /rate <rate_value>."))

    def handle_pitch_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if self._get_tts_mode() == "google":
            self.bot.privateMessage(user_id, self._("Pitch is only available in Microsoft mode."))
            return
        if not args:
            self.bot.privateMessage(user_id, self._("Invalid command. Usage: /pitch <pitch_value>"))
            return
        try:
            pitch_value = int(args[0])
            if -100 <= pitch_value <= 100:
                self._get_user_settings(user_id, create=True)["pitch"] = pitch_value
                self.bot.privateMessage(user_id, self._("Pitch set to {pitch}.").format(pitch=pitch_value))
            else:
                self.bot.privateMessage(user_id, self._("Invalid pitch value. Pitch should be between -100 and 100."))
        except ValueError:
            self.bot.privateMessage(user_id, self._("Invalid command. Usage: /pitch <pitch_value>"))

    def handle_volume_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if self._get_tts_mode() == "google":
            self.bot.privateMessage(user_id, self._("Volume is only available in Microsoft mode."))
            return
        if not args:
            self.bot.privateMessage(user_id, self._("Invalid command. Usage: /volume <volume_value>"))
            return
        try:
            volume_value = float(args[0])
            if 0.1 <= volume_value <= 1.0:
                self._get_user_settings(user_id, create=True)["volume"] = volume_value
                self.bot.privateMessage(user_id, self._("Volume set to {volume}.").format(volume=volume_value))
            else:
                self.bot.privateMessage(user_id, self._("Invalid volume value. Volume should be between 0.1 and 1.0."))
        except ValueError:
            self.bot.privateMessage(user_id, self._("Invalid command. Usage: /volume <volume_value>"))

    def handle_voice_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if not args:
            if self._get_tts_mode() == "google":
                self.bot.privateMessage(user_id, self._("Invalid command. Usage: /voice <language_code>, for example /voice th."))
            else:
                self.bot.privateMessage(user_id, self._("Invalid command. Usage: /voice <voice_name>."))
            return
        value = " ".join(args).strip()
        if self._get_tts_mode() == "google":
            lang = self._resolve_google_lang(value)
            if not lang:
                self.bot.privateMessage(user_id, self._("Unknown Google standard TTS language: {lang}. Use /get_voices to list languages.").format(lang=value))
                return
            self._get_user_settings(user_id, create=True)["google_lang"] = lang
            self.bot.privateMessage(user_id, self._("Google standard TTS language set to {lang}.").format(lang=lang))
        else:
            self._get_user_settings(user_id, create=True)["voice"] = value
            self.bot.privateMessage(user_id, self._("Voice set to {voice_name}.").format(voice_name=value))

    def handle_speed_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if self._get_tts_mode() != "google":
            self.bot.privateMessage(user_id, self._("Speed is only available in Google TTS mode. For Microsoft, use /rate."))
            return
        if not args:
            self.bot.privateMessage(user_id, self._("Invalid command. Usage: /speed <value>."))
            return
        try:
            speed_value = float(args[0])
            if 0.25 <= speed_value <= 4.0:
                self._get_user_settings(user_id, create=True)["speed"] = speed_value
                self.bot.privateMessage(user_id, self._("Speed set to {value}.").format(value=speed_value))
            else:
                self.bot.privateMessage(user_id, self._("Invalid speed value. Use a number between 0.25 and 4.0."))
        except ValueError:
            self.bot.privateMessage(user_id, self._("Invalid command. Usage: /speed <value>."))

    def handle_stop_speech_command(self, textmessage, *args):
        user = self.bot.getUser(textmessage.nFromUserID)
        if user.nChannelID != self.bot.getMyChannelID():
            self.bot.privateMessage(textmessage.nFromUserID, self._("Sorry, You are not in the same channel"))
            return
        self.bot.stopStreamingMediaFileToChannel()

    def handle_tts_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if not args:
            state = self._("enabled") if self.bot.tts_enabled else self._("disabled")
            self.bot.privateMessage(user_id, self._("TTS is currently {state}.").format(state=state))
            return
        value = args[0].strip().lower()
        if value not in ("on", "off"):
            self.bot.privateMessage(user_id, self._("Invalid value. Use /tts on or /tts off."))
            return
        self.bot.tts_enabled = value == "on"
        self.bot.config_handler.update_bot_settings({"tts_enabled": self.bot.tts_enabled})
        state = self._("enabled") if self.bot.tts_enabled else self._("disabled")
        self.bot.privateMessage(user_id, self._("TTS has been {state}.").format(state=state))

    def handle_rb_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if not args:
            state = self._("enabled") if self.bot.tts_config.get("random_broadcast_enabled", False) else self._("disabled")
            self.bot.privateMessage(user_id, self._("Random broadcasts are currently {state}.").format(state=state))
            return
        value = args[0].strip().lower()
        if value not in ("on", "off"):
            self.bot.privateMessage(user_id, self._("Invalid value. Use /rb on or /rb off."))
            return
        enabled = value == "on"
        self.bot.tts_config["random_broadcast_enabled"] = enabled
        self.bot.config_handler.save_tts_config(self.bot.tts_config)
        state = self._("enabled") if enabled else self._("disabled")
        self.bot.privateMessage(user_id, self._("Random broadcasts have been {state}.").format(state=state))

    def handle_ld_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        current_setting = self._get_user_settings(user_id).get("lang_detection", False)
        self._get_user_settings(user_id, create=True)["lang_detection"] = not current_setting
        
        if not current_setting:
            self.bot.privateMessage(user_id, self._("Language detection is now ON."))
        else:
            self.bot.privateMessage(user_id, self._("Language detection is now OFF."))

    def list_voices_thread(self, textmessage, *args):
        """Runs the async voice listing in the bot's thread pool."""
        self.bot.quick_task_pool.submit(self._run_async_list_voices, textmessage, *args)

    def _run_async_list_voices(self, textmessage, *args):
        """Wrapper to run the async _list_voices method."""
        asyncio.run(self._list_voices(textmessage, *args))

    async def _list_voices(self, textmessage, *args):
        """List Microsoft voices or Google standard gTTS languages."""
        user_id = textmessage.nFromUserID
        try:
            if self._get_tts_mode() == "google":
                languages = tts_langs()
                lang_code = args[0].strip() if args else None
                if lang_code:
                    resolved = self._resolve_google_lang(lang_code)
                    if not resolved:
                        self.bot.privateMessage(user_id, self._("No Google standard TTS language found for {lang}.").format(lang=lang_code))
                        return
                    self.bot.privateMessage(
                        user_id,
                        self._("Google standard TTS language: {name} ({code})").format(
                            name=languages.get(resolved, resolved), code=resolved
                        ),
                    )
                    return
                found = [f"{name} ({code})" for code, name in sorted(languages.items(), key=lambda item: item[1].lower())]
                for i in range(0, len(found), 8):
                    self.bot.privateMessage(user_id, "\n".join(found[i:i+8]))
                return

            voices = await self.speech_engine.get_voices_list()
            lang_code = args[0].lower() if args else None
            found_voices = []
            for voice in voices:
                if not lang_code or voice["Locale"].lower().startswith(lang_code):
                    found_voices.append(self._("Name: {voice_name}, ShortName: {short_name}, Locale: {locale}").format(
                        voice_name=voice['FriendlyName'], short_name=voice['ShortName'], locale=voice['Locale']))

            if not found_voices:
                self.bot.privateMessage(user_id, self._("No voices found for the specified language code."))
                return

            for i in range(0, len(found_voices), 4):
                self.bot.privateMessage(user_id, "\n".join(found_voices[i:i+4]))

        except Exception as e:
            self.bot.privateMessage(user_id, self._("Error listing voices: {e}").format(e=e))

    def handle_ttsmode_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if not args:
            self.bot.privateMessage(user_id, self._("Usage: /ttsmode <microsoft|google>"))
            return
        mode = args[0].strip().lower()
        if mode not in ("microsoft", "google"):
            self.bot.privateMessage(user_id, self._("Invalid mode. Use microsoft or google."))
            return
        self.bot.tts_config["mode"] = mode
        self.bot.config_handler.save_tts_config(self.bot.tts_config)
        self.bot.privateMessage(user_id, self._("TTS mode set to {mode}.").format(mode=mode))

    def _get_tts_mode(self):
        mode = (self.bot.tts_config.get("mode") or "google").strip().lower()
        return mode if mode in ("microsoft", "google") else "google"

    def _as_bool(self, value):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _resolve_google_lang(self, lang):
        value = str(lang or "").strip()
        if not value:
            return "th"
        languages = tts_langs()
        if value in languages:
            return value
        lower_map = {code.lower(): code for code in languages}
        if value.lower() in lower_map:
            return lower_map[value.lower()]
        base = value.split("-", 1)[0].lower()
        if base in lower_map:
            return lower_map[base]
        return None

    def is_google_language(self, lang):
        return self._resolve_google_lang(lang) is not None

    def _atempo_filter(self, speed):
        speed = max(0.25, min(4.0, float(speed)))
        factors = []
        while speed < 0.5:
            factors.append(0.5)
            speed /= 0.5
        while speed > 2.0:
            factors.append(2.0)
            speed /= 2.0
        factors.append(speed)
        return ",".join(f"atempo={factor:.6g}" for factor in factors)

    def _synthesize_google_standard(self, text, filepath, lang="th", tld="com", slow=False, speed=1.0):
        """Generate Google standard speech with gTTS. No Google Cloud credentials are used."""
        resolved_lang = self._resolve_google_lang(lang) or "th"
        tld = str(tld or "com").strip() or "com"
        speed = max(0.25, min(4.0, float(speed)))
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

        source_path = filepath
        temp_source = None
        if abs(speed - 1.0) > 0.001:
            fd, temp_source = tempfile.mkstemp(prefix="sntalkbot_gtts_", suffix=".mp3")
            os.close(fd)
            source_path = temp_source

        try:
            gTTS(text=str(text), lang=resolved_lang, tld=tld, slow=self._as_bool(slow)).save(source_path)
            if temp_source:
                result = subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", temp_source, "-filter:a", self._atempo_filter(speed),
                        "-vn", filepath,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "ffmpeg failed while adjusting Google TTS speed")
            return os.path.getsize(filepath) if os.path.exists(filepath) else 0
        finally:
            if temp_source:
                try:
                    os.remove(temp_source)
                except OSError:
                    pass





    def _speak_google(self, text_to_speak, filepath, user_id):
        user_settings = self._get_user_settings(user_id)
        lang = user_settings.get("google_lang") or self.bot.tts_config.get("google_lang") or "th"
        try:
            speed = max(0.25, min(4.0, float(user_settings.get("speed", self.bot.tts_config.get("google_speed", 1.0)))))
        except (TypeError, ValueError):
            speed = 1.0
        return self._synthesize_google_standard(
            text_to_speak,
            filepath,
            lang=lang,
            tld=self.bot.tts_config.get("google_tld", "com"),
            slow=self.bot.tts_config.get("google_slow", False),
            speed=speed,
        )

    def _speak_google_with_voice_name(self, text_to_speak, filepath, voice_name):
        # gTTS has language/accent selection rather than Cloud named voices.
        lang = self._resolve_google_lang(voice_name) or self.bot.tts_config.get("google_lang") or "th"
        return self._synthesize_google_standard(
            text_to_speak,
            filepath,
            lang=lang,
            tld=self.bot.tts_config.get("google_tld", "com"),
            slow=self.bot.tts_config.get("google_slow", False),
            speed=self.bot.tts_config.get("google_speed", 1.0),
        )

    def _wait_for_broadcast_finish(self, filepath, text_to_speak):
        duration_ms = self.bot.get_media_file_duration_ms(filepath)
        if duration_ms <= 0:
            duration_ms = self._estimate_speech_duration_ms(text_to_speak)
        time.sleep(max(1.0, (duration_ms / 1000.0) + 0.5))

    def _estimate_speech_duration_ms(self, text_to_speak):
        words = len((text_to_speak or "").split())
        if words <= 0:
            return 2000
        seconds = max(2.0, words / 2.7)
        return int(seconds * 1000)

    def _speak_google_random_voice(self, text_to_speak, filepath):
        # Kept for backward compatibility: Google standard gTTS has no named voice catalogue.
        return self._synthesize_google_standard(
            text_to_speak,
            filepath,
            lang=self.bot.tts_config.get("google_lang", "th"),
            tld=self.bot.tts_config.get("google_tld", "com"),
            slow=self.bot.tts_config.get("google_slow", False),
            speed=self.bot.tts_config.get("google_speed", 1.0),
        )

    def _get_user_settings_key(self, user_id):
        user = self.bot.getUser(user_id)
        if user:
            username = ttstr(user.szUsername).strip()
            if username:
                return f"user:{username.lower()}"
            nickname = ttstr(user.szNickname).strip()
            if nickname:
                return f"nick:{nickname.lower()}"
        return f"id:{user_id}"

    def _get_user_settings(self, user_id, create=False):
        settings_key = self._get_user_settings_key(user_id)
        if create:
            return self.user_speech_settings.setdefault(settings_key, {})
        return self.user_speech_settings.get(settings_key, {})
