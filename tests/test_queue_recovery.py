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
        self.pool.run();self.pool.run();self.assertEqual(self.plays,['https://youtube.com/watch?v=0'])
        self.player.invalidate_stream_info.assert_called_once_with(self.plays[0])

    def test_duplicate_callback_after_success_cannot_advance_fresh_track(self):
        self.cog.on_playback_end();self.pool.run();self.pool.run();self.cog.on_playback_end()
        self.assertEqual(len(self.player.queue),1000);self.assertEqual(self.player.queue_index,0)
        self.assertFalse(self.pool.jobs)

    def test_transient_failure_can_succeed_on_third_attempt_in_place(self):
        self.cog.on_playback_end();self.pool.run();self.pool.run()
        self.fail_again();self.pool.run();self.pool.run()
        self.assertEqual(self.plays,[self.player.current_link]*2)
        self.assertEqual(len(self.player.queue),1000);self.assertEqual(self.store.list_queue_failures(),[])
        self.player.last_end_reason='eof';self.cog.on_playback_end()
        self.assertEqual(len(self.player.queue),999);self.assertEqual(self.player.queue[0]['title'],'1')
        self.assertEqual(len(self.player.queue_history),1)

    def test_last_queue_song_releases_voice_and_clears_now_playing(self):
        self.store.replace_queue([{'title':'last','link':'https://youtube.com/watch?v=last','_queue_token':'last'}])
        self.player.queue=self.store.queue();self.player.queue_index=0
        self.player.last_end_reason='eof';self.player.media_title='Last song'
        self.player.current_link='https://youtube.com/watch?v=last'
        self.cog.on_playback_end()
        self.assertEqual(len(self.player.queue),0)
        self.assertEqual(self.player.queue_index,-1)
        self.assertEqual(len(self.pool.jobs),0)
        self.bot.enableVoiceTransmission.assert_called_once_with(False)
        self.bot.doChangeStatus.assert_called_once_with(0,'idle')
        self.assertIsNone(self.player.current_link)
        self.assertEqual(self.player.media_title,'')
        self.assertFalse(self.player.pause)

    def test_native_eof_is_dispatched_off_the_callback_thread(self):
        self.player.last_end_reason='eof'
        self.cog._schedule_playback_end()
        self.assertEqual(len(self.player.queue),1000)
        self.assertEqual(len(self.pool.jobs),1)
        self.pool.run()
        self.assertEqual(len(self.player.queue),999)
        self.assertEqual(len(self.pool.jobs),1)
        self.assertEqual(self.pool.jobs[0][0],self.cog._play_from_queue)

    def test_mpv_eof_to_player_cog_to_next_queue_uses_one_serial_path(self):
        module=load_player()
        self.player._end_dispatch_lock=threading.Lock()
        self.player._end_event_handled=False
        self.player._intentional_stop=False
        self.player._mpv_end_event_registered=True
        self.player.end_callback=self.cog._schedule_playback_end
        dispatch=module.Player._dispatch_end_once.__get__(self.player)
        self.assertTrue(dispatch('eof',0))
        self.assertFalse(self.player.is_playing)
        self.assertEqual(len(self.player.queue),1000)
        self.pool.run()
        self.assertEqual(len(self.player.queue),999)
        self.assertEqual(len(self.pool.jobs),1)
        self.pool.run()
        self.cog._play_from_queue.assert_called_once_with(0)

    def test_natural_queue_handoff_does_not_stop_idle_transport_again(self):
        self.player.transport_is_active=Mock(return_value=False)
        self.player.stop_transport.reset_mock()
        self.player.play_stream=Mock()
        self.player.clear_collection=Mock();self.player.clear_radio_history=Mock()
        self.player.media_title='Next';self.cog._announce_track=Mock()
        self.cog._prefetch_next_for_current=Mock();self.cog._log_action=Mock()
        self.cog._play_from_queue=type(self.cog)._play_from_queue.__get__(self.cog)
        self.cog._play_from_queue(0)
        self.player.stop_transport.assert_not_called()
        self.player.play_stream.assert_called_once()
        self.bot.enableVoiceTransmission.assert_called_with(True)

    def test_queue_arms_teamtalk_voice_before_starting_mpv(self):
        order=[]
        self.player.transport_is_active=Mock(return_value=False)
        self.player.stop_transport.reset_mock()
        self.player.clear_collection=Mock();self.player.clear_radio_history=Mock()
        self.player.media_title='Next';self.cog._announce_track=Mock()
        self.cog._prefetch_next_for_current=Mock();self.cog._log_action=Mock()
        self.bot.enableVoiceTransmission.side_effect=lambda enabled: order.append(('voice',enabled))
        self.player.play_stream=Mock(side_effect=lambda link: order.append(('play',link)))
        self.cog._play_from_queue=type(self.cog)._play_from_queue.__get__(self.cog)
        self.cog._play_from_queue(0)
        self.assertEqual(order[0],('voice',True))
        self.assertEqual(order[1][0],'play')

    def test_queue_selection_is_enqueued_and_stale_restart_skipped(self):
        first={'title':'A','link':'https://youtube.com/watch?v=a'}
        second={'title':'B','link':'https://youtube.com/watch?v=b'}
        self.store.replace_queue([{
            'title':'A','link':first['link'],'_queue_token':'choice',
            '_search_results':[first,second],'_search_index':0,
        }])
        self.player.queue=self.store.queue();self.player.queue_index=0
        self.cog._play_from_queue=Mock()
        self.cog._change_queue_search_selection(SimpleNamespace(nFromUserID=7),1,('1',))
        self.assertEqual(self.player.queue[0]['link'],second['link'])
        self.cog._play_from_queue.assert_not_called()
        self.pool.run()
        self.cog._play_from_queue.assert_called_once_with(0,'choice',second['link'])

        self.cog._play_from_queue=type(self.cog)._play_from_queue.__get__(self.cog)
        self.player.stop_transport.reset_mock()
        self.cog._play_from_queue(0,'choice',first['link'])
        self.player.stop_transport.assert_not_called()

    def test_queue_first_search_result_warms_next_selection(self):
        choices=[{'title':name,'link':f'https://youtube.com/watch?v={name}'} for name in ('a','b','c')]
        self.store.replace_queue([{
            'title':'a','link':choices[0]['link'],'_queue_token':'first',
            '_search_results':choices,'_search_index':0,
        }])
        self.player.queue=self.store.queue();self.player.queue_index=0
        self.player.prefetcher=SimpleNamespace(schedule=Mock())
        self.cog._prefetch_next_for_current=type(self.cog)._prefetch_next_for_current.__get__(self.cog)
        self.cog._prefetch_next_for_current()
        self.player.prefetcher.schedule.assert_called_once_with([choices[1]['link']])

    def test_autoplay_without_any_related_song_releases_voice(self):
        self.store.replace_queue([])
        self.player.queue=self.store.queue();self.player.queue_index=-1
        self.player.queue_mode=False;self.player.play_mode=2
        self.player.last_end_reason='eof'
        self.cog.autoplay_enabled=False
        self.cog._play_next_related=Mock(return_value=False)
        self.cog.on_playback_end()
        self.assertEqual(len(self.pool.jobs),1)
        self.pool.run()
        self.cog._play_next_related.assert_called_once_with(None,False,True)
        self.bot.enableVoiceTransmission.assert_called_once_with(False)
        self.bot.doChangeStatus.assert_called_once_with(0,'idle')
        self.assertIsNone(self.player.current_link)

    def test_exhaustion_archives_once_and_duplicate_cannot_delete_next_song(self):
        for _ in range(3):self.fail_again();self.pool.run();self.pool.run()
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

    def test_cancel_during_retry_extraction_never_leaves_loading_flag_stuck(self):
        self.cog.on_playback_end()
        context=self.cog._retry_pending
        self.assertIsNotNone(context)
        self.player.play_stream=Mock(side_effect=lambda _link,**_kw: context['cancel'].set())
        self.cog._perform_retry_playback_context(context)
        self.assertFalse(self.cog.loading_new_track)
        self.assertFalse(self.cog._deferred_playback_end)

    def test_collection_auto_advance_uses_playback_pool_not_busy_io_pool(self):
        self.player.queue_mode=False;self.player.queue_index=-1
        self.player.collection_results=[
            {'title':'Current','link':self.player.current_link},
            {'title':'Next','link':'https://youtube.com/watch?v=next'},
        ]
        self.player.current_collection_index=0
        self.player.last_end_reason='eof'
        dedicated=Pool();self.cog._playback_pool=dedicated
        self.cog._play_next_from_active_list=Mock()
        self.cog.on_playback_end()
        self.assertEqual(self.pool.jobs,[])
        self.assertEqual(len(dedicated.jobs),1)
        dedicated.run()
        self.cog._play_next_from_active_list.assert_called_once_with(None,False)

    def test_age_auth_is_retained_without_guest_retry_loop(self):
        self.player.last_error_category='age_auth';self.cog.on_playback_end()
        self.assertEqual(len(self.player.queue),999);self.assertFalse(self.plays)
        row=self.store.list_queue_failures()[0];self.assertTrue(row['reason'].startswith('age_auth'))
        self.assertEqual(row['attempts'],1)

    def test_prefetch_prioritizes_only_the_immediate_queue_successor(self):
        self.player.prefetcher=SimpleNamespace(schedule=Mock())
        module=load_cog()
        module.PlayerCog._prefetch_next_for_current(self.cog)
        self.player.prefetcher.schedule.assert_called_once_with(['https://youtube.com/watch?v=1'])
        self.assertEqual(self.player.queue_index,0)
        self.assertEqual(len(self.player.queue),1000)

    def test_collection_prefetch_does_not_block_next_track_with_later_items(self):
        self.player.queue_mode=False
        self.player.prefetcher=SimpleNamespace(schedule=Mock())
        self.cog._get_active_results=lambda:([
            {'link':f'https://youtube.com/watch?v={i}'} for i in range(8)
        ],'playlist')
        self.cog._get_active_index=lambda:2
        module=load_cog()
        module.PlayerCog._prefetch_next_for_current(self.cog)
        self.player.prefetcher.schedule.assert_called_once_with(['https://youtube.com/watch?v=3'])

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

    def test_playlist_name_selection_keeps_queue_fifo(self):
        playlist_url='https://www.youtube.com/playlist?list=PL1234567890ABC'
        self.player.classify_collection_link=lambda link:'playlist' if 'list=' in link else None
        self.player.search_playlists=Mock(return_value=[{'title':'Thai Mix','link':playlist_url,'channel':'Creator'}])
        self.cog.pending_playlist_searches={}
        self.cog.pending_playlist_search_lock=threading.Lock()
        self.cog._play_collection_task=Mock()
        user=SimpleNamespace(nFromUserID=7)
        self.cog.handle_append_playlist_command(user,'Thai','Mix')
        self.assertEqual(len(self.pool.jobs),1)
        self.pool.run()
        self.player.search_playlists.assert_called_once_with('Thai Mix',limit=10)
        self.assertEqual([row['title'] for row in self.player.queue[:2]],['0','1'])
        self.cog.handle_playlist_search_selection_command(user,'1')
        self.pool.run()
        self.cog._play_collection_task.assert_called_once_with(playlist_url,7,True)
        self.assertEqual(len(self.player.queue),1000)

    def test_playlist_search_selection_is_private_to_requester(self):
        playlist_url='https://www.youtube.com/playlist?list=PL1234567890ABC'
        self.player.classify_collection_link=lambda link:None
        self.player.search_playlists=lambda _name,limit=10:[{'title':'Thai Mix','link':playlist_url}]
        self.cog.pending_playlist_searches={}
        self.cog.pending_playlist_search_lock=threading.Lock()
        self.cog._play_collection_task=Mock()
        self.cog.handle_append_playlist_command(SimpleNamespace(nFromUserID=7),'Thai')
        self.pool.run()
        self.cog.handle_playlist_search_selection_command(SimpleNamespace(nFromUserID=8),'1')
        self.assertFalse(self.pool.jobs)
        self.cog.handle_playlist_search_selection_command(SimpleNamespace(nFromUserID=7),'1')
        self.pool.run()
        self.cog._play_collection_task.assert_called_once_with(playlist_url,7,True)

    def test_playlist_url_is_still_accepted_without_search(self):
        playlist_url='https://www.youtube.com/playlist?list=PL1234567890ABC'
        self.player.classify_collection_link=lambda link:'playlist' if link==playlist_url else None
        self.player.search_playlists=Mock()
        self.cog._play_collection_task=Mock()
        self.cog.handle_append_playlist_command(SimpleNamespace(nFromUserID=7),playlist_url)
        self.pool.run()
        self.cog._play_collection_task.assert_called_once_with(playlist_url,7,True)
        self.player.search_playlists.assert_not_called()


