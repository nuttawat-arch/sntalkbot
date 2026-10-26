"""Offline playlist discovery regression checks; no real YouTube call required."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_maintenance import load_player


class PlaylistDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_player()
        self.player = self.module.Player.__new__(self.module.Player)

    def test_extracts_only_playlist_results_and_preserves_result_order(self):
        extract = Mock(return_value={"entries": [
            {"id": "VIDEO123abc", "title": "Video", "url": "https://youtube.com/watch?v=VIDEO123abc"},
            {"id": "PL1234567890ABC", "title": "Playlist A", "ie_key": "YoutubePlaylist", "channel": "One"},
            {"id": "PL1234567890ABC", "title": "Duplicate", "ie_key": "YoutubePlaylist"},
            {"id": "PL0987654321XYZ", "title": "Playlist B", "ie_key": "YoutubePlaylist"},
        ]})
        self.player._fresh_ydl = lambda **_opts: nullcontext(SimpleNamespace(extract_info=extract))
        with patch.object(self.module.requests, "get") as request:
            results = self.player.search_playlists("thai hits", limit=10)
        self.assertEqual([item["title"] for item in results], ["Playlist A", "Playlist B"])
        self.assertEqual(results[0]["link"], "https://www.youtube.com/playlist?list=PL1234567890ABC")
        self.assertEqual(results[0]["channel"], "One")
        self.assertIn("search_query=thai+hits", extract.call_args.args[0])
        request.assert_not_called()

    def test_html_fallback_parses_only_playlist_metadata(self):
        document = {"contents": [
            {"playlistRenderer": {"playlistId": "PL1234567890ABC",
                                    "title": {"runs": [{"text": "เพลงไทย"}]},
                                    "shortBylineText": {"simpleText": "ผู้สร้าง"}, "videoCount": "20"}},
            {"videoRenderer": {"videoId": "video98765"}},
        ]}
        self.player._fresh_ydl = lambda **_opts: nullcontext(SimpleNamespace(extract_info=lambda *_a, **_k: {"entries": []}))
        response = SimpleNamespace(text="prefix var ytInitialData = " + json.dumps(document) + "; suffix",
                                   raise_for_status=lambda: None)
        with patch.object(self.module.requests, "get", return_value=response) as request:
            result = self.player.search_playlists("เพลงไทย")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "เพลงไทย")
        self.assertEqual(result[0]["channel"], "ผู้สร้าง")
        request.assert_called_once()

    def test_unsafe_or_empty_search_never_reaches_network(self):
        with patch.object(self.module.requests, "get") as request:
            self.assertEqual(self.player.search_playlists(""), [])
            self.assertEqual(self.player.search_playlists("a" * 501), [])
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
