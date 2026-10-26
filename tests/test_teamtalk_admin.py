"""Offline contract tests for the official TeamTalk SDK administration bridge."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot.teamtalk_admin import TeamTalkAdministration, AdminInputError
from bot.web_controls import WebControls


class Account:
    def __init__(self):
        self.szUsername = ''
        self.szPassword = ''
        self.uUserRights = 0
        self.uUserType = 0


class Channel:
    def __init__(self, channel_id=0):
        self.nChannelID = channel_id
        self.nParentID = 1
        self.szName = 'Room'
        self.szTopic = 'Old topic'
        self.szPassword = 'old secret'
        self.bPassword = True
        self.uChannelType = 1
        self.nMaxUsers = 15
        self.audiocodec = SimpleNamespace(codec=2)
        self.audiocfg = SimpleNamespace(gain=1)


SDK = SimpleNamespace(UserType=SimpleNamespace(USERTYPE_ADMIN=2, USERTYPE_DEFAULT=1),
                      BanType=SimpleNamespace(BANTYPE_USERNAME=1), BannedUser=SimpleNamespace,
                      UserRight=SimpleNamespace(USERRIGHT_TRANSMIT_VOICE=0x20,
                                                USERRIGHT_TEXTMESSAGE_CHANNEL=0x40),
                      ChannelType=SimpleNamespace(CHANNEL_DEFAULT=0, CHANNEL_PERMANENT=1),
                      UserAccount=Account, Channel=Channel, ttstr=lambda x: x)


class TeamTalkAdminTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(sys.modules, {'TeamTalk5': SDK})
        patcher.start(); self.addCleanup(patcher.stop)
        self.props = SimpleNamespace(szServerName='Production', szMOTDRaw='Hello',
                                     szMOTD='Hello', szServerVersion='5.22A', bAutoSave=0,
                                     nMaxUsers=100, nMaxLoginAttempts=4,
                                     nMaxLoginsPerIPAddress=2, nUserTimeout=60, nLoginDelayMSec=0,
                                     szAccessToken='SECRET')
        self.channel = Channel(2)
        self.bot = SimpleNamespace(player_enabled=False, tts_enabled=False,
                                   server_management_enabled=True, server_config={'username':'bot'},
                                   getMyUserAccount=lambda:SimpleNamespace(uUserType=2),
                                   getMyUserID=lambda:3, getMyChannelID=lambda:0,
                                   getUser=lambda uid:SimpleNamespace(nUserID=uid,nChannelID=2),
                                   getServerProperties=lambda:self.props,
                                   getServerChannels=lambda:[self.channel],
                                   getChannel=lambda cid:self.channel if cid in (1,2) else None,
                                   getRootChannelID=lambda:1,
                                   doUpdateServer=Mock(return_value=31), doMakeChannel=Mock(return_value=32),
                                   doUpdateChannel=Mock(return_value=33), doRemoveChannel=Mock(return_value=34),
                                   doSaveConfig=Mock(return_value=35), doQueryServerStats=Mock(return_value=36),
                                   doListUserAccounts=Mock(return_value=37), doListBans=Mock(return_value=38),
                                   doDeleteUserAccount=Mock(return_value=39), doNewUserAccount=Mock(return_value=40),
                                   doBanIPAddress=Mock(return_value=41), doUnBanUser=Mock(return_value=42),
                                   doBan=Mock(return_value=45), doUnbanUserEx=Mock(return_value=46),
                                   doChannelOp=Mock(return_value=43), doKickUser=Mock(return_value=44),
                                   state_store=SimpleNamespace(set_meta=lambda *args:None))
        self.admin = TeamTalkAdministration(self.bot)
        self.bot.teamtalk_admin = self.admin

    def test_non_admin_cannot_view_or_mutate(self):
        self.bot.getMyUserAccount=lambda:SimpleNamespace(uUserType=1)
        self.assertEqual(self.admin.available(), [])
        with self.assertRaises(AdminInputError):self.admin.validate('server_save', {})
        self.assertEqual(self.admin.snapshot()['properties'], {})

    def test_snapshot_never_leaks_access_token_password_or_account_password(self):
        self.admin.on_account(SimpleNamespace(szUsername='alice', szPassword='TOPSECRET',
                                               uUserType=1, uUserRights=7, szLastLoginTime='recent'))
        import json
        result=json.dumps(self.admin.snapshot())
        self.assertIn('alice',result)
        self.assertNotIn('TOPSECRET',result)
        self.assertNotIn('SECRET',result)
        self.assertNotIn('old secret',result)

    def test_server_update_does_not_reset_unsubmitted_properties(self):
        args=self.admin.validate('server_update',{'server_name':'New title','max_users':'80'})
        self.assertEqual(self.admin.dispatch('server_update',args),31)
        sent=self.bot.doUpdateServer.call_args.args[0]
        self.assertEqual(sent.szServerName,'New title')
        self.assertEqual(sent.nMaxUsers,80)
        self.assertEqual(sent.nMaxLoginAttempts,4)
        self.assertEqual(self.props.szServerName,'Production')
        self.assertEqual(sent.szAccessToken,'SECRET')

    def test_stale_remote_forms_cannot_overwrite_updated_settings(self):
        revision=self.admin.snapshot()['properties']['revision']
        args=self.admin.validate('server_update',{'server_name':'Old page','revision':revision})
        self.props.szServerName='Changed on another client'
        with self.assertRaises(AdminInputError):self.admin.dispatch('server_update',args)
        self.bot.doUpdateServer.assert_not_called()
        channel_revision=self.admin.snapshot()['channels'][0]['revision']
        chargs=self.admin.validate('channel_update',{'channel_id':'2','name':'Room',
                'topic':'Old topic','max_users':'15','permanent':'on','revision':channel_revision})
        self.channel.szTopic='External edit'
        with self.assertRaises(AdminInputError):self.admin.dispatch('channel_update',chargs)
        self.bot.doUpdateChannel.assert_not_called()

    def test_channel_update_keeps_codec_flags_and_password(self):
        args=self.admin.validate('channel_update',{'channel_id':'2','name':'Room',
                    'topic':'Topic','max_users':'27','permanent':'off','password':''})
        self.admin.dispatch('channel_update',args)
        sent=self.bot.doUpdateChannel.call_args.args[0]
        self.assertEqual(sent.szPassword,'old secret')
        self.assertEqual(sent.uChannelType,0)
        self.assertEqual(sent.audiocodec.codec,2)
        self.assertEqual(self.channel.szName,'Room')

    def test_unsupported_sdk_channel_rename_is_rejected_not_silently_confirmed(self):
        args=self.admin.validate('channel_update',{'channel_id':'2','name':'Misleading rename',
                    'topic':'Topic','max_users':'27','permanent':'on'})
        with self.assertRaisesRegex(AdminInputError,'ไม่รองรับเปลี่ยนชื่อห้อง'):
            self.admin.dispatch('channel_update',args)
        self.bot.doUpdateChannel.assert_not_called()

    def test_create_account_uses_allowlisted_rights(self):
        args=self.admin.validate('account_create',{'username':'fresh_user','password':'long-password',
                    'role':'default','rights':'voice,channel_text'})
        self.assertEqual(self.admin.dispatch('account_create',args),40)
        account=self.bot.doNewUserAccount.call_args.args[0]
        self.assertEqual(account.uUserRights,0x60)
        self.assertEqual(account.uUserType,1)
        for rights in ('voice,voice','voice,server_admin','../../etc'):
            with self.assertRaises(AdminInputError):
                self.admin.validate('account_create',{'username':'fresh','password':'long-password','rights':rights})

    def test_delete_guard_root_self_and_ip_validation(self):
        with self.assertRaises(AdminInputError):self.admin.validate('channel_delete',{'channel_id':'2'})
        with self.assertRaises(AdminInputError):self.admin.dispatch('channel_delete',{'channel_id':1})
        with self.assertRaises(AdminInputError):self.admin.dispatch('account_delete',{'username':'bot'})
        with self.assertRaises(AdminInputError):self.admin.validate('ban_ip',{'ip':'127.0.0.1; echo hi'})
        with self.assertRaises(AdminInputError):
            self.admin.validate('operator_set',{'user_id':'3','channel_id':'2','enabled':'on'})

    def test_offline_username_ban_uses_bearware_banneduser(self):
        self.admin.dispatch('ban_username',self.admin.validate('ban_username',{'username':'offline'}))
        banned=self.bot.doBan.call_args.args[0]
        self.assertEqual(banned.szUsername,'offline')
        self.admin.dispatch('unban_username',self.admin.validate('unban_username',{'username':'offline'}))
        self.assertEqual(self.bot.doUnbanUserEx.call_args.args[0].szUsername,'offline')

    def test_web_control_waits_for_sdk_confirmation(self):
        controls=WebControls(self.bot)
        self.addCleanup(controls.close)
        self.assertIn('server_update',controls.available())
        controls.submit({'action':'server_update','server_name':'Updated'})
        controls.pool.submit(lambda:None).result(timeout=2)
        self.assertEqual(controls.snapshot()['state'],'awaiting_server')
        controls.on_command_processing(31,True)
        self.assertEqual(controls.snapshot()['state'],'confirmed')
        controls.submit({'action':'server_update','server_name':'Second'})
        controls.pool.submit(lambda:None).result(timeout=2)
        controls.on_command_error(31,SimpleNamespace(szErrorMsg='Access denied'))
        self.assertEqual(controls.snapshot()['state'],'rejected')
        self.assertEqual(controls.snapshot()['error'],'Access denied')

    def test_web_kick_and_ban_wait_for_actual_teamtalk_confirmation(self):
        self.bot.getUser=lambda uid:SimpleNamespace(nUserID=uid,nChannelID=2,szUsername='guest')
        controls=WebControls(self.bot)
        self.addCleanup(controls.close)
        controls.submit({'action':'kick_user','user_id':5})
        controls.pool.submit(lambda:None).result(timeout=2)
        self.bot.doKickUser.assert_called_once_with(5,0)
        self.assertEqual(controls.snapshot()['state'],'awaiting_server')
        controls.on_command_error(44,SimpleNamespace(szErrorMsg='Not authorized'))
        self.assertEqual(controls.snapshot()['state'],'rejected')
        controls.submit({'action':'ban_user','user_id':5})
        controls.pool.submit(lambda:None).result(timeout=2)
        self.assertEqual(self.bot.doBan.call_args.args[0].szUsername,'guest')
        self.assertEqual(controls.snapshot()['state'],'awaiting_server')
        controls.on_command_processing(45,True)
        self.assertEqual(controls.snapshot()['state'],'confirmed')

    def test_early_sdk_response_is_not_lost(self):
        controls=WebControls(self.bot)
        self.addCleanup(controls.close)
        controls.on_command_processing(35,True)
        controls.submit({'action':'server_save'})
        controls.pool.submit(lambda:None).result(timeout=2)
        self.assertEqual(controls.snapshot()['state'],'confirmed')


if __name__=='__main__':unittest.main()