class FastFirstSearchTests(unittest.TestCase):
    def setUp(self):
        self.module=load_cog()
        self.player=SimpleNamespace(
            queue=[],queue_index=-1,queue_mode=True,queue_lock=threading.RLock(),
            queue_transition=False,playback_end_transition=False,is_playing=False,
            search_youtube=Mock(),search_ytmusic=Mock(),
        )
        self.pool=Pool()
        self.bot=SimpleNamespace(io_pool=self.pool,privateMessage=Mock())
        self.cog=self.module.PlayerCog.__new__(self.module.PlayerCog)
        self.cog.bot=self.bot;self.cog.player=self.player;self.cog._=lambda value:value
        self.cog._nickname=lambda user_id:'Listener'
        self.cog._send_playback_message=Mock();self.cog._announce_queue=Mock()
        self.cog._after_queue_enqueue=Mock();self.cog._log_action=Mock()

    def test_first_song_starts_from_one_result_before_full_search_expands(self):
        full=[{'title':f'Song {i}','link':f'https://youtube.com/watch?v={i}'} for i in range(50)]
        self.player.search_youtube.side_effect=lambda query,**kwargs: full[:1] if kwargs.get('limit')==1 else full
        self.cog._search_and_enqueue_task('Thai music',7)
        self.player.search_youtube.assert_called_once_with('Thai music',limit=1)
        self.cog._after_queue_enqueue.assert_called_once_with(True)
        self.assertEqual(len(self.player.queue),1)
        self.assertEqual(len(self.player.queue[0]['_search_results']),1)
        self.assertEqual(len(self.pool.jobs),1)
        self.pool.run()
        self.assertEqual(len(self.player.queue[0]['_search_results']),50)
        self.assertEqual(self.player.queue[0]['title'],'Song 0')
        self.assertEqual(self.player.queue[0]['_search_index'],0)

    def test_background_search_does_not_replace_user_selection_or_stale_queue(self):
        first={'title':'First','link':'https://youtube.com/watch?v=first'}
        second={'title':'Second','link':'https://youtube.com/watch?v=second'}
        self.player.search_youtube.side_effect=lambda query,**kwargs:[first] if kwargs.get('limit')==1 else [second,first]
        self.cog._search_and_enqueue_task('song',7)
        original=self.player.queue[0]
        token=original['_queue_token']
        # A user's choice must not be silently replaced by a later full search.
        selected=dict(original,title='Custom selection',link='https://youtube.com/watch?v=custom')
        self.player.queue[0]=selected
        self.pool.run()
        self.assertEqual(self.player.queue[0]['title'],'Custom selection')
        self.assertEqual(self.player.queue[0]['_queue_token'],token)
        self.assertEqual(len(self.player.queue[0]['_search_results']),2)
        # Deleting the original request while the full search is in flight
        # must never modify another request occupying the same queue index.
        self.player.queue[0]={'title':'Someone else','link':'https://youtube.com/watch?v=other','_queue_token':'other'}
        self.cog._expand_queued_search_results('song','youtube',token)
        self.assertEqual(self.player.queue[0]['title'],'Someone else')
        self.assertNotIn('_search_results',self.player.queue[0])

    def test_existing_queue_keeps_complete_search_and_ytmusic_intent(self):
        self.player.queue=[{'title':'Playing','link':'https://youtube.com/watch?v=old','_queue_token':'old'}]
        self.player.queue_index=0;self.player.is_playing=True
        result=[{'title':'Music','link':'https://music.youtube.com/watch?v=music'}]
        self.player.search_ytmusic.return_value=result
        self.cog._search_and_enqueue_task('music',7,source='ytmusic')
        self.player.search_ytmusic.assert_called_once_with('music')
        self.cog._after_queue_enqueue.assert_called_once_with(False)
        self.assertEqual(len(self.pool.jobs),0)
        self.assertEqual(self.player.queue[-1]['_search_source'],'ytmusic')

    def test_normal_play_starts_from_first_result_and_restores_full_navigation(self):
        self.player.queue_mode=False
        self.player.search_results=[];self.player.current_search_index=0
        self.player.reset_radio_history=Mock();self.player.play_stream=Mock()
        self.player.media_title='First';self.player.current_link=None
        self.bot.bot_config={'gender':0};self.bot.enableVoiceTransmission=Mock()
        self.bot.doChangeStatus=Mock()
        self.cog._set_playback_context=Mock()
        self.cog._announce_track=Mock();self.cog._prefetch_next_for_current=Mock()
        tracks=[{'title':f'Track {i}','link':f'https://music.youtube.com/watch?v={i}'} for i in range(20)]
        self.player.search_ytmusic.side_effect=lambda query,**kwargs: tracks[:1] if kwargs.get('limit')==1 else tracks
        self.cog._search_and_play_task('songs',7,source='ytmusic')
        self.player.search_ytmusic.assert_called_once_with('songs',limit=1)
        self.player.play_stream.assert_called_once_with(tracks[0]['link'])
        self.assertEqual(len(self.player.search_results),1)
        self.assertEqual(len(self.pool.jobs),1)
        self.pool.run()
        self.assertEqual(len(self.player.search_results),20)
        self.cog._prefetch_next_for_current.assert_called()

    def test_background_normal_search_cannot_overwrite_newer_request(self):
        self.player.search_results=[{'title':'Newer request','link':'https://youtube.com/watch?v=new'}]
        newer=self.player.search_results
        old=[{'title':'Old request','link':'https://youtube.com/watch?v=old'}]
        self.player.search_youtube.return_value=[{'title':'Stale','link':'https://youtube.com/watch?v=stale'}]
        self.cog._expand_active_search_results('old','youtube',old)
        self.assertIs(self.player.search_results,newer)
        self.assertEqual(len(newer),1)

    def test_first_page_search_failure_falls_back_without_double_background_search(self):
        results=[{'title':'Recovered','link':'https://youtube.com/watch?v=ok'},
                 {'title':'Alternate','link':'https://youtube.com/watch?v=alt'}]
        self.player.search_youtube.side_effect=lambda query,**kwargs: [] if kwargs.get('limit')==1 else results
        self.cog._search_and_enqueue_task('recovery',7)
        self.assertEqual(self.player.search_youtube.call_count,2)
        self.assertEqual(len(self.player.queue[0]['_search_results']),2)
        self.cog._after_queue_enqueue.assert_called_once_with(True)
        self.assertEqual(self.pool.jobs,[])


