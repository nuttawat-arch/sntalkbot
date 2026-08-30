import os
import re
import shutil
import base64
import binascii
import html
import mpv
import tempfile
import threading
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
import requests
import yt_dlp
from bot.prefetch import LinkPrefetcher

class Player(mpv.MPV):
    def __init__(self, config_handler, cookiefile=None, state_store=None, *args, **kwargs):
        # Linux/Docker launchers set TTUTIL_MPV_AO=pulse so MPV sends audio to
        # the virtual PulseAudio sink. Leave it unset on desktop systems to let
        # mpv choose the native audio output automatically.
        mpv_ao = os.getenv("TTUTIL_MPV_AO", "").strip()
        if mpv_ao and "ao" not in kwargs:
            kwargs["ao"] = mpv_ao
        super().__init__(ytdl=False, vo='null', video=False, *args, **kwargs)
        self.config_handler = config_handler
        self.state_store = state_store
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
        persist_queue = bool(self.playback_config.get("persist_queue", True))
        if self.state_store is not None:
            self.queue = self.state_store.queue()
            if not persist_queue:
                self.queue.clear()
                self.state_store.set_meta("queue_index", -1)
            try:
                restored_index = int(self.state_store.get_meta("queue_index", -1))
            except (TypeError, ValueError):
                restored_index = -1
            if restored_index >= len(self.queue) or restored_index < -1:
                restored_index = -1
            self.queue_index = restored_index
        else:
            self.queue = []
            self.queue_index = -1
        # Queue mutations may come from yt-dlp worker threads at the exact moment
        # mpv reports playback-end. Keep ordering deterministic across that boundary.
        self.queue_lock = threading.RLock()
        self.queue_transition = False
        self.playback_end_transition = False
        self.queue_history = []
        self.queue_mode = self.playback_config.get("queue_mode", False)
        # Normal (non-queue) discovery history is independent from search results.
        # Search navigation uses ,/. while n/b navigate YouTube/YouTube Music radio.
        self.radio_history = []
        self.radio_index = -1
        self.radio_candidates = []
        self.radio_source = "youtube"
        self.play_mode = int(self.playback_config.get("play_mode", 2) or 2)
        self._prefetch_cache = {}
        self._ydl_lock = threading.Lock()
        self.recent_history = {}
        self.end_callback = None
        self._intentional_stop = False
        self._end_dispatch_lock = threading.Lock()
        self._end_event_handled = True
        self._mpv_end_event_registered = False
        self.last_end_reason = None
        self.last_end_error = 0
        # A new external item can start before libmpv delivers the terminal event
        # for the previous one. Keep a monotonically increasing generation and a
        # short handoff grace so a late EOF/ERROR cannot terminate the fresh item.
        self.playback_epoch = 0
        self.active_playback_epoch = 0
        self.active_playback_started = 0.0
        self._terminal_handoff_grace = 0.85
        # python-mpv/libmpv reports asynchronous load/playback failures through
        # END_FILE. yt-dlp extraction can succeed even when mpv later rejects the
        # resolved media, so relying only on play() exceptions or idle-active can
        # leave a Queue item stalled. Register one permanent END_FILE listener and
        # keep idle-active only as a compatibility fallback for older bindings.
        try:
            self.event_callback('END_FILE')(self._on_end_file_event)
            self._mpv_end_event_registered = True
        except Exception as exc:
            print(f"MPV END_FILE callback unavailable; using idle-active fallback: {exc}")
        self._temp_cache = {}
        self.cookiefile = (
            cookiefile
            or os.getenv("SNTALKBOT_COOKIES_FILE", "").strip()
            or self.playback_config.get("cookiefile_path")
            or "/app/data/cookies.txt"
        )
        # Bundled legacy-project default. Persistent/user replacement always wins.
        self.bundled_cookiefile = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "defaults", "cookies.txt"
        )
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
        try:
            ytdlp_version = getattr(getattr(yt_dlp, "version", None), "__version__", "unknown")
            deno_path = shutil.which("deno") or "NOT FOUND"
            cookie_source = "user/default" if self._active_cookiefile() else "none"
            print(f"Media resolver ready: yt-dlp {ytdlp_version}; Deno: {deno_path}; cookies: {cookie_source}")
        except Exception:
            pass
        self.prefetcher = LinkPrefetcher(self.prefetch_stream_info, max_pending=5)

    @staticmethod
    def _cookiefile_has_records(path):
        """Return True only when a Netscape cookie file has at least one data row.

        TTUHelper 1.4.0 may create a header-only cookies.txt for a fresh instance.
        Treat that placeholder as empty so the bundled project default remains the
        effective fallback until a real user-exported cookie file replaces it.
        """
        if not path or not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.rstrip("\r\n")
                    if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
                        continue
                    if len(line.split("\t")) >= 7:
                        return True
        except OSError:
            return False
        return False

    def _active_cookiefile(self):
        if self.cookiefile and self._cookiefile_has_records(self.cookiefile):
            return self.cookiefile
        if self.bundled_cookiefile and self._cookiefile_has_records(self.bundled_cookiefile):
            return self.bundled_cookiefile
        return None

    def _base_ydl_opts(self, *, extract_flat=False, noplaylist=False, playlistend=None, use_cookies=True):
        """Return yt-dlp Python API options shared by search and playback.

        Deno is installed in the production image specifically for yt-dlp's
        current YouTube EJS challenge path.  Explicitly point the Python API at
        the executable so an environment/PATH difference cannot silently make
        YouTube formats disappear.  A no-cookie retry is available to callers
        because stale account cookies can break otherwise-public media.
        """
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
        active_cookiefile = self._active_cookiefile() if use_cookies else None
        if active_cookiefile:
            opts["cookiefile"] = active_cookiefile
        deno = shutil.which("deno")
        if deno:
            opts["js_runtimes"] = {"deno": {"path": deno}}
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
        result = {
            "title": entry.get("title") or "Unknown title",
            "link": str(link),
        }
        if video_id:
            result["id"] = str(video_id)
        uploader = entry.get("artist") or entry.get("uploader") or entry.get("channel")
        if uploader:
            result["artist"] = str(uploader)
        return result

    @property
    def media_title(self):
        return self._media_title

    def __setattr__(self, name, value):
        if name == "media_title":
            object.__setattr__(self, "_media_title", value)
            return
        if name == "queue_index":
            value = int(value)
            object.__setattr__(self, name, value)
            try:
                store = object.__getattribute__(self, "state_store")
                playback = object.__getattribute__(self, "playback_config")
            except Exception:
                store = None
                playback = {}
            if store is not None and bool(playback.get("persist_queue", True)):
                store.set_meta("queue_index", value)
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

    def fetch_collection_details(self, link, max_items=100):
        """Return ``(type, title, items)`` for YouTube/YouTube Music collections.

        ``fetch_collection`` remains as the backward-compatible two-value API.
        The title is used only for concise queue/session announcements.
        """
        collection_type = self.classify_collection_link(link)
        if collection_type == "playlist":
            title, items = self._fetch_playlist_details(link, max_items=max_items)
            return collection_type, title, items
        if collection_type == "channel":
            items = self._fetch_channel_videos(link, max_items=max_items)
            return collection_type, "channel", items
        return None, None, []

    def fetch_collection(self, link, max_items=100):
        collection_type, _title, items = self.fetch_collection_details(link, max_items=max_items)
        return collection_type, items

    def _fetch_playlist_details(self, link, max_items=100):
        try:
            with yt_dlp.YoutubeDL(self._base_ydl_opts(extract_flat=True, playlistend=max_items)) as ydl:
                info = ydl.extract_info(link, download=False)
        except Exception as exc:
            print(f"Error loading playlist videos: {exc}")
            return None, []
        title = str((info or {}).get("title") or "playlist")
        source = "ytmusic" if "music.youtube.com" in str(link).lower() else "youtube"
        results = []
        for entry in self._iter_entries(info or {}):
            item = self._entry_to_result(entry)
            if item:
                item.setdefault("collection_title", title)
                item.setdefault("collection_type", "playlist")
                item.setdefault("source", source)
                if source == "ytmusic" and item.get("id"):
                    item["link"] = f"https://music.youtube.com/watch?v={item['id']}"
                results.append(item)
            if len(results) >= max_items:
                break
        return title, results

    def _fetch_playlist_videos(self, link, max_items=100):
        _title, results = self._fetch_playlist_details(link, max_items=max_items)
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

    def _search_once(self, target, limit=50, *, use_cookies=True):
        results = []
        with yt_dlp.YoutubeDL(
            self._base_ydl_opts(extract_flat=True, playlistend=limit, use_cookies=use_cookies)
        ) as ydl:
            info = ydl.extract_info(target, download=False)
        for entry in self._iter_entries(info or {}):
            item = self._entry_to_result(entry)
            if item:
                results.append(item)
            if len(results) >= limit:
                break
        return results

    def _search(self, target, limit=50):
        """Search once with the effective cookie, then retry public media cleanly.

        This avoids one bad/stale cookie file turning every YouTube and YouTube
        Music search into an empty result while still preferring the user's cookie
        for account-gated content.
        """
        first_error = None
        try:
            results = self._search_once(target, limit=limit, use_cookies=True)
            if results:
                return results
        except Exception as exc:
            first_error = exc
        if self._active_cookiefile():
            try:
                results = self._search_once(target, limit=limit, use_cookies=False)
                if results:
                    print("yt-dlp search recovered without cookies")
                    return results
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                else:
                    print(f"yt-dlp no-cookie search retry failed: {exc}")
        if first_error is not None:
            print(f"yt-dlp search failed: {first_error}")
        return []

    def _tag_source(self, results, source):
        for item in results:
            item.setdefault("source", source)
        return results

    def search_youtube(self, query):
        """Search YouTube with independent extractor fallbacks.

        ``ytsearch:`` is the established API path and stays primary.  The normal
        YouTube search URL is a fallback, not a replacement, so an extractor
        rollout on either surface cannot disable both Queue Mode and normal play.
        """
        query = str(query or "").strip()
        if not query:
            return []
        results = self._search(f"ytsearch50:{query}", limit=50)
        if not results:
            target = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            results = self._search(target, limit=50)
        return self._tag_source(results, "youtube")

    def search_ytmusic(self, query):
        """Search YouTube Music, with a playable ID fallback via YouTube search.

        YouTube Music search has historically had extractor-specific regressions.
        If its search page returns no songs, reuse ordinary YouTube discovery only
        to obtain video IDs, then canonicalize those IDs back to music.youtube.com
        so ``pm`` remains a distinct YouTube Music intent.
        """
        query = str(query or "").strip()
        if not query:
            return []
        target = f"https://music.youtube.com/search?q={quote_plus(query)}#songs"
        results = self._search(target, limit=20)
        if not results:
            fallback = self._search(f"ytsearch20:{query}", limit=20)
            results = []
            for item in fallback:
                item = dict(item)
                video_id = self.video_id_from_result(item)
                if video_id:
                    item["id"] = video_id
                    item["link"] = f"https://music.youtube.com/watch?v={video_id}"
                    results.append(item)
        return self._tag_source(results, "ytmusic")

    @staticmethod
    def video_id_from_result(item):
        if not item:
            return None
        video_id = item.get("id")
        if video_id:
            return str(video_id)
        try:
            parsed = urlparse(str(item.get("link") or ""))
            if parsed.netloc.endswith("youtu.be"):
                return parsed.path.strip("/").split("/")[0] or None
            if "youtube.com" in parsed.netloc:
                return parse_qs(parsed.query).get("v", [None])[0]
        except Exception:
            return None
        return None

    def related_radio(self, seed, source=None, limit=30):
        """Return YouTube/YouTube Music radio items for ``seed``.

        This uses YouTube's own Mix/Radio playlist surface when yt-dlp can expose
        it. A metadata-based search is only a fallback for deployments where the
        generated radio playlist is unavailable without additional cookies/tokens.
        """
        seed = dict(seed or {})
        video_id = self.video_id_from_result(seed)
        source = source or seed.get("source") or "youtube"
        results = []
        if video_id:
            if source == "ytmusic":
                radio_id = f"RDAMVM{video_id}"
                target = f"https://music.youtube.com/watch?v={video_id}&list={radio_id}"
            else:
                target = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}&start_radio=1"
            results = self._search(target, limit=limit)
            self._tag_source(results, source)

        # Remove the seed and duplicates while preserving YouTube's returned order.
        seed_link = str(seed.get("link") or "")
        seed_id = video_id
        unique = []
        seen = set()
        for item in results:
            item_id = self.video_id_from_result(item)
            key = item_id or str(item.get("link") or "")
            if not key or key in seen or (seed_id and item_id == seed_id) or str(item.get("link") or "") == seed_link:
                continue
            seen.add(key)
            unique.append(item)
        if unique:
            return unique

        # Conservative fallback: still use YouTube/YouTube Music search, seeded by
        # title + artist. This is not claimed to reproduce the private recommender.
        title = str(seed.get("title") or self.media_title or "").strip()
        artist = str(seed.get("artist") or "").strip()
        query = " ".join(part for part in (title, artist) if part).strip()
        if not query:
            return []
        fallback = self.search_ytmusic(query) if source == "ytmusic" else self.search_youtube(query)
        unique = []
        seen = set()
        for item in fallback:
            item_id = self.video_id_from_result(item)
            key = item_id or str(item.get("link") or "")
            if not key or key in seen or (seed_id and item_id == seed_id) or str(item.get("link") or "") == seed_link:
                continue
            seen.add(key)
            unique.append(item)
            if len(unique) >= limit:
                break
        return unique

    def reset_radio_history(self, seed, source=None):
        seed = dict(seed or {})
        if not seed.get("link"):
            return
        seed.setdefault("title", self.media_title or "Unknown title")
        seed.setdefault("source", source or seed.get("source") or "youtube")
        self.radio_history = [seed]
        self.radio_index = 0
        self.radio_candidates = []
        self.radio_source = seed.get("source", "youtube")

    def clear_radio_history(self):
        self.radio_history = []
        self.radio_index = -1
        self.radio_candidates = []

    def update_filters(self):
        """Apply optional music effects through the current FFmpeg/libavfilter bridge.

        mpv already inserts scaletempo2 automatically when speed differs from
        1.0 and audio-pitch-correction is enabled, so the effect chain should
        contain only effects explicitly requested by the user.  The stereo
        filters require stereo input; aformat performs the conversion once
        before either stereo effect.
        """
        graph = []
        if self.is_stereo_wide or self.is_stereo_echo:
            graph.append("aformat=channel_layouts=stereo")
        if self.is_stereo_wide:
            # FFmpeg stereowiden: delay, feedback, crossfeed and drymix are the
            # supported current parameters.  Keep values moderate so widening
            # is audible without the old over-processed crystalizer/compressor
            # chain.
            graph.append("stereowiden=delay=12:feedback=0.25:crossfeed=0.20:drymix=0.85")
        if self.is_stereo_echo:
            # Historical config key kept for compatibility.  The effect itself
            # is Extra Stereo (channel-difference expansion), not an echo.
            graph.append("extrastereo=m=1.8:c=1")
        if self.is_bass_boosted:
            # Use FFmpeg's current bass/lowshelf filter through lavfi.  A
            # conservative +6 dB around 90 Hz gives useful bass lift while
            # reducing clipping risk compared with the legacy +15 dB preset.
            graph.append("bass=g=6:f=90:w=0.7")

        self.af = f"lavfi=[{','.join(graph)}]" if graph else ""

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

    @staticmethod
    def _stream_candidate_score(url):
        """Rank likely audio/radio stream URLs discovered inside a station webpage."""
        value = str(url or "").strip()
        low = value.lower()
        if not low.startswith(("http://", "https://")):
            return -1
        if any(low.endswith(ext) or (ext + "?") in low for ext in (
            ".mp3", ".aac", ".aacp", ".ogg", ".opus", ".m4a", ".wav",
            ".flac", ".m3u8", ".m3u", ".pls", ".asx", ".xspf",
        )):
            return 100
        score = 0
        if ";stream" in low:
            score += 90
        if any(token in low for token in (
            "/stream", "/listen", "/live", "icecast", "shoutcast",
            "radioplayer", "radio-player", "player/", "player?",
        )):
            score += 55
        parsed = urlparse(value)
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port and port not in (80, 443):
            score += 25
        if any(bad in low for bad in (
            ".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js",
            ".woff", ".woff2", ".ttf", ".ico", ".webp", ".pdf",
        )):
            score -= 100
        return score

    @staticmethod
    def _decode_embedded_text(value):
        """Decode common HTML/JavaScript URL escaping without executing page code."""
        text = html.unescape(str(value or ""))
        text = text.replace("\\/", "/")
        def repl_u(match):
            try:
                return chr(int(match.group(1), 16))
            except Exception:
                return match.group(0)
        text = re.sub(r"\\u([0-9a-fA-F]{4})", repl_u, text)
        text = re.sub(r"\\x([0-9a-fA-F]{2})", repl_u, text)
        return text

    @staticmethod
    def _looks_like_direct_stream(url):
        value = str(url or "").lower().split("#", 1)[0]
        path = value.split("?", 1)[0]
        if ";stream" in value:
            return True
        return path.endswith((
            ".mp3", ".aac", ".aacp", ".ogg", ".opus", ".m4a", ".wav",
            ".flac", ".m3u8",
        ))

    @staticmethod
    def _looks_like_playlist(url):
        path = str(url or "").lower().split("?", 1)[0].split("#", 1)[0]
        return path.endswith((".pls", ".m3u", ".asx", ".xspf"))

    @classmethod
    def _extract_radio_targets(cls, text, base_url):
        """Return prioritized, bounded targets discovered in HTML/JS/JSON/playlists.

        The resolver does not execute JavaScript.  It only recognizes common static
        player configuration forms, media/embed attributes, playlist files and
        escaped/encoded HTTP URLs.  Ordinary navigation links are deliberately not
        crawled, which keeps a non-radio website from turning into a site spider.
        """
        raw = cls._decode_embedded_text(text)
        targets = []
        seen = set()

        def add(value, *, bonus=0, follow=False, direct=False, kind="text"):
            value = cls._decode_embedded_text(value).strip().strip("'\"<>()[]{} ,")
            if not value or value.startswith(("data:", "javascript:", "#")):
                return
            if value.startswith("//"):
                scheme = urlparse(base_url).scheme or "https"
                value = f"{scheme}:{value}"
            absolute = urljoin(base_url, value)
            parsed = urlparse(absolute)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return
            if absolute in seen:
                return
            score = cls._stream_candidate_score(absolute)
            if score < 0:
                return
            seen.add(absolute)
            direct = bool(direct or cls._looks_like_direct_stream(absolute))
            follow = bool(follow or direct or cls._looks_like_playlist(absolute) or score >= 20)
            targets.append({
                "url": absolute,
                "score": score + int(bonus),
                "order": len(targets),
                "follow": follow,
                "direct": direct,
                "kind": kind,
            })

            # Player pages often put the real stream in a percent-encoded query
            # parameter (for example ?stream=https%3A%2F%2Fhost%2Flive).
            for values in parse_qs(parsed.query, keep_blank_values=False).values():
                for nested in values[:4]:
                    nested = unquote(str(nested or ""))
                    if nested.startswith(("http://", "https://", "//")):
                        add(nested, bonus=70, follow=True, kind="query")

        class DiscoveryParser(HTMLParser):
            def handle_starttag(self, tag, attrs):
                tag = str(tag or "").lower()
                data = {str(k or "").lower(): (v or "") for k, v in attrs if k}
                if tag in {"audio", "video", "source"}:
                    for key in ("src", "data-src", "data-url", "data-stream", "data-stream-url"):
                        if data.get(key):
                            add(data[key], bonus=140, follow=True, direct=True, kind="media")
                elif tag in {"iframe", "embed"}:
                    for key in ("src", "data-src", "data-url"):
                        if data.get(key):
                            add(data[key], bonus=100, follow=True, kind="embed")
                elif tag == "object" and data.get("data"):
                    add(data["data"], bonus=90, follow=True, kind="embed")
                elif tag == "a" and data.get("href"):
                    # Follow only stream/player-looking links, never ordinary site nav.
                    href = data["href"]
                    absolute = urljoin(base_url, cls._decode_embedded_text(href))
                    if cls._stream_candidate_score(absolute) >= 20 or cls._looks_like_playlist(absolute):
                        add(href, bonus=25, follow=True, kind="link")
                elif tag == "meta":
                    equiv = data.get("http-equiv", "").lower()
                    content = data.get("content", "")
                    if equiv == "refresh" and content:
                        match = re.search(r"(?i)url\s*=\s*['\"]?([^'\";]+)", content)
                        if match:
                            add(match.group(1), bonus=80, follow=True, kind="meta-refresh")

                # Generic data-* player attributes are common in WordPress/radio widgets.
                for key, value in data.items():
                    if not value:
                        continue
                    if any(token in key for token in ("stream", "audio", "radio", "source", "media")):
                        add(value, bonus=100, follow=True, kind="data-attr")

        if "<" in raw and ">" in raw:
            try:
                parser = DiscoveryParser(convert_charrefs=True)
                parser.feed(raw)
            except Exception:
                pass

        # PLS / M3U files.
        for match in re.finditer(r"(?im)^\s*File\d+\s*=\s*([^\s]+)", raw):
            add(match.group(1), bonus=150, follow=True, direct=True, kind="playlist")
        is_m3u_text = raw.lstrip().upper().startswith("#EXTM3U")
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("http://", "https://", "//")):
                add(line, bonus=120, follow=True, direct=True, kind="playlist")
            elif is_m3u_text and "=" not in line and len(line) <= 2048:
                add(line, bonus=120, follow=True, direct=True, kind="playlist")

        # Legacy ASX/XSPF radio playlists. Absolute URLs would also be found by
        # the literal scanner; these patterns additionally preserve relative refs.
        for match in re.finditer(r"""(?is)<ref[^>]+href\s*=\s*["']([^"']+)["']""", raw):
            add(match.group(1), bonus=140, follow=True, direct=True, kind="playlist")
        for match in re.finditer(r"(?is)<location[^>]*>\s*([^<]+)\s*</location>", raw):
            add(match.group(1), bonus=140, follow=True, direct=True, kind="playlist")

        # Common JS/JSON player configuration keys.
        keyed = (
            r"(?is)(?:stream(?:_?url)?|audio(?:_?url)?|radio(?:_?url)?|source|src|file|url|playlist)"
            r"\s*[=:]\s*[\"']([^\"']+)[\"']"
        )
        for match in re.finditer(keyed, raw):
            add(match.group(1), bonus=170, follow=True, kind="config")

        # A small, safe atob() recognizer handles static base64 player configs.
        for match in re.finditer(r"(?is)atob\(\s*['\"]([A-Za-z0-9+/=_-]{12,4096})['\"]\s*\)", raw):
            token = match.group(1)
            try:
                padded = token + ("=" * (-len(token) % 4))
                decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
            except (ValueError, UnicodeError, binascii.Error):
                continue
            for url_match in re.finditer(r"https?://[^\s\"'<>\\]+", decoded, flags=re.I):
                add(url_match.group(0), bonus=100, follow=True, kind="base64-config")

        # Last resort: literal HTTP URLs in inline scripts/JSON.  They are ranked
        # but only followed when the URL itself looks stream/player related.
        for match in re.finditer(r"https?://[^\s\"'<>\\]+", raw, flags=re.I):
            add(match.group(0), bonus=0, kind="literal")

        targets.sort(key=lambda item: (-item["score"], item["order"]))
        return targets

    @classmethod
    def _extract_stream_candidates(cls, text, base_url):
        """Compatibility helper returning ordered URLs only."""
        return [item["url"] for item in cls._extract_radio_targets(text, base_url)]

    def _resolve_radio_webpage(self, link, *, max_depth=3, max_fetches=20, max_seconds=18.0):
        """Resolve a station homepage/embed/playlist to a direct audio stream.

        yt-dlp remains the first resolver in play_stream().  This bounded crawler
        is only a fallback for ordinary HTTP(S) pages that yt-dlp cannot turn into
        a playable URL.  It never executes JavaScript and never follows ordinary
        website navigation links.
        """
        start = str(link or "").strip()
        if not start.lower().startswith(("http://", "https://")):
            return None
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 SNTalkBot-RadioResolver/2.0",
            "Accept": "text/html,application/xhtml+xml,application/json,audio/*,application/vnd.apple.mpegurl,audio/x-mpegurl,*/*;q=0.5",
            "Icy-MetaData": "1",
        }
        visited = set()
        queue = [(start, 0, None)]
        best_title = None
        fetches = 0
        embedded_ydl_attempts = 0
        max_embedded_ydl_attempts = 3
        deadline = time.monotonic() + max(float(max_seconds), 1.0)
        playlist_types = {
            "audio/x-scpls", "application/pls+xml", "audio/x-mpegurl",
            "audio/mpegurl", "application/x-mpegurl",
        }

        while queue and fetches < max_fetches and time.monotonic() < deadline:
            current, depth, referer = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            fetches += 1
            request_headers = dict(headers)
            if referer:
                request_headers["Referer"] = referer
            remaining = max(deadline - time.monotonic(), 0.5)
            read_timeout = min(8.0, max(1.0, remaining))
            try:
                response = requests.get(
                    current,
                    headers=request_headers,
                    timeout=(4, read_timeout),
                    allow_redirects=True,
                    stream=True,
                )
                response.raise_for_status()
            except Exception:
                continue

            final_url = str(response.url or current)
            content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            icy_name = str(response.headers.get("icy-name") or "").strip()
            if icy_name and not best_title:
                best_title = icy_name

            # Strong URL/ICY signals let us avoid reading an endless stream body
            # when a radio server uses a generic content-type.
            if (
                (icy_name and content_type in {"", "application/octet-stream", "binary/octet-stream"})
                or (self._looks_like_direct_stream(final_url) and content_type not in {"text/html", "application/xhtml+xml", "application/json"})
            ):
                response.close()
                return {"url": final_url, "title": best_title or final_url, "referer": referer}

            if (content_type.startswith("audio/") and content_type not in playlist_types) or content_type in {
                "application/ogg", "application/vnd.apple.mpegurl",
            }:
                response.close()
                return {"url": final_url, "title": best_title or final_url, "referer": referer}

            try:
                chunks = []
                total = 0
                for chunk in response.iter_content(chunk_size=16384):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= 768 * 1024 or time.monotonic() >= deadline:
                        break
                payload = b"".join(chunks)
                encoding = response.encoding or "utf-8"
            finally:
                response.close()

            text = payload.decode(encoding, errors="replace")
            if not best_title:
                title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
                if title_match:
                    best_title = re.sub(r"\s+", " ", html.unescape(title_match.group(1))).strip()

            # An HLS manifest is itself the stable playable URL. Do not mistake
            # individual media segments inside it for separate station streams.
            upper_text = text.lstrip().upper()
            if upper_text.startswith("#EXTM3U") and "#EXT-X-" in upper_text[:65536]:
                return {"url": final_url, "title": best_title or final_url, "referer": referer}

            targets = self._extract_radio_targets(text, final_url)
            for target in targets:
                candidate = target["url"]
                if target["direct"] and not self._looks_like_playlist(candidate):
                    return {
                        "url": candidate,
                        "title": best_title or candidate,
                        "referer": final_url,
                    }

            # If the page delegates playback to an iframe/embed, give yt-dlp a
            # few bounded chances on those player URLs. The homepage Generic
            # Extractor may be unsupported while the embedded provider has a
            # dedicated yt-dlp extractor. Never do this for ordinary navigation.
            if (
                embedded_ydl_attempts < max_embedded_ydl_attempts
                and hasattr(self, "ydl")
                and hasattr(self, "_ydl_lock")
                and time.monotonic() < deadline
            ):
                for target in targets:
                    if target.get("kind") != "embed":
                        continue
                    embedded_ydl_attempts += 1
                    candidate = target["url"]
                    try:
                        with self._ydl_lock:
                            embedded_info = self.ydl.extract_info(candidate, download=False)
                        embedded_url = (embedded_info or {}).get("url")
                        if embedded_url:
                            return {
                                "url": str(embedded_url),
                                "title": (embedded_info or {}).get("title") or best_title or candidate,
                                "referer": final_url,
                            }
                    except Exception:
                        pass
                    if embedded_ydl_attempts >= max_embedded_ydl_attempts or time.monotonic() >= deadline:
                        break

            if depth < max_depth:
                followed = 0
                for target in targets:
                    candidate = target["url"]
                    if not target["follow"] or candidate in visited:
                        continue
                    queue.append((candidate, depth + 1, final_url))
                    followed += 1
                    if followed >= 10:
                        break
        return None

    def _arm_end_detection(self):
        """Arm exactly one terminal callback for a new external playback generation."""
        with self._end_dispatch_lock:
            self.playback_epoch = int(getattr(self, "playback_epoch", 0) or 0) + 1
            self.active_playback_epoch = self.playback_epoch
            self.active_playback_started = time.monotonic()
            self._intentional_stop = False
            self._end_event_handled = False
            self.last_end_reason = None
            self.last_end_error = 0
            return self.active_playback_epoch

    def _cancel_end_detection(self):
        """Disarm terminal handling after a synchronous load failure."""
        with self._end_dispatch_lock:
            self._end_event_handled = True

    def _dispatch_end_once(self, reason="eof", error=0):
        """Dispatch one natural/error playback end, deduplicating mpv events.

        END_FILE and the legacy idle-active observer can both arrive for one
        item. A lock/armed bit prevents double queue advancement. Intentional
        stop/restart events are never treated as completed media.
        """
        with self._end_dispatch_lock:
            if self._intentional_stop or self._end_event_handled:
                return False
            self._end_event_handled = True
            self.last_end_reason = str(reason or "eof")
            try:
                self.last_end_error = int(error or 0)
            except (TypeError, ValueError):
                self.last_end_error = 0
        # Hold the transition flag across the callback so a concurrent Queue
        # append cannot mistake this tiny end boundary for an idle fresh Queue.
        self.playback_end_transition = True
        try:
            self.is_playing = False
            if not self._mpv_end_event_registered:
                try:
                    self.unobserve_property('idle-active', self._on_idle_active)
                except Exception:
                    pass
            if self.end_callback:
                self.end_callback()
        finally:
            self.playback_end_transition = False
        return True

    def _terminal_event_looks_stale(self):
        """Return True when a late terminal event belongs to the previous item.

        During stop->play handoff libmpv may deliver the old EOF/ERROR after the
        new file is already active. There is no stable media-id on every python-mpv
        binding, so correlate the event with the current transport: inside the short
        handoff window, an END_FILE while mpv reports *not idle* cannot describe the
        newly armed item and must be ignored. A genuinely broken new item becomes
        idle, so its immediate ERROR is still handled and retried/skipped normally.
        """
        grace = float(getattr(self, "_terminal_handoff_grace", 0.85) or 0.85)
        try:
            age = max(0.0, time.monotonic() - float(getattr(self, "active_playback_started", 0.0) or 0.0))
        except Exception:
            age = grace + 1.0
        if age > grace:
            return False
        try:
            return bool(self.idle_active) is False
        except Exception:
            return False

    def _on_end_file_event(self, event):
        """Handle libmpv END_FILE; ERROR means the current item is unplayable.

        libmpv reasons: EOF=0, RESTARTED=1, ABORTED=2, QUIT=3, ERROR=4,
        REDIRECT=5. Only EOF/ERROR represent a terminal item for our external
        queue. ABORTED/RESTARTED are expected during explicit transport changes.
        """
        data = getattr(event, "data", None)
        reason = getattr(data, "reason", None)
        error = getattr(data, "error", 0)
        try:
            reason = int(reason)
        except (TypeError, ValueError):
            return
        if reason not in (0, 4):
            return
        if self._terminal_event_looks_stale():
            print("Ignoring stale MPV END_FILE from previous playback generation")
            return
        if reason == 4:
            if self._dispatch_end_once("error", error):
                print(f"MPV playback error for current item (error={error})")
        else:
            self._dispatch_end_once("eof", error)

    def _play_resolved_radio(self, link):
        resolved = self._resolve_radio_webpage(link)
        if not resolved:
            return False
        direct = resolved.get("url")
        if not direct:
            return False
        self.media_title = resolved.get("title") or str(link)
        self._arm_end_detection()
        self.is_playing = True
        try:
            self.play(str(direct))
        except Exception:
            self._cancel_end_detection()
            self.is_playing = False
            raise
        self.current_link = str(link)
        if not self._mpv_end_event_registered:
            self.observe_property('idle-active', self._on_idle_active)
        self.add_to_recent_history(self.media_title, self.current_link)
        return True


    @staticmethod
    def _canonical_youtube_playback_candidates(link):
        value = str(link or "").strip()
        candidates = [value] if value else []
        try:
            parsed = urlparse(value)
            host = (parsed.hostname or "").lower()
            if host == "music.youtube.com":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
                if video_id:
                    normal = f"https://www.youtube.com/watch?v={video_id}"
                    if normal not in candidates:
                        candidates.append(normal)
        except Exception:
            pass
        return candidates

    def _extract_play_info_resilient(self, link):
        """Extract playable metadata with bounded URL/cookie fallbacks.

        Keep the requested link as the public/history identity.  The fallback
        candidate is only an extraction transport detail and is never exposed as
        a source change to the caller.
        """
        errors = []
        candidates = self._canonical_youtube_playback_candidates(link)
        if not candidates:
            candidates = [str(link or "")]
        has_cookie = bool(self._active_cookiefile())
        for candidate in candidates:
            for use_cookies in ((True, False) if has_cookie else (True,)):
                try:
                    if candidate == str(link) and use_cookies:
                        info = self.ydl.extract_info(candidate, download=False)
                    else:
                        with yt_dlp.YoutubeDL(
                            self._base_ydl_opts(noplaylist=True, use_cookies=use_cookies)
                        ) as ydl:
                            info = ydl.extract_info(candidate, download=False)
                    if info:
                        if candidate != str(link):
                            print("yt-dlp playback recovered through canonical YouTube URL")
                        elif not use_cookies:
                            print("yt-dlp playback recovered without cookies")
                        return info
                except Exception as exc:
                    errors.append((candidate, use_cookies, exc))
        if errors:
            candidate, use_cookies, exc = errors[-1]
            mode = "cookies" if use_cookies else "no-cookies"
            raise RuntimeError(f"yt-dlp extraction failed ({mode}, {candidate}): {exc}") from exc
        raise RuntimeError("yt-dlp extraction returned no playable metadata")

    def play_stream(self, link):
        """Play a URL using yt-dlp, with a direct HTTP stream fallback for radio/stream URLs."""
        try:
            self.pause = False
            info = self._prefetch_cache.pop(link, None)
            if not info:
                try:
                    with self._ydl_lock:
                        # A prefetch worker may have been extracting this exact URL
                        # while play_stream() waited for the shared yt-dlp lock.
                        # Re-check after acquiring the lock so we consume that fresh
                        # result instead of paying for a duplicate extraction.
                        info = self._prefetch_cache.pop(link, None)
                        if not info:
                            info = self._extract_play_info_resilient(link)
                except Exception:
                    host = (urlparse(str(link)).hostname or "").lower()
                    if str(link).lower().startswith(("http://", "https://")) and not any(x in host for x in ("youtube.com", "youtu.be", "music.youtube.com")):
                        if self._play_resolved_radio(link):
                            return
                    raise
            self.media_title = info.get('title') or "Unknown title"
            if self._requires_temp_download(info, link):
                temp_path = self._download_temp_media(info, link)
                self._cache_temp_file(link, temp_path, ttl_seconds=240)
                self._arm_end_detection()
                self.is_playing = True
                try:
                    self.play(temp_path)
                except Exception:
                    self._cancel_end_detection()
                    self.is_playing = False
                    raise
            else:
                direct_link = info.get('url')
                if not direct_link:
                    host = (urlparse(str(link)).hostname or "").lower()
                    if str(link).lower().startswith(("http://", "https://")) and not any(x in host for x in ("youtube.com", "youtu.be", "music.youtube.com")):
                        if self._play_resolved_radio(link):
                            return
                    raise ValueError("No playable URL found for the requested link.")
                self._arm_end_detection()
                self.is_playing = True
                try:
                    self.play(direct_link)
                except Exception:
                    self._cancel_end_detection()
                    self.is_playing = False
                    raise
            self.current_link = link
            if not self._mpv_end_event_registered:
                self.observe_property('idle-active', self._on_idle_active)
            self.add_to_recent_history(self.media_title, link)

        except Exception as e:
            print(f"Error playing stream: {e}")
            self._cancel_end_detection()
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
        self.stop_transport()
        if original_volume is not None:
            self.volume = original_volume

    def prefetch_stream_info(self, link):
        if link in self._prefetch_cache:
            return
        try:
            with self._ydl_lock:
                # Playback may have populated the cache while this worker waited.
                if link in self._prefetch_cache:
                    return
                info = self._extract_play_info_resilient(link)
                # Commit while still holding the same yt-dlp lock.  Otherwise
                # playback can acquire the lock in the tiny window after
                # extract_info() returns but before this worker stores the cache,
                # causing the next queue item to be extracted a second time.
                if info:
                    self._prefetch_cache[link] = info
        except Exception as e:
            print(f"Error prefetching stream: {e}")
            return

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


    def stop_transport(self):
        """Stop mpv intentionally without treating END_FILE/idle as completion."""
        with self._end_dispatch_lock:
            self._intentional_stop = True
            self._end_event_handled = True
        if not self._mpv_end_event_registered:
            try:
                self.unobserve_property('idle-active', self._on_idle_active)
            except Exception:
                pass
        self.is_playing = False
        try:
            super().stop()
        except Exception:
            # python-mpv may surface stop through command() on older bindings.
            try:
                self.command('stop')
            except Exception:
                pass

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
        """Compatibility fallback when python-mpv END_FILE callbacks are unavailable."""
        if value is not True:
            return
        if self._intentional_stop:
            self.is_playing = False
            try:
                self.unobserve_property('idle-active', self._on_idle_active)
            except Exception:
                pass
            return
        if self._terminal_event_looks_stale():
            return
        self._dispatch_end_once("idle", 0)

    def transport_is_active(self):
        """Best-effort real mpv transport state, independent of our callback flag."""
        if bool(self.is_playing) or bool(getattr(self, "pause", False)):
            return True
        try:
            return not bool(self.idle_active)
        except Exception:
            return False

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
