import os
import re
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
        active_cookiefile = None
        if self.cookiefile and self._cookiefile_has_records(self.cookiefile):
            active_cookiefile = self.cookiefile
        elif self.bundled_cookiefile and self._cookiefile_has_records(self.bundled_cookiefile):
            active_cookiefile = self.bundled_cookiefile
        if active_cookiefile:
            opts["cookiefile"] = active_cookiefile
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

    def _tag_source(self, results, source):
        for item in results:
            item.setdefault("source", source)
        return results

    def search_youtube(self, query):
        """Search YouTube using yt-dlp's official ytsearch extractor."""
        return self._tag_source(self._search(f"ytsearch50:{query}", limit=50), "youtube")

    def search_ytmusic(self, query):
        """Search the YouTube Music Songs section using its supported search URL extractor."""
        target = f"https://music.youtube.com/search?q={quote_plus(query)}#songs"
        return self._tag_source(self._search(target, limit=20), "ytmusic")

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

    def _play_resolved_radio(self, link):
        resolved = self._resolve_radio_webpage(link)
        if not resolved:
            return False
        direct = resolved.get("url")
        if not direct:
            return False
        self.media_title = resolved.get("title") or str(link)
        self.is_playing = True
        self.play(str(direct))
        self.current_link = str(link)
        self.observe_property('idle-active', self._on_idle_active)
        self.add_to_recent_history(self.media_title, self.current_link)
        return True

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
                            info = self.ydl.extract_info(link, download=False)
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
                self.is_playing = True
                self.play(temp_path)
            else:
                direct_link = info.get('url')
                if not direct_link:
                    host = (urlparse(str(link)).hostname or "").lower()
                    if str(link).lower().startswith(("http://", "https://")) and not any(x in host for x in ("youtube.com", "youtu.be", "music.youtube.com")):
                        if self._play_resolved_radio(link):
                            return
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
                # Playback may have populated the cache while this worker waited.
                if link in self._prefetch_cache:
                    return
                info = self.ydl.extract_info(link, download=False)
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
            # Mark the whole mpv idle transition before exposing is_playing=False.
            # Queue additions can arrive from another TeamTalk/thread-pool thread
            # at this exact boundary; without this guard a newly appended item can
            # be mistaken for a fresh idle queue and jump ahead of older entries.
            self.playback_end_transition = True
            try:
                self.is_playing = False

                # Stop observing idle-active to prevent further triggers.
                self.unobserve_property('idle-active', self._on_idle_active)

                if self.end_callback:
                    self.end_callback()
            finally:
                self.playback_end_transition = False

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