class StreamMetadataTests(unittest.TestCase):
    def setUp(self):
        self.module=load_player();self.player=self.module.Player.__new__(self.module.Player)
        self.player._prefetch_cache={};self.player._prefetch_times={}
        self.player._ydl_lock=threading.Lock();self.player._prefetch_inflight={}

    def test_fast_youtube_resolver_prefers_opus_and_caches_result(self):
        self.player._fast_stream_cache={};self.player._fast_stream_cache_lock=threading.Lock()
        self.player._fast_stream_cache_ttl=7200;self.player._youtube_video_id=self.module.Player._youtube_video_id
        self.player._stream_url_ttl=self.module.Player._stream_url_ttl
        self.player._fast_stream_get=self.module.Player._fast_stream_get.__get__(self.player)
        self.player._fast_stream_put=self.module.Player._fast_stream_put.__get__(self.player)
        response=SimpleNamespace(status_code=200,json=lambda:{
            'playabilityStatus':{'status':'OK'},'videoDetails':{'title':'Fast'},
            'streamingData':{'adaptiveFormats':[
                {'itag':140,'url':'https://cdn.example/a.m4a','mimeType':'audio/mp4','bitrate':128000},
                {'itag':251,'url':'https://cdn.example/a.opus','mimeType':'audio/webm','bitrate':96000},
            ]},
        })
        self.player._stream_http=SimpleNamespace(post=Mock(return_value=response))
        resolve=self.module.Player._resolve_youtube_direct_audio.__get__(self.player)
        link='https://www.youtube.com/watch?v=abcdefghijk'
        first=resolve(link);second=resolve(link)
        self.assertEqual(first['url'],'https://cdn.example/a.opus')
        self.assertEqual(second['url'],first['url'])
        self.player._stream_http.post.assert_called_once()

    def test_fast_youtube_resolver_restricted_media_falls_back_cleanly(self):
        self.player._fast_stream_cache={};self.player._fast_stream_cache_lock=threading.Lock()
        self.player._fast_stream_cache_ttl=7200;self.player._youtube_video_id=self.module.Player._youtube_video_id
        self.player._fast_stream_get=self.module.Player._fast_stream_get.__get__(self.player)
        self.player._fast_stream_put=self.module.Player._fast_stream_put.__get__(self.player)
        response=SimpleNamespace(status_code=200,json=lambda:{'playabilityStatus':{'status':'LOGIN_REQUIRED'}})
        self.player._stream_http=SimpleNamespace(post=Mock(return_value=response))
        resolve=self.module.Player._resolve_youtube_direct_audio.__get__(self.player)
        self.assertIsNone(resolve('https://www.youtube.com/watch?v=abcdefghijk'))
        self.assertEqual(self.player._stream_http.post.call_count,1)

    def test_signed_url_expiry_overrides_fresh_prefetch_timestamp(self):
        self.player._prefetch_cache['song']={'url':f'https://cdn.example/audio?expire={int(time.time())+10}'}
        self.player._prefetch_times['song']=time.monotonic()
        self.assertIsNone(self.player._pop_prefetched('song'))

    def test_non_youtube_platforms_still_use_the_generic_media_extractor(self):
        from contextlib import contextmanager
        seen=[]
        self.player._active_cookiefile=lambda:None
        @contextmanager
        def extractor(**options):
            yield SimpleNamespace(extract_info=lambda url,download: (seen.append(url) or {'url':url,'title':'Media'}))
        self.player._fresh_ydl=extractor
        links=[
            'https://soundcloud.com/example/song',
            'https://www.twitch.tv/videos/123456',
            'https://vimeo.com/123456',
        ]
        for link in links:
            self.assertEqual(self.player._extract_play_info_resilient(link)['url'],link)
        self.assertEqual(seen,links)

    def test_prefetch_survives_long_first_song_when_signed_url_is_valid(self):
        info={'title':'Second','url':f'https://cdn.example/audio?expire={int(time.time())+3600}'}
        self.player._prefetch_cache['second']=info
        self.player._prefetch_times['second']=time.monotonic()-600
        self.assertEqual(self.player._pop_prefetched('second'),info)

    def test_prefetch_still_expires_after_safe_upper_bound(self):
        self.player._prefetch_cache['second']={'title':'Second','url':'https://cdn.example/audio'}
        self.player._prefetch_times['second']=time.monotonic()-1801
        self.assertIsNone(self.player._pop_prefetched('second'))

    def test_prefetched_next_song_starts_without_second_extractor_call(self):
        link='https://www.youtube.com/watch?v=next'
        media='https://cdn.example/music?expire='+str(int(time.time())+3600)
        self.player._prefetch_cache[link]={'title':'Next song','url':media}
        self.player._prefetch_times[link]=time.monotonic()
        self.player.pause=False
        self.player._ydl_lock=threading.Lock()
        self.player._extract_play_info_resilient=Mock(side_effect=AssertionError('unexpected yt-dlp call'))
        self.player._requires_temp_download=Mock(return_value=False)
        self.player._apply_stream_headers=Mock()
        self.player._arm_end_detection=Mock()
        self.player._cancel_end_detection=Mock()
        self.player._mpv_end_event_registered=True
        self.player.play=Mock()
        self.player.add_to_recent_history=Mock()
        self.assertIsNone(self.player.play_stream(link))
        self.player.play.assert_called_once_with(media)
        self.player._extract_play_info_resilient.assert_not_called()

    def test_foreground_play_does_not_wait_for_unrelated_slow_prefetch(self):
        entered=threading.Event();release=threading.Event()
        def extract(link):
            if link=='background':
                entered.set();release.wait(2.0)
            return {'title':'Ready','url':'https://cdn.example/audio'}
        self.player._extract_play_info_resilient=extract
        worker=threading.Thread(target=self.player.prefetch_stream_info,args=('background',),daemon=True)
        worker.start();self.assertTrue(entered.wait(1))
        self.player.pause=False;self.player._requires_temp_download=Mock(return_value=False)
        self.player._apply_stream_headers=Mock();self.player._arm_end_detection=Mock()
        self.player._cancel_end_detection=Mock();self.player.play=Mock()
        self.player._mpv_end_event_registered=True;self.player.add_to_recent_history=Mock()
        try:
            start=time.monotonic()
            self.player.play_stream('foreground')
            self.assertLess(time.monotonic()-start,0.65)
            self.player.play.assert_called_once_with('https://cdn.example/audio')
        finally:
            release.set();worker.join(2)

    def test_pending_prefetch_is_reused_if_about_to_finish(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def extract(link):
            calls.append(link)
            entered.set();release.wait(2)
            return {'title':'Ready','url':'https://cdn.example/audio'}
        self.player._extract_play_info_resilient=extract
        worker=threading.Thread(target=self.player.prefetch_stream_info,args=('same',),daemon=True)
        worker.start();self.assertTrue(entered.wait(1))
        self.player.pause=False;self.player._requires_temp_download=Mock(return_value=False)
        self.player._apply_stream_headers=Mock();self.player._arm_end_detection=Mock()
        self.player._cancel_end_detection=Mock();self.player.play=Mock()
        self.player._mpv_end_event_registered=True;self.player.add_to_recent_history=Mock()
        timer=threading.Timer(0.05,release.set);timer.start()
        try:
            self.player.play_stream('same')
            self.assertEqual(calls,['same'])
            self.player.play.assert_called_once()
        finally:
            release.set();worker.join(2);timer.join(2)

    def test_eof_property_observer_dispatches_without_end_file(self):
        self._arm_watchdog_fixture()
        self.player._on_eof_reached('eof-reached', True)
        self.player.end_callback.assert_called_once()
        self.assertEqual(self.player.last_end_reason,'eof')

    def test_idle_observer_remains_permanent_after_intentional_stop(self):
        self._arm_watchdog_fixture()
        self.player._intentional_stop=True
        self.player.unobserve_property=Mock()
        self.player._on_idle_active('idle-active', True)
        self.player.unobserve_property.assert_not_called()
        self.player.end_callback.assert_not_called()

    def test_native_eof_property_recovers_when_idle_never_flips(self):
        self._arm_watchdog_fixture()
        self.player.idle_active=False
        self.player._on_start_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=5)))
        self.player.active_playback_started=time.monotonic()-8
        self.module.Player.__getitem__=lambda _self,key: True if key=='eof-reached' else (7.5 if key=='time-pos' else False)
        self.player._playback_watchdog_tick()
        self.player._watchdog_eof_since=time.monotonic()-2
        self.player._playback_watchdog_tick()
        self.player.end_callback.assert_called_once()
        self.assertEqual(self.player.last_end_reason,'eof')

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

    def test_native_end_without_start_uses_adopted_entry_id_for_terminal_check(self):
        # A START_FILE race can leave an already-observed active ID while the
        # current generation is still awaiting its matching start event. Once
        # END_FILE proves a different, non-previous entry is current, the local
        # active-id snapshot must be refreshed or the terminal event is dropped.
        self._arm_watchdog_fixture()
        self.player._previous_mpv_entry_id=40
        self.player._active_mpv_entry_id=41
        self.player._awaiting_mpv_start=True
        self.player.idle_active=True
        self.player._on_end_file_event(SimpleNamespace(
            data=SimpleNamespace(playlist_entry_id=42,reason=0,error=0)))
        self.player.end_callback.assert_called_once()
        self.assertEqual(self.player._active_mpv_entry_id,42)
        self.assertEqual(self.player.last_end_reason,'eof')

    def test_native_end_without_matching_start_advances_new_entry(self):
        # This is the intermittent silent-queue failure: MPV delivers the
        # terminal event for a new unique entry, but START_FILE was missed.
        self._arm_watchdog_fixture()
        self.player._active_mpv_entry_id=41
        self.player._arm_end_detection()
        self.player.idle_active=True
        self.player._on_end_file_event(SimpleNamespace(
            data=SimpleNamespace(playlist_entry_id=42,reason=0,error=0)))
        self.player.end_callback.assert_called_once()
        self.assertEqual(self.player.last_end_reason,'eof')

    def test_native_error_without_start_is_not_dropped(self):
        self._arm_watchdog_fixture()
        self.player._active_mpv_entry_id=51
        self.player._arm_end_detection()
        self.player.idle_active=True
        self.player._on_end_file_event(SimpleNamespace(
            data=SimpleNamespace(playlist_entry_id=52,reason=4,error=-13)))
        self.player.end_callback.assert_called_once()
        self.assertEqual(self.player.last_end_reason,'error')

    def test_old_native_start_id_does_not_adopt_previous_track(self):
        self._arm_watchdog_fixture()
        self.player._active_mpv_entry_id=61
        self.player._arm_end_detection()
        self.player._on_start_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=61)))
        self.assertTrue(self.player._awaiting_mpv_start)
        self.player._on_start_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=62)))
        self.assertFalse(self.player._awaiting_mpv_start)
        self.assertEqual(self.player._active_mpv_entry_id,62)

    def _arm_watchdog_fixture(self):
        self.player._end_dispatch_lock=threading.Lock()
        self.player.playback_epoch=0
        self.player._mpv_start_event_registered=True
        self.player._mpv_end_event_registered=True
        self.player._intentional_stop=False
        self.player._end_event_handled=True
        self.player._active_mpv_entry_id=None
        self.player.is_playing=True
        self.player.pause=False
        self.player.end_callback=Mock()
        self.player._arm_end_detection()

    def test_watchdog_recovers_eof_when_native_end_event_is_missing(self):
        self._arm_watchdog_fixture()
        self.player.idle_active=False
        self.player._playback_watchdog_tick()
        self.player.idle_active=True
        self.player.active_playback_started=time.monotonic()-10
        self.player._watchdog_idle_since=time.monotonic()-2
        self.player._playback_watchdog_tick()
        self.player._playback_watchdog_tick()
        self.player.end_callback.assert_called_once()
        self.assertEqual(self.player.last_end_reason,'idle')

    def test_watchdog_does_not_end_a_new_media_during_initial_idle(self):
        self._arm_watchdog_fixture()
        self.player.idle_active=True
        self.player.active_playback_started=time.monotonic()-6
        self.player._watchdog_idle_since=time.monotonic()-2
        self.player._playback_watchdog_tick()
        self.player.end_callback.assert_not_called()
        self.assertFalse(self.player._end_event_handled)

    def test_watchdog_recovers_very_short_song_with_start_event(self):
        self._arm_watchdog_fixture()
        self.player._on_start_file_event(SimpleNamespace(data=SimpleNamespace(playlist_entry_id=3)))
        self.player.idle_active=True
        self.player.active_playback_started=time.monotonic()-4
        self.player._watchdog_idle_since=time.monotonic()-2
        self.player._playback_watchdog_tick()
        self.player.end_callback.assert_called_once()

    def test_watchdog_retries_transport_frozen_after_audio_progress(self):
        self._arm_watchdog_fixture()
        self.player.idle_active=False
        self.player._watchdog_seen_active=True
        self.player._watchdog_seen_position=True
        self.player._watchdog_last_position=35.0
        self.player._watchdog_last_progress_at=time.monotonic()-41
        self.module.Player.__getitem__=lambda _self,key: 35.0 if key=='time-pos' else False
        self.player._playback_watchdog_tick()
        self.player.end_callback.assert_called_once()
        self.assertEqual(self.player.last_end_reason,'error')

    def test_watchdog_detects_stuck_final_frame_without_native_eof(self):
        self._arm_watchdog_fixture()
        self.player.idle_active=False
        self.player._watchdog_seen_position=True
        self.player._watchdog_last_position=119.85
        self.player._watchdog_last_progress_at=time.monotonic()-6
        self.player._watchdog_near_end_since=time.monotonic()-4
        self.module.Player.__getitem__=lambda _self,key: {
            'time-pos':119.85,'duration':120.0,'eof-reached':False,
            'paused-for-cache':False,
        }.get(key)
        self.player._playback_watchdog_tick()
        self.player.end_callback.assert_called_once()
        self.assertEqual(self.player.last_end_reason,'eof')

    def test_watchdog_does_not_end_unknown_length_live_stream(self):
        self._arm_watchdog_fixture()
        self.player.idle_active=False
        self.player._watchdog_seen_position=True
        self.player._watchdog_last_position=119.85
        self.player._watchdog_last_progress_at=time.monotonic()-6
        self.player._watchdog_near_end_since=time.monotonic()-4
        self.module.Player.__getitem__=lambda _self,key: {
            'time-pos':119.85,'duration':None,'eof-reached':False,
            'paused-for-cache':False,
        }.get(key)
        self.player._playback_watchdog_tick()
        self.player.end_callback.assert_not_called()

    def test_watchdog_never_skips_a_manually_paused_song(self):
        self._arm_watchdog_fixture()
        self.player.idle_active=False
        self.player.pause=True
        self.player._watchdog_seen_position=True
        self.player._watchdog_last_position=20.0
        self.player._watchdog_last_progress_at=time.monotonic()-100
        self.player._playback_watchdog_tick()
        self.player.end_callback.assert_not_called()

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
