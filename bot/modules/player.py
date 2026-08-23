from TeamTalk5 import ttstr
import os
import yt_dlp
import threading
import time
import json
import re

class PlayerCog:
    """
    A module for handling all music and media player related commands.
    """
    def __init__(self, bot):
        self.bot = bot
        self.player = bot.player
        self._ = bot._        
        self.download_in_progress = False
        self.upload_timers = {}
        self.loading_new_track = False        
        self.autoplay_enabled = bool(self.bot.playback_config.get("autoplay_enabled", self.player.play_mode == 2))
        self.pending_channel_tabs = {}
        self.pending_playlist_tabs = {}
        self.pending_channel_timeout = 60
        self.player.end_callback = self.on_playback_end
        data_dir = os.getenv("TTUTIL_DATA_DIR", ".")
        os.makedirs(data_dir, exist_ok=True)
        self.favorites_file = os.path.join(data_dir, "favorites.json")
        self.favorites = self.load_favorites()

    def load_favorites(self):
        if os.path.exists(self.favorites_file):
            try:
                with open(self.favorites_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_favorites(self):
        try:
            with open(self.favorites_file, 'w', encoding='utf-8') as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving favorites: {e}")

    def register(self, command_handler):
        """Registers all the player commands with the command handler."""
        command_handler.register_command('u', self.handle_play_url_command)
        command_handler.register_command('p', self.handle_play_search_or_pause_command)
        command_handler.register_command('pm', self.handle_ytmusic_search_command)
        command_handler.register_command('n', self.handle_next_track_command)
        command_handler.register_command('b', self.handle_previous_track_command)
        command_handler.register_command('v', self.handle_change_volume_command)
        command_handler.register_command('l', self.handle_get_current_link_command) # ขอลิ้งค์เพลงที่กำลังเล่น
        command_handler.register_command('pg', self.handle_playing_info_command) # ดูข้อมูลเพลงที่กำลังเล่นอยู่
        command_handler.register_command('d', self.handle_get_duration_command) # Alias for /pg or specific duration info
        command_handler.register_command('r', self.handle_history_command)
        command_handler.register_command('dl', self.handle_download_command)
        command_handler.register_command('s', self.handle_stop_command)
        command_handler.register_command('x', self.handle_pause_resume_command)
        command_handler.register_command('t', self.handle_seek_to_time_command)
        command_handler.register_command('autoplay', self.handle_autoplay_command)
        command_handler.register_command('channel', self.handle_channel_command)
        command_handler.register_command('q', self.handle_queue_toggle_command)
        command_handler.register_command('ql', self.handle_queue_list_command)
        command_handler.register_command('qc', self.handle_queue_check_command)
        command_handler.register_command('dq', self.handle_delete_queue_command)
        command_handler.register_command('cq', self.handle_clear_queue_command)
        command_handler.register_command('.', self.handle_next_search_result_selection)
        command_handler.register_command(',', self.handle_prev_search_result_selection)
        command_handler.register_command('+', self.handle_seek_forward_command)
        command_handler.register_command('-', self.handle_seek_back_command)
        command_handler.register_command('fav', self.handle_fav_command)
        command_handler.register_command('playfav', self.handle_playfav_command)
        command_handler.register_command('delfav', self.handle_delfav_command)
        command_handler.register_command('3d', self.handle_3d_command)
        command_handler.register_command('3d2', self.handle_3d2_command)
        command_handler.register_command('bass', self.handle_bass_command)
        command_handler.register_command('sp', self.handle_speed_command)
        command_handler.register_command('f', self.handle_fade_command)
        command_handler.register_command('m', self.handle_mode_command)
        command_handler.register_command('m1', self.handle_mode1_command)
        command_handler.register_command('m2', self.handle_mode2_command)
        command_handler.register_command('m3', self.handle_mode3_command)
        command_handler.register_command('hide', self.handle_hide_command)
        command_handler.register_command('select', self.handle_select_command)
        command_handler.register_command('favorites', self.handle_favorites_list_command)
        command_handler.register_command('shuffle', self.handle_shuffle_command)
        command_handler.register_command('ptts', self.handle_player_tts_command, admin_only=True)
        command_handler.register_command('pttsmode', self.handle_player_tts_mode_command, admin_only=True)
        command_handler.register_command('pvoice', self.handle_player_voice_command, admin_only=True)
        command_handler.register_command('pvoices', self.handle_player_voices_command)
        command_handler.register_command('pttsrate', self.handle_player_tts_rate_command, admin_only=True)
        command_handler.register_command('pttsspeed', self.handle_player_tts_speed_command, admin_only=True)
        command_handler.register_command('cc', self.handle_clear_cache_command, admin_only=True)
        command_handler.register_command('csize', self.handle_cache_size_command, admin_only=True)
        command_handler.register_command('cm', self.handle_channel_messages_command, admin_only=True)

    def handle_channel_messages_command(self, textmessage, *args):
        enabled = not self.bot.playback_config.get("send_channel_messages", True)
        self.bot.playback_config["send_channel_messages"] = enabled
        self.bot.config_handler.update_playback_settings({"send_channel_messages": enabled})
        state = self._("enabled") if enabled else self._("disabled")
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Playback channel messages are now {state}.").format(state=state),
        )

    def handle_clear_cache_command(self, textmessage, *args):
        prefetched, temporary = self.player.clear_cache()
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Cache cleared. Prefetched entries: {prefetched}; temporary files: {temporary}.").format(
                prefetched=prefetched, temporary=temporary
            ),
        )

    def handle_cache_size_command(self, textmessage, *args):
        size_mb = self.player.cache_size_bytes() / (1024 * 1024)
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Cache size: {size:.2f} MB").format(size=size_mb),
        )

    def handle_player_tts_command(self, textmessage, *args):
        """Control Player track/queue speech independently from Manager chat TTS."""
        user_id = textmessage.nFromUserID
        playback = self.bot.playback_config
        if not args or args[0].lower() == "status":
            tracks = "ON" if playback.get("announce_tracks", True) else "OFF"
            queue_state = "ON" if playback.get("announce_queue", True) else "OFF"
            mode = self.bot.tts_cog.get_player_tts_mode()
            self.bot.privateMessage(user_id, self._("Player TTS: tracks={tracks}, queue={queue}, mode={mode}").format(
                tracks=tracks, queue=queue_state, mode=mode))
            return

        target = "all"
        value_index = 0
        first = args[0].lower()
        if first in ("tracks", "track", "queue"):
            target = "tracks" if first in ("tracks", "track") else "queue"
            value_index = 1
        if len(args) <= value_index or args[value_index].lower() not in ("on", "off"):
            self.bot.privateMessage(user_id, self._("Usage: /ptts on|off|status or /ptts tracks on|off or /ptts queue on|off"))
            return
        enabled = args[value_index].lower() == "on"
        updates = {}
        if target in ("all", "tracks"):
            updates["announce_tracks"] = enabled
            playback["announce_tracks"] = enabled
        if target in ("all", "queue"):
            updates["announce_queue"] = enabled
            playback["announce_queue"] = enabled
        self.bot.config_handler.update_playback_settings(updates)
        state = "ON" if enabled else "OFF"
        self.bot.privateMessage(user_id, self._("Player TTS {target}: {state}").format(target=target, state=state))

    def handle_player_tts_mode_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if not args or args[0].lower() not in ("microsoft", "google"):
            self.bot.privateMessage(user_id, self._("Usage: /pttsmode microsoft|google"))
            return
        mode = args[0].lower()
        self.bot.playback_config["announcement_tts_mode"] = mode
        self.bot.config_handler.update_playback_settings({"announcement_tts_mode": mode})
        self.bot.privateMessage(user_id, self._("Player TTS mode set to {mode}.").format(mode=mode))

    def handle_player_voice_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        mode = self.bot.tts_cog.get_player_tts_mode()
        if not args:
            if mode == "google":
                self.bot.privateMessage(user_id, self._("Usage: /pvoice <language_code>, for example /pvoice th"))
            else:
                self.bot.privateMessage(user_id, self._("Usage: /pvoice <voice_name>"))
            return
        value = " ".join(args).strip()
        if mode == "google":
            lang = self.bot.tts_cog._resolve_google_lang(value)
            if not lang:
                self.bot.privateMessage(user_id, self._("Unknown Google standard TTS language: {lang}. Use /pvoices to list languages.").format(lang=value))
                return
            key = "announcement_google_lang"
            value = lang
            label = self._("Google standard language")
        else:
            key = "announcement_microsoft_voice"
            label = self._("Microsoft voice")
        self.bot.playback_config[key] = value
        self.bot.config_handler.update_playback_settings({key: value})
        self.bot.privateMessage(user_id, self._("Player {label} set to {value}.").format(label=label, value=value))

    def handle_player_voices_command(self, textmessage, *args):
        lang_code = args[0] if args else None
        self.bot.tts_cog.list_player_voices(textmessage.nFromUserID, lang_code)

    def handle_player_tts_rate_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if self.bot.tts_cog.get_player_tts_mode() != "microsoft":
            self.bot.privateMessage(user_id, self._("Player TTS rate is available in Microsoft mode. For Google use /pttsspeed."))
            return
        if not args:
            self.bot.privateMessage(user_id, self._("Usage: /pttsrate <-100..100>"))
            return
        try:
            value = int(args[0])
        except ValueError:
            value = 999
        if not -100 <= value <= 100:
            self.bot.privateMessage(user_id, self._("Player TTS rate must be between -100 and 100."))
            return
        self.bot.playback_config["announcement_rate"] = value
        self.bot.config_handler.update_playback_settings({"announcement_rate": value})
        self.bot.privateMessage(user_id, self._("Player TTS rate set to {value}.").format(value=value))

    def handle_player_tts_speed_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if self.bot.tts_cog.get_player_tts_mode() != "google":
            self.bot.privateMessage(user_id, self._("Player TTS speed is available in Google mode. For Microsoft use /pttsrate."))
            return
        if not args:
            self.bot.privateMessage(user_id, self._("Usage: /pttsspeed <0.25..4.0>"))
            return
        try:
            value = float(args[0])
        except ValueError:
            value = -1.0
        if not 0.25 <= value <= 4.0:
            self.bot.privateMessage(user_id, self._("Player Google TTS speed must be between 0.25 and 4.0."))
            return
        self.bot.playback_config["announcement_google_speed"] = value
        self.bot.config_handler.update_playback_settings({"announcement_google_speed": value})
        self.bot.privateMessage(user_id, self._("Player Google standard TTS speed set to {value}.").format(value=value))

    def handle_prefixed_message(self, textmessage):
        """
        No longer handles prefixes without slashes as per user request.
        """
        return False

    def _is_in_same_channel(self, user_id):
        """Helper to check if a user is in the bot's channel."""
        user = self.bot.getUser(user_id)
        if not user or user.nChannelID != self.bot.getMyChannelID():
            self.bot.privateMessage(user_id, self._("You are not in the same channel"))
            return False
        return True

    def _nickname(self, user_id):
        """Return a safe nickname even if an async task finishes after logout."""
        try:
            user = self.bot.getUser(user_id)
            if user:
                return ttstr(user.szNickname) or self._("Unknown")
        except Exception:
            pass
        return self._("Unknown")

    def _send_playback_message(self, message, user_id=None):
        if self.bot.playback_config.get("send_channel_messages", True):
            self.bot.send_message(message)
            return
        if self.bot.playback_config.get("channel_messages_mode", "private") == "private" and user_id:
            self.bot.privateMessage(user_id, message)

    def _announce_track(self, title):
        if not self.bot.playback_config.get("announce_tracks", True):
            return
        try:
            self.bot.tts_cog.announce_player(self._("Now playing: {title}").format(title=title))
        except Exception as exc:
            print(f"Track announcement failed: {exc}")

    def _announce_queue(self, title=None, count=None):
        if not self.bot.playback_config.get("announce_queue", True):
            return
        try:
            if count is not None:
                text = self._("Added {count} tracks to the queue.").format(count=count)
            else:
                text = self._("Added to queue: {title}").format(title=title or self._("Unknown"))
            self.bot.tts_cog.announce_player(text)
        except Exception as exc:
            print(f"Queue announcement failed: {exc}")

    def handle_play_url_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
            
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: /u <link>"))
            return

        link = " ".join(args)
        collection_type = self.player.classify_collection_link(link)
        if collection_type:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Loading {collection_type}...").format(collection_type=collection_type))
            self.bot.io_pool.submit(self._play_collection_task, link, textmessage.nFromUserID)
            return
            
        if self.player.queue_mode:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Adding URL to queue..."))
            self.bot.io_pool.submit(self._enqueue_url_task, link, textmessage.nFromUserID)
            return

        self.player.clear_collection()
        self.player.current_link = link
        self.bot.enableVoiceTransmission(True)
        try:
            self.player.play_stream(link)
        except Exception as e:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Error playing stream: {e}").format(e=str(e)))
            return
        user_nickname = self._nickname(textmessage.nFromUserID)
        self._send_playback_message(self._("{nickname} requested playing from a URL").format(nickname=user_nickname))
        self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
        self._announce_track(self.player.media_title)

    def _enqueue_url_task(self, link, user_id):
        try:
            with self.player._ydl_lock:
                info = self.player.ydl.extract_info(link, download=False)
            video = {
                'title': info.get('title') or "Unknown title",
                'link': link
            }
            self.player.queue.append(video)
            user_nickname = self._nickname(user_id)
            self._send_playback_message(self._("{nickname} added to queue: {title}").format(nickname=user_nickname, title=video['title']))
            self._announce_queue(title=video['title'])
            if not self.player.is_playing:
                self.player.queue_index = len(self.player.queue) - 1
                self._play_from_queue(self.player.queue_index)
        except Exception as e:
            self.bot.privateMessage(user_id, self._("Error adding to queue: {e}").format(e=str(e)))

    def _play_collection_task(self, link, user_id):
        collection_type, results = self.player.fetch_collection(link)
        if not results:
            self.bot.privateMessage(user_id, self._("No videos found in the {collection_type}.").format(collection_type=collection_type or "playlist/channel"))
            return
        
        if self.player.queue_mode:
            self.player.queue.extend(results)
            self._send_playback_message(self._("{nickname} added {count} items from {collection_type} to queue.").format(
                nickname=self._nickname(user_id),
                count=len(results),
                collection_type=collection_type or "playlist/channel"
            ))
            self._announce_queue(count=len(results))
            if not self.player.is_playing:
                self.player.queue_index = len(self.player.queue) - len(results)
                self._play_from_queue(self.player.queue_index)
            return

        self.player.search_results = []
        self.player.current_search_index = 0
        self.player.collection_results = results
        self.player.current_collection_index = 0
        self.player.collection_source = collection_type
        first_video = results[0]
        self.player.current_link = first_video["link"]
        self.bot.enableVoiceTransmission(True)
        try:
            self.player.play_stream(first_video["link"])
        except Exception as e:
            self._send_playback_message(self._("Error playing {title}: {e}. Skipping...").format(title=first_video['title'], e=str(e)))
            self.on_playback_end()
            return
        self._prefetch_next_for_current()
        user_nickname = self._nickname(user_id)
        self._send_playback_message(self._("{nickname} requested to play from a {collection_type}").format(
            nickname=user_nickname, collection_type=collection_type or "playlist/channel"))
        self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
        self._announce_track(self.player.media_title)

    def handle_channel_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        if not self.player.is_playing or not self.player.current_link:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return

        self.bot.privateMessage(textmessage.nFromUserID, self._("Loading channel tabs..."))
        self.bot.io_pool.submit(self._fetch_channel_tabs_task, textmessage.nFromUserID, self.player.current_link)

    def _fetch_channel_tabs_task(self, user_id, current_link):
        channel_link = self.player.get_channel_link(current_link)
        if not channel_link:
            self.bot.privateMessage(user_id, self._("Unable to determine the channel for the current video."))
            return
        tabs = self.player.get_channel_tabs(channel_link)
        if not tabs:
            self.bot.privateMessage(user_id, self._("No channel tabs with playable videos were found."))
            return
        self.pending_channel_tabs[user_id] = {
            "options": tabs,
            "expires_at": time.time() + self.pending_channel_timeout,
        }
        lines = [self._("Choose a tab by number:")]
        for idx, tab in enumerate(tabs, start=1):
            lines.append(f"{idx}) {tab['name']}")
        self.bot.privateMessage(user_id, "\n".join(lines))

    def handle_channel_selection_message(self, textmessage):
        user_id = textmessage.nFromUserID
        pending = self.pending_channel_tabs.get(user_id)
        if not pending:
            return False
        message_text = ttstr(textmessage.szMessage).strip()
        if time.time() > pending["expires_at"]:
            del self.pending_channel_tabs[user_id]
            if message_text.isdigit():
                self.bot.privateMessage(user_id, self._("Channel selection expired. Use /channel again."))
                return True
            return False
        if not message_text.isdigit():
            return False
        selection = int(message_text)
        options = pending["options"]
        if selection < 1 or selection > len(options):
            self.bot.privateMessage(user_id, self._("Invalid selection. Choose a number from the list."))
            return True
        del self.pending_channel_tabs[user_id]
        chosen = options[selection - 1]
        self.bot.privateMessage(user_id, self._("Loading {tab}...").format(tab=chosen["name"]))
        self.bot.io_pool.submit(self._play_channel_tab_task, user_id, chosen)
        return True

    def _play_channel_tab_task(self, user_id, chosen):
        try:
            if chosen.get("kind") == "playlists":
                playlists = self.player.get_channel_playlists(chosen["link"])
                if not playlists:
                    self.bot.privateMessage(user_id, self._("No playlists found on this channel."))
                    return
                self.pending_playlist_tabs[user_id] = {
                    "options": playlists,
                    "expires_at": time.time() + self.pending_channel_timeout,
                }
                lines = [self._("Choose a playlist by number:")]
                for idx, playlist in enumerate(playlists, start=1):
                    lines.append(f"{idx}) {playlist['title']}")
                self.bot.privateMessage(user_id, "\n".join(lines))
                return
            self._play_collection_task(chosen["link"], user_id)
        except Exception as e:
            self.bot.privateMessage(user_id, self._("Failed to load the selected tab: {e}").format(e=str(e)))

    def handle_playlist_selection_message(self, textmessage):
        user_id = textmessage.nFromUserID
        pending = self.pending_playlist_tabs.get(user_id)
        if not pending:
            return False
        message_text = ttstr(textmessage.szMessage).strip()
        if time.time() > pending["expires_at"]:
            del self.pending_playlist_tabs[user_id]
            if message_text.isdigit():
                self.bot.privateMessage(user_id, self._("Playlist selection expired. Use /channel again."))
                return True
            return False
        if not message_text.isdigit():
            return False
        selection = int(message_text)
        options = pending["options"]
        if selection < 1 or selection > len(options):
            self.bot.privateMessage(user_id, self._("Invalid selection. Choose a number from the list."))
            return True
        del self.pending_playlist_tabs[user_id]
        chosen = options[selection - 1]
        self.bot.privateMessage(user_id, self._("Loading playlist..."))
        self.bot.io_pool.submit(self._play_collection_task, chosen["link"], user_id)
        return True

    def handle_play_search_or_pause_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        if args: # This is a search request
            query = " ".join(args)
            if self.player.queue_mode:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Searching to add to queue..."))
                self.bot.io_pool.submit(self._search_and_enqueue_task, query, textmessage.nFromUserID)
            else:
                if self.player.is_playing:
                    self.player.fade_out_and_stop()
                    self.bot.enableVoiceTransmission(False)
                self.player.clear_collection()
                self.bot.privateMessage(textmessage.nFromUserID, self._("Searching..."))
                self.bot.io_pool.submit(self._search_and_play_task, query, textmessage.nFromUserID)
        else: # This is a pause/resume request
            self.handle_pause_resume_command(textmessage)

    def handle_ytmusic_search_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: /pm <name>"))
            return
        
        query = " ".join(args)
        if self.player.queue_mode:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Searching YouTube Music to add to queue..."))
            self.bot.io_pool.submit(self._search_and_enqueue_task, query, textmessage.nFromUserID, source='ytmusic')
        else:
            if self.player.is_playing:
                self.player.fade_out_and_stop()
                self.bot.enableVoiceTransmission(False)
            self.player.clear_collection()
            self.bot.privateMessage(textmessage.nFromUserID, self._("Searching YouTube Music..."))
            self.bot.io_pool.submit(self._search_and_play_task, query, textmessage.nFromUserID, source='ytmusic')

    def _search_and_play_task(self, query, user_id, source='youtube'):
        """Task to be run in the thread pool for searching and playing."""
        if source == 'ytmusic':
            results = self.player.search_ytmusic(query)
        else:
            results = self.player.search_youtube(query)
            
        if results:
            self.player.search_results = results
            self.player.current_search_index = 0
            first_video = results[0]
            self.player.current_link = first_video['link']
            self.bot.enableVoiceTransmission(True)
            try:
                self.player.play_stream(first_video['link'])
            except Exception as e:
                self._send_playback_message(self._("Error playing {title}: {e}. Skipping...").format(title=first_video['title'], e=str(e)))
                self.on_playback_end()
                return
            self._prefetch_next_for_current()
            user_nickname = self._nickname(user_id)
            self._send_playback_message(self._("{nickname} requested to play: {title}").format(nickname=user_nickname, title=first_video['title']))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
        else:
            self._send_playback_message(self._("No results found for '{query}'.").format(query=query))

    def _search_and_enqueue_task(self, query, user_id, source='youtube'):
        """Task to search and add to queue."""
        if source == 'ytmusic':
            results = self.player.search_ytmusic(query)
        else:
            results = self.player.search_youtube(query)
            
        if results:
            self.player.search_results = results
            self.player.current_search_index = 0
            video = results[0]
            self.player.queue.append(video)
            user_nickname = self._nickname(user_id)
            self._send_playback_message(self._("{nickname} added to queue: {title}").format(nickname=user_nickname, title=video['title']))
            self._announce_queue(title=video['title'])
            if not self.player.is_playing:
                self.player.queue_index = len(self.player.queue) - 1
                self._play_from_queue(self.player.queue_index)
        else:
            self._send_playback_message(self._("No results found for '{query}'.").format(query=query))

    def _play_from_queue(self, index):
        if index < 0 or index >= len(self.player.queue):
            return
        
        video = self.player.queue[index]
        self.loading_new_track = True
        try:
            self.player.stop()
            self.player.current_link = video['link']
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(video['link'])
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
        except Exception as e:
            self._send_playback_message(self._("Error playing {title}: {e}. Skipping...").format(title=video.get('title', 'Unknown'), e=str(e)))
            self.on_playback_end() # Trigger next track
        finally:
            self.loading_new_track = False

    def handle_pause_resume_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
            
        title = self.player.media_title
        if self.player.is_playing and not self.player.pause:
            self.player.pause_stream()
            self.bot.enableVoiceTransmission(False)
            user_nickname = self._nickname(textmessage.nFromUserID)
            self._send_playback_message(self._("{nickname} paused the playback").format(nickname=user_nickname))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Paused: {title}").format(title=title)))
        elif self.player.pause:
            self.player.pause = False
            self.bot.enableVoiceTransmission(True)
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=title)))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing to pause or resume."))

    def handle_seek_forward_command(self, textmessage, *args):
        arg_str = args[0] if args else "10"
        self.handle_seek_forward(textmessage, arg_str)

    def handle_seek_back_command(self, textmessage, *args):
        arg_str = args[0] if args else "10"
        self.handle_seek_back(textmessage, arg_str)

    def handle_seek_forward(self, textmessage, arg_str):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return
        
        try:
            amount = int(arg_str) if arg_str else 10
            self.player.seek_forward(amount)
        except ValueError:
            self.player.seek_forward(10)
            
    def handle_seek_back(self, textmessage, arg_str):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return
        
        try:
            amount = int(arg_str) if arg_str else 10
            self.player.seek_back(amount)
        except ValueError:
            self.player.seek_back(10)

    def handle_seek_to_time_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: /t <time> (e.g., 1:30 or 90)"))
            return
        
        time_str = args[0]
        try:
            if ":" in time_str:
                parts = time_str.split(":")
                if len(parts) == 2:
                    seconds = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                else:
                    raise ValueError
            else:
                seconds = int(time_str)
            
            self.player.seek(seconds, reference="absolute")
        except ValueError:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid time format. Use seconds or M:S or H:M:S."))

    def handle_next_track_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        def play_next_track():
            self._play_next_from_active_list(user_id=textmessage.nFromUserID, announce_private=True)
        
        self.bot.io_pool.submit(play_next_track)

    def handle_previous_track_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        def play_previous_track():
            self._play_previous_from_active_list(user_id=textmessage.nFromUserID, announce_private=True)

        self.bot.io_pool.submit(play_previous_track)
        
    def handle_stop_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        if self.player.is_playing or self.player.queue:
            self.player.stop()
            self.player.current_link = None
            self.player.search_results = []
            self.player.current_search_index = 0
            self.player.clear_collection()
            self.player.queue = []
            self.player.queue_index = -1
            self.bot.enableVoiceTransmission(False)
            user_nickname = self._nickname(textmessage.nFromUserID)
            self._send_playback_message(self._("{nickname} stopped the playback and cleared queue").format(nickname=user_nickname))
            status_msg = self.bot.get_idle_status_message()
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(status_msg))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            
    def handle_change_volume_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        try:
            if not args:
                self.bot.privateMessage(textmessage.nFromUserID, self._("The current volume is {volume}").format(volume=int(self.player.volume)))
                return
            
            volume = int(args[0])
            max_volume = self.bot.playback_config['max_volume']
            if volume > max_volume:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Maximum allowed volume is {max_volume}").format(max_volume=max_volume))
            else:
                self.player.volume = volume
                user_nickname = self._nickname(textmessage.nFromUserID)
                self._send_playback_message(self._("{name} has changed the volume to {volume}").format(name=user_nickname, volume=volume))
        except (ValueError, IndexError):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: /v [volume_level]"))

    def on_playback_end(self):
        """Callback function to be called when playback ends."""
        if self.loading_new_track:
            return

        # 1. Check Queue
        if self.player.queue_mode and self.player.queue:
            if self.player.queue_index < len(self.player.queue) - 1:
                self.player.queue_index += 1
                self.bot.io_pool.submit(self._play_from_queue, self.player.queue_index)
                return

        # 2. TT Player modes for non-queue playback.
        if self.player.play_mode == 3 and self.player.current_link:
            self.bot.io_pool.submit(self._repeat_current_track)
            return
        if (self.player.play_mode == 2 or self.autoplay_enabled) and self._has_next_in_active_list():
            self.bot.io_pool.submit(self._play_next_from_active_list, None, False)
            return

        self.bot.enableVoiceTransmission(False)
        status_msg = self.bot.get_idle_status_message()
        self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(status_msg))


    def _repeat_current_track(self):
        """Replay the current link for M3 repeat mode without rebuilding the active collection."""
        link = self.player.current_link
        if not link:
            return
        self.loading_new_track = True
        try:
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(link)
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
        except Exception as exc:
            self._send_playback_message(self._("Error playing {title}: {e}. Skipping...").format(title=self.player.media_title or "Unknown", e=str(exc)))
            self.bot.enableVoiceTransmission(False)
        finally:
            self.loading_new_track = False

    def handle_autoplay_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        if args:
            arg = args[0].strip().lower()
            if arg in ("on", "1", "true", "yes"):
                self.autoplay_enabled = True
            elif arg in ("off", "0", "false", "no"):
                self.autoplay_enabled = False
            else:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: /autoplay [on|off]"))
                return
        else:
            self.autoplay_enabled = not self.autoplay_enabled

        if self.autoplay_enabled and self.player.play_mode != 3:
            self.player.play_mode = 2
        elif not self.autoplay_enabled and self.player.play_mode == 2:
            self.player.play_mode = 1
        self.bot.playback_config["autoplay_enabled"] = self.autoplay_enabled
        self.bot.playback_config["play_mode"] = self.player.play_mode
        self.bot.config_handler.update_playback_settings({
            "autoplay_enabled": self.autoplay_enabled,
            "play_mode": self.player.play_mode,
        })
        state = self._("enabled") if self.autoplay_enabled else self._("disabled")
        self.bot.privateMessage(textmessage.nFromUserID, self._("Autoplay is {state}.").format(state=state))
        if self.autoplay_enabled:
            self._prefetch_next_for_current()

    def _get_active_results(self):
        if self.player.queue_mode and self.player.queue:
            return self.player.queue, "queue"
        if self.player.collection_results:
            return self.player.collection_results, "collection"
        if self.player.search_results:
            return self.player.search_results, "search"
        return None, None

    def _get_active_index(self):
        if self.player.queue_mode and self.player.queue:
            return self.player.queue_index
        if self.player.collection_results:
            return self.player.current_collection_index
        return self.player.current_search_index

    def _set_active_index(self, value):
        if self.player.queue_mode and self.player.queue:
            self.player.queue_index = value
        elif self.player.collection_results:
            self.player.current_collection_index = value
        else:
            self.player.current_search_index = value

    def _has_next_in_active_list(self):
        results, _ = self._get_active_results()
        if not results:
            return False
        current_index = self._get_active_index()
        return current_index < len(results) - 1

    def _play_next_from_active_list(self, user_id=None, announce_private=False):
        results, list_type = self._get_active_results()
        if not results:
            if user_id:
                self.bot.privateMessage(user_id, self._("No list to play from."))
            return

        current_index = self._get_active_index()
        if current_index >= len(results) - 1:
            if user_id:
                self.bot.privateMessage(user_id, self._("You've reached the end of the list."))
            return

        self.loading_new_track = True
        self._set_active_index(current_index + 1)
        next_video = results[self._get_active_index()]
        
        try:
            self.player.stop()
            self.player.current_link = next_video['link']
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(next_video['link'])
            if announce_private and user_id:
                self.bot.privateMessage(user_id, self._("Playing: {title}").format(title=next_video['title']))
            elif user_id is None:
                self._send_playback_message(self._("Autoplaying: {title}").format(title=next_video['title']))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
            self._prefetch_next_for_current()
        except Exception as e:
            self._send_playback_message(self._("Error playing {title}: {e}. Skipping...").format(title=next_video.get('title', 'Unknown'), e=str(e)))
            self.on_playback_end()
        finally:
            self.loading_new_track = False

    def _play_previous_from_active_list(self, user_id=None, announce_private=False):
        results, _ = self._get_active_results()
        if not results:
            if user_id:
                self.bot.privateMessage(user_id, self._("No list to play from."))
            return

        current_index = self._get_active_index()
        if current_index <= 0:
            if user_id:
                self.bot.privateMessage(user_id, self._("You are at the beginning of the list."))
            return

        self.loading_new_track = True
        self._set_active_index(current_index - 1)
        prev_video = results[self._get_active_index()]
        
        try:
            self.player.stop()
            self.player.current_link = prev_video['link']
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(prev_video['link'])
            if announce_private and user_id:
                self.bot.privateMessage(user_id, self._("Playing: {title}").format(title=prev_video['title']))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._prefetch_next_for_current()
        except Exception as e:
            self._send_playback_message(self._("Error playing {title}: {e}. Skipping...").format(title=prev_video.get('title', 'Unknown'), e=str(e)))
            self.on_playback_end()
        finally:
            self.loading_new_track = False

    def _prefetch_next_for_current(self):
        results, _ = self._get_active_results()
        if not results:
            return
        current_index = self._get_active_index()
        links = [item.get("link") for item in results[current_index + 1: current_index + 6] if item.get("link")]
        self.player.prefetcher.schedule(links)

    def handle_history_command(self, textmessage, *args):
        if args:
            self.handle_play_from_history(textmessage, *args)
        else:
            self.handle_recent_history(textmessage)

    def handle_recent_history(self, textmessage):
        history_str = self.player.get_recent_history()
        history_lines = history_str.splitlines()
        for i in range(0, len(history_lines), 4):
            chunk = "\n".join(history_lines[i:i + 4])
            self.bot.privateMessage(textmessage.nFromUserID, chunk)

    def handle_play_from_history(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        try:
            index = int(args[0])
            self.bot.enableVoiceTransmission(True)
            result_message = self.player.play_from_history(index)
            if "Playing" in result_message:
                user_nickname = self._nickname(textmessage.nFromUserID)
                self._send_playback_message(self._("{nickname} requested to play {title} from history").format(nickname=user_nickname, title=self.player.media_title))
                self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            else:
                self.bot.privateMessage(textmessage.nFromUserID, result_message)
        except (ValueError, IndexError):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: /r <index>"))

    def handle_download_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        if self.download_in_progress:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Download already in progress. Please wait."))
            return

        link = " ".join(args) if args else self.player.current_link
        
        if not link:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: /dl <youtube_link> or play a track first."))
            return

        self.bot.io_pool.submit(self._download_and_upload_task, textmessage.nFromUserID, link)

    def _download_and_upload_task(self, user_id, link):
        """Task for downloading and uploading audio, run in the thread pool."""
        self.download_in_progress = True
        self.bot.privateMessage(user_id, self._("Downloading audio. Please wait..."))
        try:
            cached_file = self.player.get_cached_media(link)
            if cached_file:
                filename = cached_file
            else:
                ydl_opts = self.player._base_ydl_opts(noplaylist=True)
                ydl_opts.update({
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'outtmpl': os.path.join("files", "%(title)s.%(ext)s"),
                    'skip_download': False,
                })
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(link, download=True)
                    filename = ydl.prepare_filename(info_dict)

            user = self.bot.getUser(user_id)
            if not user:
                return
            channel_id = int(getattr(user, "nChannelID", 0) or 0)
            if not channel_id:
                return
            self.bot.doSendFile(channel_id, ttstr(filename))
            filename_only = os.path.basename(filename)
            self.bot.privateMessage(user_id, self._("File {filename} downloaded. Uploading...").format(filename=filename_only))
            
            if self.bot.bot_config['video_deletion_timer'] > 0:
                self.upload_timers[filename] = threading.Timer(
                    self.bot.bot_config['video_deletion_timer'] * 60, 
                    self.delete_uploaded_file, 
                    args=(filename, channel_id)
                )
                self.upload_timers[filename].start()

        except Exception as e:
            self.bot.privateMessage(user_id, self._("Error downloading or uploading: {e}").format(e=str(e)))
        finally:
            self.download_in_progress = False

    def delete_uploaded_file(self, filename, channel_id):
        """Deletes the uploaded audio file after the timer expires."""
        try:
            file_id = self.get_file_id_by_name(channel_id, os.path.basename(filename)) 
            if file_id:
                self.bot.doDeleteFile(channel_id, file_id)
            if os.path.exists(filename):
                os.remove(filename)
            del self.upload_timers[filename]
        except Exception as e:
            print(self._("Error deleting file: {e}").format(e=str(e)))

    def get_file_id_by_name(self, channel_id, filename):
        """Gets the file ID from the TeamTalk server based on filename."""
        files = self.bot.getChannelFiles(channel_id)
        for file in files:
            if ttstr(file.szFileName) == filename:
                return file.nFileID
        return None

    def handle_queue_toggle_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        if args:
            arg = args[0].strip().lower()
            if arg in ("on", "1", "true", "yes"):
                self.player.queue_mode = True
            elif arg in ("off", "0", "false", "no"):
                self.player.queue_mode = False
            else:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: /q [on|off]"))
                return
        else:
            self.player.queue_mode = not self.player.queue_mode
        
        self.bot.playback_config["queue_mode"] = self.player.queue_mode
        self.bot.config_handler.update_playback_settings({"queue_mode": self.player.queue_mode})
        state = self._("enabled") if self.player.queue_mode else self._("disabled")
        self.bot.privateMessage(textmessage.nFromUserID, self._("Queue system is {state}.").format(state=state))

    def handle_queue_list_command(self, textmessage, *args):
        if not self.player.queue:
            self.bot.privateMessage(textmessage.nFromUserID, self._("The queue is empty."))
            return
        
        lines = [self._("Current Queue:")]
        for i, video in enumerate(self.player.queue):
            prefix = "-> " if i == self.player.queue_index else f"{i+1}. "
            lines.append(f"{prefix}{video['title']}")
        
        msg = "\n".join(lines)
        for chunk in self.bot._split_private_message(msg):
            self.bot.privateMessage(textmessage.nFromUserID, chunk)

    def handle_queue_check_command(self, textmessage, *args):
        if not self.player.queue:
            self.bot.privateMessage(textmessage.nFromUserID, self._("The queue is empty."))
            return
        
        msg = self._("Playing: {current} / {total}").format(
            current=self.player.queue_index + 1,
            total=len(self.player.queue)
        )
        self.bot.privateMessage(textmessage.nFromUserID, msg)

    def handle_delete_queue_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: /dq <index>"))
            return
        
        try:
            idx = int(args[0]) - 1
            if 0 <= idx < len(self.player.queue):
                removed = self.player.queue.pop(idx)
                self.bot.privateMessage(textmessage.nFromUserID, self._("Removed from queue: {title}").format(title=removed['title']))
                if idx < self.player.queue_index:
                    self.player.queue_index -= 1
                elif idx == self.player.queue_index:
                    if self.player.is_playing:
                        self.handle_next_track_command(textmessage)
            else:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid queue index."))
        except ValueError:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: /dq <index>"))

    def handle_clear_queue_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        self.player.queue = []
        self.player.queue_index = -1
        self.bot.privateMessage(textmessage.nFromUserID, self._("Queue cleared."))

    def handle_playing_info_command(self, textmessage, *args):
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing."))
            return
        
        title = self.player.media_title or self._("Unknown")
        elapsed = self.player.format_time(self.player.playback_time or 0)
        total = self.player.format_time(self.player.duration or 0)
        self.bot.privateMessage(textmessage.nFromUserID, self._("Currently playing: {title} [{elapsed}/{total}]").format(title=title, elapsed=elapsed, total=total))

    def handle_get_duration_command(self, textmessage, *args):
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return

        elapsed_time = self.player.playback_time or 0
        total_duration = self.player.duration or 0
        remaining_time = total_duration - elapsed_time
        
        self.bot.privateMessage(textmessage.nFromUserID, 
            self._("Total duration: {total_duration}. Elapsed time: {elapsed_time}. Remaining time: {remaining_time}").format(
                total_duration=self.player.format_time(total_duration), 
                elapsed_time=self.player.format_time(elapsed_time), 
                remaining_time=self.player.format_time(remaining_time)))

    def handle_get_current_link_command(self, textmessage, *args):
        if self.player.current_link:
            self.bot.privateMessage(textmessage.nFromUserID, self.player.current_link)
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing."))

    def handle_next_search_result_selection(self, textmessage, *args):
        if not self.player.search_results or not self.player.queue_mode or not self.player.queue:
            return
        
        self.player.current_search_index = (self.player.current_search_index + 1) % len(self.player.search_results)
        video = self.player.search_results[self.player.current_search_index]
        
        if self.player.queue:
            self.player.queue[-1] = video
            self.bot.privateMessage(textmessage.nFromUserID, self._("Selection changed to: {title}").format(title=video['title']))
            if self.player.queue_index == len(self.player.queue) - 1:
                self._play_from_queue(self.player.queue_index)

    def handle_prev_search_result_selection(self, textmessage, *args):
        if not self.player.search_results or not self.player.queue_mode or not self.player.queue:
            return
        
        self.player.current_search_index = (self.player.current_search_index - 1) % len(self.player.search_results)
        video = self.player.search_results[self.player.current_search_index]
        
        if self.player.queue:
            self.player.queue[-1] = video
            self.bot.privateMessage(textmessage.nFromUserID, self._("Selection changed to: {title}").format(title=video['title']))
            if self.player.queue_index == len(self.player.queue) - 1:
                self._play_from_queue(self.player.queue_index)

    def handle_fav_command(self, textmessage, *args):
        if not self.player.is_playing or not self.player.current_link:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing."))
            return
        
        track = {
            "title": self.player.media_title,
            "link": self.player.current_link
        }
        if track not in self.favorites:
            self.favorites.append(track)
            self.save_favorites()
            self.bot.privateMessage(textmessage.nFromUserID, self._("Added to favorites: {title}").format(title=track['title']))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Already in favorites."))

    def handle_playfav_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.favorites:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Your favorites list is empty."))
            return
        
        if self.player.queue_mode:
            self.player.queue.extend(self.favorites)
            self._send_playback_message(self._("{nickname} added all favorites to queue.").format(nickname=self._nickname(textmessage.nFromUserID)))
            if not self.player.is_playing:
                self.player.queue_index = len(self.player.queue) - len(self.favorites)
                self._play_from_queue(self.player.queue_index)
        else:
            self.player.clear_collection()
            self.player.collection_results = self.favorites
            self.player.current_collection_index = 0
            self.player.collection_source = "favorites"
            self._play_from_queue_explicit(0, self.favorites)

    def _play_from_queue_explicit(self, index, results):
        first_video = results[index]
        self.player.current_link = first_video["link"]
        self.bot.enableVoiceTransmission(True)
        try:
            self.player.play_stream(first_video["link"])
            self._send_playback_message(self._("Playing from favorites: {title}").format(title=self.player.media_title))
        except Exception as e:
            self._send_playback_message(self._("Error playing {title}: {e}").format(title=first_video['title'], e=str(e)))
            self.on_playback_end()

    def handle_delfav_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        self.favorites = []
        self.save_favorites()
        self.bot.privateMessage(textmessage.nFromUserID, self._("Favorites list cleared."))

    def handle_3d_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        arg = args[0] if args else ""
        if arg == "on": self.player.is_stereo_wide = True
        elif arg == "off": self.player.is_stereo_wide = False
        else: self.player.is_stereo_wide = not self.player.is_stereo_wide
        self.player.update_filters()
        self.bot.config_handler.update_playback_settings({"is_stereo_wide": self.player.is_stereo_wide})
        self._send_playback_message(self._("Stereo 3D 1: {state}").format(state="ON" if self.player.is_stereo_wide else "OFF"))

    def handle_3d2_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        arg = args[0] if args else ""
        if arg == "on": self.player.is_stereo_echo = True
        elif arg == "off": self.player.is_stereo_echo = False
        else: self.player.is_stereo_echo = not self.player.is_stereo_echo
        self.player.update_filters()
        self.bot.config_handler.update_playback_settings({"is_stereo_echo": self.player.is_stereo_echo})
        self._send_playback_message(self._("Stereo 3D 2 (Echo): {state}").format(state="ON" if self.player.is_stereo_echo else "OFF"))

    def handle_bass_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        arg = args[0] if args else ""
        if arg == "on": self.player.is_bass_boosted = True
        elif arg == "off": self.player.is_bass_boosted = False
        else: self.player.is_bass_boosted = not self.player.is_bass_boosted
        self.player.update_filters()
        self.bot.config_handler.update_playback_settings({"is_bass_boosted": self.player.is_bass_boosted})
        self._send_playback_message(self._("Bass Boost: {state}").format(state="ON" if self.player.is_bass_boosted else "OFF"))

    def handle_speed_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Current speed: {speed}x").format(speed=self.player.speed))
            return
        try:
            val = float(args[0])
            self.player.speed = val
            self.player['speed'] = val
            self.bot.config_handler.update_playback_settings({"speed": val})
            self._send_playback_message(self._("Playback speed set to: {speed}x").format(speed=val))
        except:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid speed value."))

    def handle_fade_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        self.player.fade_enabled = not getattr(self.player, "fade_enabled", True)
        self.bot.config_handler.update_playback_settings({"fade_enabled": self.player.fade_enabled})
        self._send_playback_message(self._("Fade effect: {state}").format(state="ON" if self.player.fade_enabled else "OFF"))

    def handle_mode_command(self, textmessage, *args):
        mode = getattr(self.player, "play_mode", 1)
        m_txt = {1: "Single", 2: "Auto/Next", 3: "Repeat"}
        self.bot.privateMessage(textmessage.nFromUserID, self._("Current mode: M{mode} - {txt}").format(mode=mode, txt=m_txt.get(mode, "")))

    def _set_play_mode(self, mode):
        self.player.play_mode = mode
        self.autoplay_enabled = mode == 2
        self.bot.playback_config["play_mode"] = mode
        self.bot.playback_config["autoplay_enabled"] = self.autoplay_enabled
        self.bot.config_handler.update_playback_settings({
            "play_mode": mode,
            "autoplay_enabled": self.autoplay_enabled,
        })

    def handle_mode1_command(self, textmessage, *args):
        self._set_play_mode(1)
        self._send_playback_message(self._("Mode set to: M1 (Single)"))

    def handle_mode2_command(self, textmessage, *args):
        self._set_play_mode(2)
        self._send_playback_message(self._("Mode set to: M2 (Auto/Next)"))
        self._prefetch_next_for_current()

    def handle_mode3_command(self, textmessage, *args):
        self._set_play_mode(3)
        self._send_playback_message(self._("Mode set to: M3 (Repeat)"))

    def handle_select_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: /select <index>"))
            return
        try:
            index = int(args[0]) - 1
        except ValueError:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Index must be a number."))
            return
        results, _ = self._get_active_results()
        if not results:
            results = self.player.search_results
        if index < 0 or index >= len(results):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Track index is out of range."))
            return
        self.loading_new_track = True
        try:
            self._set_active_index(index)
            item = results[index]
            self.player.stop()
            self.player.current_link = item["link"]
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(item["link"])
            self._send_playback_message(self._("Playing: {title}").format(title=self.player.media_title), textmessage.nFromUserID)
            self._announce_track(self.player.media_title)
            self._prefetch_next_for_current()
        except Exception as exc:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Error playing track: {error}").format(error=str(exc)))
        finally:
            self.loading_new_track = False

    def handle_favorites_list_command(self, textmessage, *args):
        if not self.favorites:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Your favorites list is empty."))
            return
        for index, track in enumerate(self.favorites, 1):
            self.bot.privateMessage(textmessage.nFromUserID, f"{index}. {track.get('title', 'Unknown')} - {track.get('link', '')}")

    def handle_shuffle_command(self, textmessage, *args):
        import random
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.player.queue:
            self.bot.privateMessage(textmessage.nFromUserID, self._("The queue is empty."))
            return
        start = max(self.player.queue_index + 1, 0)
        pending = self.player.queue[start:]
        random.shuffle(pending)
        self.player.queue[start:] = pending
        self.bot.privateMessage(textmessage.nFromUserID, self._("The unplayed queue has been shuffled."))
        self._prefetch_next_for_current()

    def handle_hide_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        self.player.hide_status = not getattr(self.player, "hide_status", False)
        if self.player.hide_status:
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(""))
            self._send_playback_message(self._("Status hidden."))
        else:
            if self.player.is_playing:
                status = self._("Playing: {title}").format(title=self.player.media_title)
            else:
                status = self.bot.get_idle_status_message()
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(status))
            self._send_playback_message(self._("Status shown."))
