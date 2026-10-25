"""Offline regression tests; no TeamTalk connection or account is used."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace, ModuleType
from unittest.mock import patch
import importlib.util
import os
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot.cookie_policy import newest_cookie, cookie_records
from bot.maintenance import CacheMaintenance, validate_schedule
from bot.state_store import StateStore

COOKIE = '# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\ttest-session\n'


def load_player():
    mpv = ModuleType('mpv'); mpv.MPV = type('MPV', (), {})
    yt = ModuleType('yt_dlp')
    with patch.dict(sys.modules, {'mpv': mpv, 'yt_dlp': yt}):
        spec = importlib.util.spec_from_file_location('_tested_player', ROOT / 'bot/player.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class CookieTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.paths = [Path(self.temp.name) / name for name in ('local', 'shared', 'bundled')]
        for i, p in enumerate(self.paths):
            p.write_text(COOKIE + f'# source {i}\n'); os.utime(p, (100+i, 100+i))

    def test_newest_bundled_beats_old_instance(self):
        self.assertEqual(newest_cookie(*self.paths), str(self.paths[2]))

    def test_shared_replacement_beats_bundled(self):
        os.utime(self.paths[1], (1000, 1000))
        self.assertEqual(newest_cookie(*self.paths), str(self.paths[1]))

    def test_new_individual_override(self):
        os.utime(self.paths[0], (1000, 1000))
        self.assertEqual(newest_cookie(*self.paths), str(self.paths[0]))

    def test_fresh_copy_of_old_bootstrap_is_not_new_export(self):
        self.paths[0].write_bytes(self.paths[2].read_bytes())
        os.utime(self.paths[1], (1000, 1000))
        self.assertEqual(newest_cookie(*self.paths), str(self.paths[1]))

    def test_expired_and_placeholder_rejected(self):
        self.paths[0].write_text(COOKIE.replace('\t0\t', '\t1\t'))
        self.paths[1].write_text('# Netscape HTTP Cookie File\n')
        self.assertFalse(cookie_records(self.paths[0])); self.assertFalse(cookie_records(self.paths[1]))
        self.assertEqual(newest_cookie(*self.paths), str(self.paths[2]))

    def test_http_only_bom_and_crlf(self):
        self.paths[0].write_text('\ufeff' + COOKIE.replace('.youtube.com', '#HttpOnly_.youtube.com').replace('\n', '\r\n'))
        self.assertTrue(cookie_records(self.paths[0]))

    def test_snapshot_never_changes_published_session(self):
        module = load_player(); player = module.Player.__new__(module.Player)
        source = self.paths[0]; snapshots = []
        player._base_ydl_opts = lambda **kw: {'cookiefile': str(source)}
        class FakeYDL:
            def __init__(self, opts): self.path = Path(opts['cookiefile']); snapshots.append(self.path)
            def __enter__(self): return self
            def __exit__(self, *args): self.path.write_text('jar rewritten by yt-dlp')
        module.yt_dlp.YoutubeDL = FakeYDL
        before = source.read_bytes()
        with player._fresh_ydl() as client:
            self.assertEqual(client.path.read_bytes(), before)
            self.assertNotEqual(client.path, source)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse(snapshots[0].exists())
        source.write_text(COOKIE + '# latest upload\n')
        with player._fresh_ydl() as client:
            self.assertIn('# latest upload', client.path.read_text())


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = StateStore(Path(self.temp.name) / 'state.sqlite3'); self.addCleanup(self.store.close)
        self.store.queue().append({'title': 'Keep me', 'link': 'https://example.test/song'})
        self.store.save_favorites([{'title': 'Favorite', 'link': 'https://example.test/favorite'}])
        self.calls = []
        self.player = SimpleNamespace(playback_config={'cache_cleanup_time': '00:00', 'cache_cleanup_timezone': 'Asia/Bangkok', 'cache_cleanup_sound': ''}, clear_cache=lambda: self.calls.append(True) or (2, 3))
        self.bot = SimpleNamespace(player=self.player, state_store=self.store)
        self.worker = CacheMaintenance(self.bot)

    def at(self, day, hour=0, minute=0):
        return datetime(2026, 10, day, hour, minute, tzinfo=ZoneInfo('Asia/Bangkok'))

    def test_daily_once_across_restart(self):
        self.assertTrue(self.worker.tick(self.at(26)))
        self.assertFalse(CacheMaintenance(self.bot).tick(self.at(26, 12)))
        self.assertTrue(self.worker.tick(self.at(27)))
        self.assertEqual(len(self.calls), 2)

    def test_playlist_and_favorites_survive(self):
        self.worker.tick(self.at(26))
        self.assertEqual(self.store.queue_count(), 1)
        self.assertEqual(len(self.store.load_favorites()), 1)
        self.assertIn('playlist_preserved', self.store.get_meta('cache_cleanup_result'))

    def test_custom_time_and_disabled(self):
        self.player.playback_config['cache_cleanup_time'] = '02:30'
        self.assertFalse(self.worker.tick(self.at(26, 2, 29)))
        self.assertTrue(self.worker.tick(self.at(26, 2, 30)))
        self.player.playback_config['cache_cleanup_enabled'] = False
        self.assertFalse(self.worker.tick(self.at(27, 3)))

    def test_failed_cleanup_is_retried_not_marked_done(self):
        def fail(): raise OSError('injected failure')
        self.player.clear_cache = fail
        with self.assertRaises(OSError): self.worker.tick(self.at(26))
        self.assertIsNone(self.store.get_meta('cache_cleanup_day'))
        self.assertFalse(self.worker.lock.locked())

    def test_sound_cannot_escape_instance(self):
        outside = Path(self.temp.name) / 'outside.mp3'; outside.write_bytes(b'not audio')
        data = Path(self.temp.name) / 'data'; data.mkdir()
        self.player.playback_config['cache_cleanup_sound'] = '../outside.mp3'
        with patch.dict(os.environ, {'TTUTIL_DATA_DIR': str(data)}):
            self.worker._play_sound()  # Must return before importing real mpv.
        self.assertTrue(outside.exists())

    def test_invalid_time_and_timezone(self):
        for clock, tz in [('24:00', 'UTC'), ('1:30', 'UTC'), ('00:00', 'Not/AZone')]:
            with self.assertRaises((ValueError, KeyError)): validate_schedule(clock, tz)

    def test_real_clear_cache_keeps_current_file_and_queue(self):
        module = load_player(); player = module.Player.__new__(module.Player)
        current = Path(self.temp.name) / 'current.mp3'; current.write_bytes(b'current')
        old = Path(self.temp.name) / 'old.mp3'; old.write_bytes(b'old')
        player._ydl_lock = threading.Lock(); player._prefetch_cache = {'next': {'url': 'stale'}}
        player._prefetch_times = {}; player.prefetcher = SimpleNamespace(clear=lambda: None)
        player.current_link = 'current'; player.is_playing = True
        player._temp_cache = {'current': {'path': str(current)}, 'old': {'path': str(old)}}
        player.queue = self.store.queue()
        self.assertEqual(player.clear_cache(), (1, 1))
        self.assertTrue(current.exists()); self.assertFalse(old.exists())
        self.assertEqual(len(player.queue), 1)

    def test_cleanup_sound_preserves_running_music(self):
        from bot import maintenance as maintenance_module
        audio = Path(self.temp.name) / 'sounds'; audio.mkdir()
        (audio / 'cache-cleanup.mp3').write_bytes(b'fixture')
        self.player.playback_config['cache_cleanup_sound'] = 'sounds/cache-cleanup.mp3'
        self.player.transport_is_active = lambda: True
        tx = []
        self.bot.enableVoiceTransmission = tx.append
        self.bot.player_cog = SimpleNamespace(_teamtalk_voice_tx_active=lambda: False)
        sound = SimpleNamespace(idle_active=True, play=lambda path: None, terminate=lambda: None)
        fake_mpv = ModuleType('mpv'); fake_mpv.MPV = lambda **kw: sound
        with patch.dict(os.environ, {'TTUTIL_DATA_DIR': self.temp.name}), patch.dict(sys.modules, {'mpv': fake_mpv}), patch.object(maintenance_module.time, 'monotonic', side_effect=[0,2,2]):
            self.worker._play_sound()
        self.assertEqual(tx, [True])

    def test_prefetch_capacity_is_global_across_schedules(self):
        from bot.prefetch import LinkPrefetcher
        entered = threading.Event(); release = threading.Event()
        def blocked(link): entered.set(); release.wait(2)
        worker = LinkPrefetcher(blocked, max_pending=2)
        try:
            worker.schedule(['one']); self.assertTrue(entered.wait(1))
            worker.schedule(['two', 'three']); worker.schedule(['four'])
            self.assertEqual(len(worker._queued), 2)
        finally:
            release.set(); worker.close()

    def test_stale_signed_url_is_not_reused(self):
        module = load_player(); player = module.Player.__new__(module.Player)
        player._prefetch_cache = {'url': {'url': 'expired'}}
        player._prefetch_times = {'url': time.monotonic() - 301}
        self.assertIsNone(player._pop_prefetched('url'))


if __name__ == '__main__':
    unittest.main()
