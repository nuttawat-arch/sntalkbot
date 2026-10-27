from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
import configparser
import importlib.util
import json
import os
import sys
import threading
import unittest
import urllib.request
import urllib.error
import socket

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from bot.web_controls import WebControls,ControlError,WEB_ACTOR_ID,PLAYER_ACTIONS
from bot.state_store import StateStore
from bot.http_api import LocalStatusApi
from bot.dashboard_state import RuntimeSnapshotBuilder

class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=StateStore(Path(self.tmp.name)/'state.sqlite3');self.addCleanup(self.store.close)
        self.cog=Mock();self.cog.favorites=[{'title':'one','link':'one'},{'title':'two','link':'two'}]
        self.bot=SimpleNamespace(player_enabled=True,server_management_enabled=False,tts_enabled=True,tts_cog=Mock(),
            playback_config={'max_volume':90},getMyUserID=lambda:1,getMyChannelID=lambda:8,
            getUser=lambda uid:SimpleNamespace(nUserID=uid),state_store=self.store,player_cog=self.cog,
            send_message=Mock(),send_broadcast_message=Mock(),_split_private_message=lambda text:[text],getServerUsers=lambda:[],
            runtime_snapshot_builder=SimpleNamespace(build_snapshot=lambda:{'player':{'queue_index':0}}))
        self.controls=WebControls(self.bot);self.bot.web_controls=self.controls
        self.addCleanup(self.controls.close)

    def drain(self):self.controls.pool.submit(lambda:None).result(timeout=2)

    def test_runtime_snapshot_exposes_actual_player_switch_settings(self):
        self.bot.playback_config.update({
            'send_channel_messages':False, 'announce_tracks':True,
            'announce_queue':False, 'announcement_tts_mode':'google',
        })
        self.bot.bot_config={'nickname':'Player'}
        self.bot.server_config={'address':'example.test','tcp_port':10333,'udp_port':10333}
        self.bot._state_flag=lambda name: 0
        self.bot.activity=Mock();self.bot.activity.recent.return_value=[]
        self.bot.player=SimpleNamespace(queue=[],queue_index=-1,queue_lock=threading.RLock(),
            queue_mode=True,is_playing=False,volume=60,speed=1.0,play_mode=2,
            current_link=None,media_title='',collection_results=[])
        snapshot=RuntimeSnapshotBuilder(self.bot).build_snapshot()['player']
        self.assertFalse(snapshot['channel_messages'])
        self.assertTrue(snapshot['announce_tracks'])
        self.assertFalse(snapshot['announce_queue'])
        self.assertEqual(snapshot['announcement_tts_mode'],'google')
        self.assertTrue(snapshot['queue_mode'])

    def test_player_cannot_broadcast_server_or_moderate(self):
        for action in ('announce_server','kick_user','ban_user','join_channel'):
            with self.assertRaises(ControlError):self.controls.submit({'action':action,'message':'hi','user_id':2,'channel_id':3})

    def test_typed_search_does_not_parse_command_text(self):
        self.controls.submit({'action':'play_youtube','query':'shutdown; restart / x'})
        self.drain();args=self.cog.handle_play_search_or_pause_command.call_args.args
        self.assertEqual(args[0].nFromUserID,WEB_ACTOR_ID)
        self.assertEqual(args[1],'shutdown; restart / x')

    def test_playlist_search_is_read_only_until_selected(self):
        expected=[{'title':'Thai Classics','link':'https://www.youtube.com/playlist?list=PL123456789AB','channel':'SN'}]
        self.bot.player=SimpleNamespace(search_playlists=Mock(return_value=expected),queue_mode=True)
        self.controls.submit({'action':'playlist_search','query':'Thai Classics'})
        self.drain()
        found=self.controls.playlist_search_snapshot()
        self.assertEqual(found['items'],expected)
        self.cog.handle_append_playlist_command.assert_not_called()
        self.controls.submit({'action':'playlist_choose','position':'1','search_token':found['token']})
        self.drain()
        args=self.cog.handle_append_playlist_command.call_args.args
        self.assertEqual(args[0].nFromUserID,WEB_ACTOR_ID)
        self.assertEqual(args[1],expected[0]['link'])
        self.assertEqual(self.controls.playlist_search_snapshot()['items'],[])

    def test_playlist_search_rejects_stale_or_forged_result(self):
        self.bot.player=SimpleNamespace(search_playlists=Mock(return_value=[
            {'title':'A','link':'https://www.youtube.com/playlist?list=PL123456789AB'}]))
        self.controls.submit({'action':'playlist_search','query':'A'});self.drain()
        token=self.controls.playlist_search_snapshot()['token']
        for payload in ({'action':'playlist_choose','position':1,'search_token':'forged'},
                        {'action':'playlist_choose','position':2,'search_token':token},
                        {'action':'playlist_search','query':''}):
            with self.assertRaises(ControlError):self.controls.submit(payload)
        self.assertFalse(self.cog.handle_append_playlist_command.called)

    def test_manager_timed_moderation_is_admin_only_and_validated(self):
        self.bot.player_enabled=False;self.bot.server_management_enabled=True
        self.bot.teamtalk_admin=SimpleNamespace(is_admin=lambda:True,available=lambda:[])
        self.bot.admin_cog=Mock();self.bot.jail_cog=Mock()
        self.bot.getMyChannelID=lambda:0
        for duration in ('1hour','-10m','0s','31d','1h:0m','999999w'):
            with self.assertRaises(ControlError):
                self.controls.submit({'action':'manager_timed_kick','nickname':'Alice','duration':duration})
        with self.assertRaises(ControlError):self.controls.submit({'action':'manager_clear_timed'})
        self.controls.submit({'action':'manager_timed_kick','nickname':'Alice','duration':'1h:30m'});self.drain()
        self.bot.admin_cog.handle_duration_kick_nickname.assert_called_with(unittest.mock.ANY,'Alice','1h:30m')
        self.controls.submit({'action':'manager_jail','nickname':'Alice'});self.drain()
        self.bot.jail_cog.handle_jail_command.assert_called_with(unittest.mock.ANY,'Alice')
        self.controls.submit({'action':'manager_clear_timed','confirm':'CLEAR'});self.drain()
        self.bot.admin_cog.handle_clear_command.assert_called_with(unittest.mock.ANY)
        self.bot.teamtalk_admin.is_admin=lambda:False
        self.assertNotIn('manager_jail',self.controls.available())

    def test_unknown_action_is_rejected(self):
        for action in ('exec','reboot','__dict__',None,[]):
            with self.assertRaises(ControlError):self.controls.submit({'action':action})

    def test_bounds_and_nonfinite_numbers(self):
        for payload in ({'action':'volume','value':-1},{'action':'volume','value':91},
                        {'action':'speed','value':'nan'},{'action':'seek','seconds':-1},
                        {'action':'play_url','url':'file:///etc/passwd'},{'action':'queue_mode','value':'other'}):
            with self.assertRaises(ControlError):self.controls.submit(payload)

    def test_mode_changes_mode_not_read_only_status(self):
        self.controls.submit({'action':'mode','value':'3'});self.drain()
        self.cog._set_play_mode.assert_called_once_with(3)
        self.cog.handle_mode_command.assert_not_called()

    def test_deleting_one_favorite_never_clears_all(self):
        self.controls.submit({'action':'favorite_delete','position':'1'});self.drain()
        self.assertEqual(self.cog.favorites,[{'title':'two','link':'two'}])
        self.cog.handle_delfav_command.assert_not_called();self.cog.save_favorites.assert_called_once()

    def test_invalid_favorite_position_preserves_everything(self):
        self.controls.submit({'action':'favorite_delete','position':'99'});self.drain()
        self.assertEqual(len(self.cog.favorites),2);self.assertEqual(self.controls.snapshot()['state'],'error')

    def test_manager_server_announcement_requires_no_current_room(self):
        self.bot.player_enabled=False;self.bot.server_management_enabled=True;self.bot.getMyChannelID=lambda:0
        self.controls.submit({'action':'announce_server','message':'hello all'});self.drain()
        self.bot.send_broadcast_message.assert_called_once_with('hello all')
        self.assertNotIn('play_youtube',self.controls.available())

    def test_role_sets_keep_playback_and_management_separate(self):
        self.assertIn('play_youtube',self.controls.available())
        self.assertNotIn('announce_channel',self.controls.available())
        self.assertNotIn('manager_filter',self.controls.available())
        self.bot.player_enabled=False;self.bot.server_management_enabled=True
        self.assertIn('announce_channel',self.controls.available())
        self.assertIn('manager_filter',self.controls.available())
        self.assertNotIn('delete_queue',self.controls.available())
        self.bot.player_enabled=True
        self.assertIn('delete_queue',self.controls.available())
        self.assertIn('manager_filter',self.controls.available())

    def test_manager_settings_use_existing_persistent_handlers(self):
        self.bot.player_enabled=False;self.bot.server_management_enabled=True
        self.bot.admin_cog=Mock()
        self.bot.general_cog=Mock()
        self.bot.getMyChannelID=lambda:0
        self.controls.submit({'action':'manager_filter','value':'on'})
        self.drain()
        args=self.bot.admin_cog.handle_filter_toggle_command.call_args.args
        self.assertEqual((args[0].nFromUserID,args[1]),(WEB_ACTOR_ID,'on'))
        self.controls.submit({'action':'manager_global_broadcast_interval','value':'180'})
        self.drain()
        self.bot.admin_cog.handle_central_global_broadcast_command.assert_called_with(
            unittest.mock.ANY, 'interval', '180')
        self.controls.submit({'action':'manager_intercept','value':'off'})
        self.drain()
        self.bot.general_cog.handle_intercept_command.assert_called_with(unittest.mock.ANY,'off')
        for value in ('0','10081','invalid'):
            with self.assertRaises(ControlError):
                self.controls.submit({'action':'manager_global_broadcast_interval','value':value})

    def test_queue_search_choice_targets_selected_entry_only(self):
        self.bot.player=SimpleNamespace(queue_mode=True)
        self.controls.submit({'action':'search_next','position':'4'});self.drain()
        self.cog.handle_next_search_result_selection.assert_called_once()
        args=self.cog.handle_next_search_result_selection.call_args.args
        self.assertEqual(args[1], '4')
        self.bot.player.queue_mode=False
        with self.assertRaises(ControlError):
            self.controls.submit({'action':'search_previous','position':'4'})

    def test_disconnected_requests_rejected(self):
        self.bot.getMyUserID=lambda:0
        with self.assertRaises(ControlError):self.controls.submit({'action':'stop'})

    def test_all_player_registry_handlers_exist(self):
        import ast
        tree=ast.parse((ROOT/'bot/modules/player.py').read_text())
        methods={node.name for node in ast.walk(tree) if isinstance(node,ast.FunctionDef)}
        for handler,*rest in PLAYER_ACTIONS.values():
            if handler is not None:self.assertIn(handler,methods)

    def test_own_announcement_echo_never_runs_commands(self):
        import ast, copy
        tree=ast.parse((ROOT/'bot/sntalkbot.py').read_text())
        method=copy.deepcopy(next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='onCmdUserTextMessage'))
        for argument in method.args.args:argument.annotation=None
        class Base:
            def onCmdUserTextMessage(self,message):self.echo_observed=True
        namespace={'Base':Base}
        module=ast.Module(body=[ast.ClassDef(name='EchoBot',bases=[ast.Name(id='Base',ctx=ast.Load())],keywords=[],body=[method],decorator_list=[])],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),'echo-test','exec'),namespace)
        bot=namespace['EchoBot']();bot.getMyUserID=lambda:42
        bot.onCmdUserTextMessage(SimpleNamespace(nFromUserID=42,szMessage='shutdown'))
        self.assertTrue(bot.echo_observed)

    def test_restore_failed_action_moves_saved_song_to_tail_without_duplicate(self):
        self.store.queue().append({'title':'failed','link':'https://example.test/failed'})
        self.store.archive_failed_queue_item(0,'playback',4)
        row=self.store.list_queue_failures()[0]
        self.controls.submit({'action':'retry_failed','failure_id':str(row['id'])});self.drain()
        self.assertEqual(self.store.queue_count(),1);self.assertEqual(self.store.list_queue_failures(),[])
        self.assertEqual(self.store.queue()[0]['title'],'failed')

    def test_http_token_and_role_enforced(self):
        import os
        from unittest.mock import patch
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        with patch.dict(os.environ,{'SNTALKBOT_API_PORT':str(port),'SNTALKBOT_API_TOKEN':'fixture-bearer-token'}):
            api=LocalStatusApi(self.bot);api.start();self.addCleanup(api.stop)
        url=f'http://127.0.0.1:{port}/v1/controls'
        with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(url)
        self.assertEqual(err.exception.code,401)
        req=urllib.request.Request(url,headers={'Authorization':'Bearer fixture-bearer-token'})
        with urllib.request.urlopen(req) as response:data=json.load(response)
        self.assertIn('play_youtube',data['actions']);self.assertEqual(data['status']['player']['queue_index'],0)
        req=urllib.request.Request(url,data=b'{"action":"announce_server","message":"no"}',headers={'Authorization':'Bearer fixture-bearer-token','Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
        self.assertEqual(err.exception.code,400)

if __name__=='__main__':unittest.main()
