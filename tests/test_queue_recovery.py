from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace,ModuleType
from unittest.mock import Mock,patch
import importlib.util
import json
import sqlite3
import sys
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from bot.state_store import StateStore
from test_maintenance import load_player


def load_cog():
    tt=ModuleType('TeamTalk5');tt.ttstr=lambda v:v
    yt=ModuleType('yt_dlp')
    spec=importlib.util.spec_from_file_location('_queue_recovery_cog',ROOT/'bot/modules/player.py')
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'TeamTalk5':tt,'yt_dlp':yt}):spec.loader.exec_module(module)
    return module


class Pool:
    def __init__(self):self.jobs=[]
    def submit(self,fn,*args):self.jobs.append((fn,args))
    def run(self):
        fn,args=self.jobs.pop(0);fn(*args)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.dbpath=Path(self.tmp.name)/'state.sqlite3';self.store=StateStore(self.dbpath);self.addCleanup(self.store.close)
        self.store.replace_queue([{'title':str(i),'link':f'https://youtube.com/watch?v={i}','_queue_token':str(i)} for i in range(1000)])
        self.pool=Pool();self.plays=[];self.messages=[]
        self.player=SimpleNamespace(queue=self.store.queue(),queue_index=0,queue_mode=True,queue_lock=threading.RLock(),
            queue_history=[],queue_transition=False,last_end_reason='error',last_end_error=-13,active_playback_epoch=1,
            is_playing=False,media_title='0',current_link='https://youtube.com/watch?v=0',pause=False,
            stop_transport=Mock(),invalidate_stream_info=Mock(),play_mode=2,collection_results=[])
        def play(link,**kw):
            self.plays.append(link);self.player.active_playback_epoch+=1;self.player.last_end_reason=None;self.player.is_playing=True
        self.player.play_stream=play
        self.bot=SimpleNamespace(state_store=self.store,io_pool=self.pool,playback_config={'playback_retry_attempts':3,'playback_retry_delay':0},
            bot_config={'gender':0},enableVoiceTransmission=Mock(),doChangeStatus=Mock(),get_idle_status_message=lambda:'idle',privateMessage=Mock())
        module=load_cog();self.cog=module.PlayerCog.__new__(module.PlayerCog)
        self.cog.bot=self.bot;self.cog.player=self.player;self.cog._=lambda v:v;self.cog.loading_new_track=False
        self.cog._deferred_playback_end=False;self.cog._send_playback_message=self.messages.append
        self.cog._prefetch_next_for_current=Mock();self.cog._play_from_queue=Mock()
        self.cog._is_in_same_channel=lambda uid:True;self.cog._nickname=lambda uid:'Tester'
        self.cog._set_playback_context('queue',self.player.current_link,'0')

    def fail_again(self):
        self.player.last_end_reason='error';self.player.last_end_error=-13;self.player.is_playing=False
        self.cog.on_playback_end()

    def test_duplicate_callback_before_retry_worker_never_skips(self):
        for _ in range(10):self.cog.on_playback_end()
        self.assertEqual(len(self.pool.jobs),1);self.assertEqual(len(self.player.queue),1000)
        self.pool.run();self.assertEqual(self.plays,['https://youtube.com/watch?v=0'])
        self.player.invalidate_stream_info.assert_called_once_with(self.plays[0])

    def test_duplicate_callback_after_success_cannot_advance_fresh_track(self):
        self.cog.on_playback_end();self.pool.run();self.cog.on_playback_end()
        self.assertEqual(len(self.player.queue),1000);self.assertEqual(self.player.queue_index,0)
        self.assertFalse(self.pool.jobs)

    def test_transient_failure_can_succeed_on_third_attempt_in_place(self):
        self.cog.on_playback_end();self.pool.run()
        self.fail_again();self.pool.run()
        self.assertEqual(self.plays,[self.player.current_link]*2)
        self.assertEqual(len(self.player.queue),1000);self.assertEqual(self.store.list_queue_failures(),[])
        self.player.last_end_reason='eof';self.cog.on_playback_end()
        self.assertEqual(len(self.player.queue),999);self.assertEqual(self.player.queue[0]['title'],'1')
        self.assertEqual(len(self.player.queue_history),1)

    def test_exhaustion_archives_once_and_duplicate_cannot_delete_next_song(self):
        for _ in range(3):self.fail_again();self.pool.run()
        self.fail_again()
        for _ in range(10):self.cog.on_playback_end()
        self.assertEqual(len(self.player.queue),999);self.assertEqual(self.player.queue[0]['title'],'1')
        failures=self.store.list_queue_failures();self.assertEqual(len(failures),1)
        self.assertEqual(failures[0]['attempts'],4);self.assertEqual(failures[0]['item']['title'],'0')
        self.assertEqual(len(self.pool.jobs),1)

    def test_stop_cancels_waiting_retry_even_if_transport_already_idle(self):
        self.cog.on_playback_end();self.cog._transport_or_voice_active=lambda:False
        self.cog.handle_stop_command(SimpleNamespace(nFromUserID=1));self.pool.run();self.cog.on_playback_end()
        self.assertFalse(self.plays);self.assertEqual(len(self.player.queue),1000)
        self.player.stop_transport.assert_called_once();self.bot.enableVoiceTransmission.assert_called_with(False)

    def test_cq_cancels_retry_and_silent_voice_transmission(self):
        self.cog.on_playback_end();self.cog.handle_clear_queue_command(SimpleNamespace(nFromUserID=1))
        self.pool.run();self.assertEqual(len(self.player.queue),0);self.assertFalse(self.plays)
        self.bot.enableVoiceTransmission.assert_called_with(False)

    def test_changed_context_cancels_queued_retry(self):
        self.cog.on_playback_end();self.cog._set_playback_context('direct','https://example.test/new','new')
        self.pool.run();self.assertFalse(self.plays)

    def test_age_auth_is_retained_without_guest_retry_loop(self):
        self.player.last_error_category='age_auth';self.cog.on_playback_end()
        self.assertEqual(len(self.player.queue),999);self.assertFalse(self.plays)
        row=self.store.list_queue_failures()[0];self.assertTrue(row['reason'].startswith('age_auth'))
        self.assertEqual(row['attempts'],1)

    def test_legacy_queue_token_is_persisted_not_lost_in_dict_copy(self):
        item=self.player.queue[0];item.pop('_queue_token');self.player.queue[0]=item
        token=self.cog._queue_token(0)
        self.assertEqual(self.player.queue[0]['_queue_token'],token)
        self.assertEqual(self.cog._queue_token(0),token)

    def test_same_url_different_queue_item_cancels_stale_retry(self):
        self.cog.on_playback_end()
        item=self.player.queue[0];item['_queue_token']='different-item';self.player.queue[0]=item
        self.pool.run();self.assertFalse(self.plays)

    def test_failed_song_can_be_restored_at_tail_exactly_once(self):
        self.player.last_error_category='age_auth';self.cog.on_playback_end();row=self.store.list_queue_failures()[0]
        self.assertTrue(self.store.restore_queue_failure(row['id']))
        self.assertFalse(self.store.restore_queue_failure(row['id']))
        self.assertEqual(len(self.player.queue),1000);self.assertEqual(self.player.queue[-1]['title'],'0')
        self.assertNotEqual(self.player.queue[-1]['_queue_token'],'0');self.assertFalse(self.store.list_queue_failures())

    def test_archive_rollback_never_loses_song(self):
        self.store._conn.execute("CREATE TRIGGER fail_queue_delete BEFORE DELETE ON queue_entries BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.archive_failed_queue_item(0,'fixture',4)
        self.assertEqual(self.store.queue_count(),1000);self.assertEqual(self.store.list_queue_failures(),[])

    def test_migrate_schema3_keeps_large_queue(self):
        self.store.close();conn=sqlite3.connect(self.dbpath)
        conn.execute('DROP TABLE queue_failures');conn.execute('PRAGMA user_version=3');conn.commit();conn.close()
        store=StateStore(self.dbpath)
        try:self.assertEqual(store.queue_count(),1000);self.assertEqual(store.list_queue_failures(),[])
        finally:store.close()


class StreamMetadataTests(unittest.TestCase):
    def setUp(self):
        self.module=load_player();self.player=self.module.Player.__new__(self.module.Player)
        self.player._prefetch_cache={};self.player._prefetch_times={}

    def test_signed_url_expiry_overrides_fresh_prefetch_timestamp(self):
        self.player._prefetch_cache['song']={'url':f'https://cdn.example/audio?expire={int(time.time())+10}'}
        self.player._prefetch_times['song']=time.monotonic()
        self.assertIsNone(self.player._pop_prefetched('song'))

    def test_transport_headers_are_forwarded_and_reset_for_next_item(self):
        self.player._apply_stream_headers({'http_headers':{'User-Agent':'FixtureBrowser','Referer':'https://youtube.com/','Cookie':'never forward','Origin':'bad\nInjected: value'}})
        self.assertEqual(self.player.http_header_fields,['User-Agent: FixtureBrowser','Referer: https://youtube.com/'])
        self.player._apply_stream_headers({});self.assertEqual(self.player.http_header_fields,[])

    def test_old_native_end_id_is_ignored_beyond_grace(self):
        self.player._active_mpv_entry_id=9;self.player.active_playback_started=time.monotonic()-10
        self.player._end_dispatch_lock=threading.Lock();self.player._end_event_handled=False
        self.player._on_end_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=8,reason=0,error=0)))
        self.assertFalse(self.player._end_event_handled)

    def test_matching_native_error_is_handled_even_when_idle_property_lags(self):
        self.player._active_mpv_entry_id=9;self.player.active_playback_started=time.monotonic()
        self.player._end_dispatch_lock=threading.Lock();self.player._end_event_handled=False
        self.player._intentional_stop=False;self.player._mpv_end_event_registered=True
        self.player.is_playing=True;self.player.idle_active=False;self.player.end_callback=Mock()
        self.player._on_end_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=9,reason=4,error=-13)))
        self.player.end_callback.assert_called_once();self.assertEqual(self.player.last_end_reason,'error')

    def test_old_end_before_new_start_cannot_consume_new_load(self):
        self.player._active_mpv_entry_id=9;self.player._mpv_start_event_registered=True
        self.player._end_dispatch_lock=threading.Lock();self.player.playback_epoch=1
        self.player._arm_end_detection();self.player.end_callback=Mock()
        self.player._mpv_end_event_registered=True;self.player.is_playing=True;self.player.idle_active=True
        self.player._on_end_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=9,reason=0,error=0)))
        self.player.end_callback.assert_not_called()
        self.player._on_start_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=10)))
        self.player._on_end_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=10,reason=4,error=-13)))
        self.player.end_callback.assert_called_once()

    def test_explicit_age_error_does_not_try_anonymous_session(self):
        calls=[];self.player._active_cookiefile=lambda:'fixture'
        from contextlib import contextmanager
        @contextmanager
        def fresh(**kwargs):
            calls.append(kwargs)
            yield SimpleNamespace(extract_info=lambda *args,**kw: (_ for _ in ()).throw(RuntimeError('Sign in to confirm your age')))
        self.player._fresh_ydl=fresh
        with self.assertRaises(self.module.MediaAccessError):self.player._extract_play_info_resilient('https://youtube.com/watch?v=age')
        self.assertEqual(len(calls),1);self.assertTrue(calls[0]['use_cookies'])

    def test_cancel_during_extract_prevents_mpv_play(self):
        cancel=threading.Event();self.player.pause=False
        self.player._pop_prefetched=lambda link:None;self.player._ydl_lock=threading.Lock()
        def extract(link):cancel.set();return {'title':'x','url':'https://cdn.example/audio'}
        self.player._extract_play_info_resilient=extract
        self.player.play=Mock();self.assertFalse(self.player.play_stream('https://youtube.com/watch?v=x',cancel_event=cancel))
        self.player.play.assert_not_called()

if __name__=='__main__':unittest.main()
