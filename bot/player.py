import os
import mpv
import tempfile
import threading
import time
from urllib.parse import parse_qs, quote_plus, urlparse
import yt_dlp
from bot.prefetch import LinkPrefetcher

class Player(mpv.MPV):
    def __init__(self, config_handler, cookiefile=None, *args, **kwargs):
        # Linux/Docker launchers set TTUTIL_MPV_AO=pulse so MPV sends audio to
        # the virtual PulseAudio sink. Leave it unset on desktop systems to let
        # mpv choose the native audio output automatically.
        mpv_ao = os.getenv("TTUTIL_MPV_AO", "").strip()
        if mpv_ao and "ao" not in kwargs:
            kwargs["ao"] = mpv_ao
        super().__init__(ytdl=False, vo='null', video=False, *args, **kwargs)
        self.config_handler = config_handler # <-- STORE THE INJECTED INSTANCE
        self.playback_config = self.config_handler.get_playback_config()
        self.is_playing=False
        self.volume=self.playback_config['default_volume']
        self.current_link=None
        self._media_title = ""
        self.search_results = []
        self.current_search_index = 0
        self.collection_results = []
        self.current_collection_index = 0
        self.collection_source = None
        self.queue = []
        self.queue_index = -1
        self.queue_mode = self.playback_config.get("queue_mode", False)
        self.play_mode = int(self.playback_config.get("play_mode", 2) or 2)
        self._prefetch_cache = {}
        self._ydl_lock = threading.Lock()
        self.recent_history = {}
        self.end_callback = None
        self._temp_cache = {}
        self.cookiefile = cookiefile or self.playback_config.get("cookiefile_path")
        self.ytdlp_config = self.config_handler.get_ytdlp_config()
        self.fade_enabled = self.playback_config.get("fade_enabled", True)
        self.is_stereo_wide = self.playback_config.get("is_stereo_wide", False)
        self.is_stereo_echo = self.playback_config.get("is_stereo_echo", False)
        self.is_bass_boosted = self.playback_config.get("is_bass_boosted", False)
        self.audio_quality = self.playback_config.get("audio_quality", "High")
        self.audio_buffer = self.playback_config.get("audio_buffer", "0.5")
        self.speed = self.playback_config.get("speed", 1.0)
        self.set_output_device()
        self.update_filters()
        self.ydl = yt_dlp.YoutubeDL(self._base_ydl_opts(noplaylist=True))
        self.prefetcher = LinkPrefetcher(self.prefetch_stream_info, max_pending=5)

    def _base_ydl_opts(self, *, extract_flat=False, noplaylist=False, playlistend=None):
        """Return yt-dlp Python API options shared by search and playback."""
        cfg = self.ytdlp_config
        opts = {
            "format": cfg.get("format", "bestaudio/best"),
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": cfg.get("timeout", 20),
            "retries": cfg.get("retries", 5),
            "fragment_retries": cfg.get("fragment_retries", 5),
            "concurrent_fragment_downloads": cfg.get("concurrent_fragment_downloads", 4),
            "extract_flat": extract_flat,
            "noplaylist": noplaylist,
        }
        if playlistend is not None:
            opts["playlistend"] = playlistend
        if self.cookiefile and os.path.isfile(self.cookiefile):
            opts["cookiefile"] = self.cookiefile
        impersonate = (cfg.get("impersonate") or "").strip()
        if impersonate:
            opts["impersonate"] = impersonate
        return opts

    @staticmethod
    def _iter_entries(info):
        """Yield leaf yt-dlp entries, including nested YouTube Music/playlist results."""
        if not isinstance(info, dict):
            return
        entries = info.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                nested = entry.get("entries")
                if isinstance(nested, list) and nested:
                    yield from Player._iter_entries(entry)
                else:
                    yield entry
            return
        yield info

    @staticmethod
    def _entry_to_result(entry):
        if not entry:
            return None
        video_id = entry.get("id")
        link = entry.get("webpage_url") or entry.get("url")
        if link and not str(link).startswith("http") and video_id:
            link = f"https://www.youtube.com/watch?v={video_id}"
        elif not link and video_id:
            link = f"https://www.youtube.com/watch?v={video_id}"
        if not link:
            return None
        return {"title": entry.get("title") or "Unknown title", "link": str(link)}

    @property
    def media_title(self):
        return self._media_title

    def __setattr__(self, name, value):
        if name == "media_title":
            object.__setattr__(self, "_media_title", value)
            return
        super().__setattr__(name, value)

    def clear_collection(self):
        self.collection_results = []
        self.current_collection_index = 0
        self.collection_source = None

    def classify_collection_link(self, link):
        try:
            parsed = urlparse(link)
        except Exception:
            return None
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()
        if "youtube.com" in host or "youtu.be" in host:
            query = parse_qs(parsed.query)
            if "list" in query or "/playlist" in path:
                return "playlist"
            if "/channel/" in path or path.startswith("/@") or path.startswith("/c/") or path.startswith("/user/"):
                return "channel"
        return None

    def fetch_collection(self, link, max_items=100):
        collection_type = self.classify_collection_link(link)
        if collection_type == "playlist":
            return collection_type, self._fetch_playlist_videos(link, max_items=max_items)
        if collection_type == "channel":
            return collection_type, self._fetch_channel_videos(link, max_items=max_items)
        return None, []

    def _fetch_playlist_videos(self, link, max_items=100):
        try:
            with yt_dlp.YoutubeDL(self._base_ydl_opts(extract_flat=True, playlistend=max_items)) as ydl:
                info = ydl.extract_info(link, download=False)
        except Exception as exc:
            print(f"Error loading playlist videos: {exc}")
            return []
        results = []
        for entry in self._iter_entries(info or {}):
            item = self._entry_to_result(entry)
            if item:
                results.append(item)
            if len(results) >= max_items:
                break
        return results

    def _fetch_channel_videos(self, link, max_items=100):
        try:
            with yt_dlp.YoutubeDL(self._base_ydl_opts(extract_flat=True, playlistend=max_items)) as ydl:
                info = ydl.extract_info(link, download=False)
        except Exception as e:
            print(f"Error loading channel videos: {e}")
            return []
        results = []
        for entry in self._iter_entries(info or {}):
            item = self._entry_to_result(entry)
            if item:
                results.append(item)
            if len(results) >= max_items:
                break
        return results

    def _search(self, target, limit=50):
        results = []
        try:
            with yt_dlp.YoutubeDL(self._base_ydl_opts(extract_flat=True, playlistend=limit)) as ydl:
                info = ydl.extract_info(target, download=False)
            for entry in self._iter_entries(info or {}):
                item = self._entry_to_result(entry)
                if item:
                    results.append(item)
                if len(results) >= limit:
                    break
        except Exception as exc:
            print(f"yt-dlp search failed: {exc}")
        return results

    def search_youtube(self, query):
        """Search YouTube using yt-dlp's official ytsearch extractor."""
        return self._search(f"ytsearch50:{query}", limit=50)

    def search_ytmusic(self, query):
        """Search the YouTube Music Songs section using its supported search URL extractor."""
        target = f"https://music.youtube.com/search?q={quote_plus(query)}#songs"
        return self._search(target, limit=20)

    def update_filters(self):
        af_val = "scaletempo2"
        if self.is_stereo_wide:
            af_val += ",lavfi=[stereowiden=delay=4:crossfeed=0.3:drytx=0.8:dryrx=0.8,crystalizer=i=1.5,acompressor=threshold=-12dB:ratio=3:attack=5:release=50:makeup=2.5]"
        if self.is_stereo_echo:
            af_val += ",lavfi=[extrastereo=m=2.5]"
        if self.is_bass_boosted:
            af_val += ",bass=g=15:f=50"
        self.af = af_val
        
        # Apply quality and buffer settings
        try:
            b_val = float(self.audio_buffer)
            self['audio-buffer'] = b_val
        except:
            pass
            
        if self.audio_quality == 'Low':
            self['audio-samplerate'] = 44100
            self['audio-channels'] = 'stereo'
        elif self.audio_quality == 'Medium':
            self['audio-samplerate'] = 48000
            self['audio-channels'] = 'stereo'
        else:
            self['audio-samplerate'] = 48000
            self['audio-channels'] = 'auto'

    def get_real_vol(self):
        """Return the current mpv volume as a bounded integer."""
        max_volume = float(self.playback_config.get("max_volume", 150) or 150)
        try:
            current = float(self.volume or 0)
        except (TypeError, ValueError):
            current = 0.0
        return int(max(0.0, min(current, max_volume)))

    def smooth_vol_change(self, start_vol, end_vol, duration=0.8):
        steps = 15
        delay = duration / steps
        diff = end_vol - start_vol
        for i in range(1, steps + 1):
            curr = int(start_vol + (diff * (i / steps)))
            self['volume'] = curr
            time.sleep(delay)

    def play_stream(self, link):
        """Play a URL using yt-dlp, with a direct HTTP stream fallback for radio/stream URLs."""
        try:
            self.pause = False
            info = self._prefetch_cache.pop(link, None)
            if not info:
                try:
                    with self._ydl_lock:
                        info = self.ydl.extract_info(link, download=False)
                except Exception:
                    host = (urlparse(str(link)).hostname or "").lower()
                    if str(link).lower().startswith(("http://", "https://")) and not any(x in host for x in ("youtube.com", "youtu.be", "music.youtube.com")):
                        self.media_title = str(link)
                        self.is_playing = True
                        self.play(str(link))
                        self.current_link = str(link)
                        self.observe_property('idle-active', self._on_idle_active)
                        self.add_to_recent_history(self.media_title, self.current_link)
                        return
                    raise
            self.media_title = info.get('title') or "Unknown title"
            if self._requires_temp_download(info, link):
                temp_path = self._download_temp_media(info, link)
                self._cache_temp_file(link, temp_path, ttl_seconds=240)
                self.is_playing = True
                self.play(temp_path)
            else:
                direct_link = info.get('url')
                if not direct_link:
                    raise ValueError("No playable URL found for the requested link.")
                self.is_playing = True
                self.play(direct_link)
            self.current_link = link
            self.observe_property('idle-active', self._on_idle_active) 
            self.add_to_recent_history(self.media_title, link)

        except Exception as e:
            print(f"Error playing stream: {e}")
            self.is_playing = False
            raise e

    def fade_out_and_stop(self, duration=1.2, steps=12):
        if not self.is_playing:
            return
        try:
            original_volume = self.volume
        except Exception:
            original_volume = None
        try:
            start_volume = float(self.volume)
            step_delay = max(duration / max(steps, 1), 0.01)
            for i in range(steps):
                next_volume = max(start_volume * (1 - ((i + 1) / steps)), 0)
                self.volume = next_volume
                time.sleep(step_delay)
        except Exception:
            pass
        self.stop()
        if original_volume is not None:
            self.volume = original_volume

    def prefetch_stream_info(self, link):
        if link in self._prefetch_cache:
            return
        try:
            with self._ydl_lock:
                info = self.ydl.extract_info(link, download=False)
        except Exception as e:
            print(f"Error prefetching stream: {e}")
            return
        if info:
            self._prefetch_cache[link] = info

    def get_channel_link(self, link):
        try:
            with self._ydl_lock:
                info = self.ydl.extract_info(link, download=False)
        except Exception as e:
            print(f"Error fetching channel info: {e}")
            return None
        if not info:
            return None
        channel_url = info.get("channel_url") or info.get("uploader_url")
        if channel_url:
            return channel_url
        channel_id = info.get("channel_id")
        if channel_id:
            return f"https://www.youtube.com/channel/{channel_id}"
        uploader_id = info.get("uploader_id")
        if uploader_id:
            if uploader_id.startswith("@"):
                return f"https://www.youtube.com/{uploader_id}"
            return f"https://www.youtube.com/channel/{uploader_id}"
        return None

    def _normalize_channel_root(self, channel_link):
        try:
            parsed = urlparse(channel_link)
        except Exception:
            return channel_link.rstrip("/")
        path = parsed.path or ""
        suffixes = (
            "/videos",
            "/shorts",
            "/streams",
            "/live",
            "/playlists",
            "/community",
            "/featured",
        )
        for suffix in suffixes:
            if path.lower().endswith(suffix):
                path = path[: -len(suffix)]
                break
        base = parsed._replace(path=path, params="", query="", fragment="").geturl()
        return base.rstrip("/")

    def _extract_tab_entries(self, link, max_items=1):
        try:
            with yt_dlp.YoutubeDL(self._base_ydl_opts(extract_flat=True, playlistend=max_items)) as ydl:
                info = ydl.extract_info(link, download=False)
        except Exception as e:
            if "not currently live" not in str(e).lower():
                print(f"Error loading channel tab: {e}")
            return []
        entries = (info or {}).get("entries") or []
        if not entries and info and info.get("url"):
            entries = [info]
        return entries

    def get_first_playlist_link(self, tab_link):
        entries = self._extract_tab_entries(tab_link, max_items=1)
        if not entries:
            return None
        entry = entries[0]
        playlist_link = entry.get("url") or entry.get("webpage_url")
        playlist_id = entry.get("id")
        if playlist_link and not playlist_link.startswith("http"):
            if playlist_id:
                playlist_link = f"https://www.youtube.com/playlist?list={playlist_id}"
        if not playlist_link and playlist_id:
            playlist_link = f"https://www.youtube.com/playlist?list={playlist_id}"
        return playlist_link

    def get_channel_tabs(self, channel_link):
        base = self._normalize_channel_root(channel_link)
        if base.endswith("/"):
            base = base[:-1]
        candidates = [
            ("Home", base, "home"),
            ("Videos", f"{base}/videos", "videos"),
            ("Shorts", f"{base}/shorts", "shorts"),
            ("Live", f"{base}/live", "live"),
            ("Streams", f"{base}/streams", "streams"),
            ("Playlists", f"{base}/playlists", "playlists"),
        ]
        available = []
        for name, link, kind in candidates:
            if kind == "playlists":
                entries = self._extract_tab_entries(link, max_items=1)
                if not entries:
                    continue
                available.append({"name": name, "link": link, "kind": kind})
                continue
            entries = self._extract_tab_entries(link, max_items=1)
            if not entries:
                continue
            available.append({"name": name, "link": link, "kind": kind})
        return available

    def get_channel_playlists(self, tab_link, max_items=50):
        entries = self._extract_tab_entries(tab_link, max_items=max_items)
        flattened = []
        queue = list(entries)
        while queue:
            entry = queue.pop(0)
            nested = entry.get("entries")
            if isinstance(nested, list) and nested:
                queue.extend(nested)
                continue
            flattened.append(entry)
        results = []
        seen = set()
        for entry in flattened:
            playlist_id = entry.get("playlist_id") or entry.get("id")
            playlist_link = entry.get("url") or entry.get("webpage_url")
            if playlist_link:
                if not playlist_link.startswith("http"):
                    if playlist_id:
                        playlist_link = f"https://www.youtube.com/playlist?list={playlist_id}"
                else:
                    parsed = urlparse(playlist_link)
                    qs = parse_qs(parsed.query)
                    list_id = qs.get("list", [None])[0]
                    if list_id:
                        playlist_id = playlist_id or list_id
            if not playlist_link and playlist_id:
                playlist_link = f"https://www.youtube.com/playlist?list={playlist_id}"
            if not playlist_link:
                continue
            title = entry.get("title") or "Untitled playlist"
            key = (playlist_link, title)
            if key in seen:
                continue
            seen.add(key)
            results.append({"title": title, "link": playlist_link})
        return results

    def pause_stream(self):
        self.pause=True

    def seek_forward(self, amount):
        self.seek(amount, reference="relative")

    def seek_back(self, amount):
        try:
            amount=-amount
            self.seek(amount)
        except:
            raise(ValueError)

    def _on_idle_active(self, name, value):
        """Callback function for 'idle-active' property change."""
        if value is True and self.is_playing:
            self.is_playing = False

            # Stop observing idle-active to prevent further triggers 
            self.unobserve_property('idle-active', self._on_idle_active)

            if self.end_callback: 
                self.end_callback()

    def set_output_device(self):
        """Select mpv output by index or native device name; ``auto`` keeps mpv's default."""
        requested = self.config_handler.get_playback_config().get("output_device", "auto")
        if requested is None:
            return
        requested = str(requested).strip()
        if not requested or requested.lower() == "auto":
            return
        try:
            output_devices = list(self.audio_device_list or [])
        except Exception as exc:
            print(f"Unable to enumerate output devices: {exc}")
            return

        if requested.lstrip("-").isdigit():
            index = int(requested)
            if 0 <= index < len(output_devices):
                device_name = output_devices[index].get("name")
                if device_name:
                    self.audio_device = device_name
                    print(f"Output device set to: {device_name}")
                return
            print("Invalid output device index in config file; using mpv default.")
            return

        requested_lower = requested.casefold()
        for device in output_devices:
            name = str(device.get("name") or "")
            description = str(device.get("description") or "")
            if requested_lower in {name.casefold(), description.casefold()}:
                self.audio_device = name
                print(f"Output device set to: {name}")
                return
        print(f"Output device '{requested}' was not found; using mpv default.")

    def _requires_temp_download(self, info, link):
        extractor = (info or {}).get('extractor_key') or (info or {}).get('extractor') or ""
        if "tiktok" in extractor.lower():
            return True
        return "tiktok.com" in link or "vt.tiktok.com" in link


    def _download_temp_media(self, info, link):
        temp_dir = tempfile.mkdtemp(prefix="ttutil_stream_")
        ydl_opts = self._base_ydl_opts(noplaylist=True)
        ydl_opts.update({
            "format": "bestaudio/best",
            "skip_download": False,
            "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
        })
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(link, download=True)
            filename = ydl.prepare_filename(info_dict)
        return filename

    def _cache_temp_file(self, link, path, ttl_seconds=240):
        self._clear_temp_cache(link)
        timer = threading.Timer(ttl_seconds, self._clear_temp_cache, args=(link,))
        self._temp_cache[link] = {"path": path, "timer": timer, "expires_at": time.time() + ttl_seconds}
        timer.start()

    def _clear_temp_cache(self, link):
        cached = self._temp_cache.pop(link, None)
        if not cached:
            return
        timer = cached.get("timer")
        if timer:
            timer.cancel()
        path = cached.get("path")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
            try:
                parent_dir = os.path.dirname(path)
                if parent_dir and os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            except Exception:
                pass

    def get_cached_media(self, link):
        cached = self._temp_cache.get(link)
        if not cached:
            return None
        if cached.get("expires_at", 0) < time.time():
            self._clear_temp_cache(link)
            return None
        path = cached.get("path")
        if not path or not os.path.exists(path):
            self._clear_temp_cache(link)
            return None
        return path

    def clear_cache(self):
        """Clear prefetched metadata and temporary downloaded media."""
        prefetched = len(self._prefetch_cache)
        temporary = len(self._temp_cache)
        self._prefetch_cache.clear()
        for link in list(self._temp_cache):
            self._clear_temp_cache(link)
        return prefetched, temporary

    def cache_size_bytes(self):
        """Return the on-disk size of temporary cached media."""
        total = 0
        for cached in list(self._temp_cache.values()):
            path = cached.get("path")
            if path and os.path.isfile(path):
                try:
                    total += os.path.getsize(path)
                except OSError:
                    pass
        return total

    def close_player(self):
        try:
            self.prefetcher.close()
        except Exception:
            pass
        for link in list(self._temp_cache):
            self._clear_temp_cache(link)
        try:
            self.terminate()
        except Exception:
            pass

    def format_time(self, seconds):
        minutes = int(seconds // 60)
        hours = minutes // 60

        sec = round(seconds % 60, 2)

        if sec == 60:
            sec = 0
            minutes += 1

        if minutes == 60:
            minutes = 0
            hours += 1

        minutes %= 60  # Equivalent to minutes = minutes % 60
        return f"{hours:02d}:{minutes:02d}:{sec:05.2f}" 

    def add_to_recent_history(self, title, link):
        """Adds a played video to the recent history."""
        if len(self.recent_history) >= 32:
            self.recent_history.pop(next(iter(self.recent_history)))
        self.recent_history[title] = link

    def get_recent_history(self):
        """Returns the recent history as a formatted string."""
        if not self.recent_history:
            return "Recent history is empty."

        history_str = "Recent History:\n"
        for i, (title, link) in enumerate(self.recent_history.items()):
            history_str += f"{i+1}: {title}\n"
        return history_str

    def play_from_history(self, index):
        """Plays a video from the recent history based on its index."""
        if 1 <= index <= len(self.recent_history):
            title = list(self.recent_history.keys())[index - 1]
            link = self.recent_history[title]
            self.play_stream(link)
            return f"Playing: {title}"
        else:
            return "Invalid history index."
