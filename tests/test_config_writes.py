from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import patch
import configparser
import importlib.util
import sys
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ConfigWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'config.ini'
        self.path.write_text('[server]\naddress=original.example\nusername=bot\npassword=token%25!\n[bot]\nlanguage=th\n[playback]\nqueue_mode=False\n')
        spec=importlib.util.spec_from_file_location('_tested_config_writes',ROOT/'bot/config_handler.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'TeamTalk5':ModuleType('TeamTalk5'),'mpv':ModuleType('mpv')}):spec.loader.exec_module(self.module)
        self.handler=self.module.ConfigHandler.__new__(self.module.ConfigHandler)
        self.handler.config_file=str(self.path);self.handler.language='th';self.handler._config_write_lock=threading.RLock()
        self.handler.config=configparser.ConfigParser(interpolation=None);self.handler.config.read(self.path)

    def read(self):
        cfg=configparser.ConfigParser(interpolation=None);cfg.read(self.path);return cfg

    def test_bot_setting_does_not_overwrite_new_web_server(self):
        cfg=self.read();cfg.set('server','address','new-web.example')
        with self.path.open('w') as handle:cfg.write(handle)
        self.handler.update_playback_settings({'queue_mode':True})
        actual=self.read();self.assertEqual(actual.get('server','address'),'new-web.example')
        self.assertEqual(actual.get('server','password'),'token%25!');self.assertTrue(actual.getboolean('playback','queue_mode'))

    def test_failed_atomic_replace_keeps_original_file(self):
        before=self.path.read_bytes()
        with patch.object(self.module.os,'replace',side_effect=OSError('injected disk failure')):
            with self.assertRaises(OSError):self.handler.update_playback_settings({'queue_mode':True})
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(list(self.path.parent.glob('.config-*')),[])

    def test_missing_config_is_not_recreated_from_memory(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):self.handler.update_playback_settings({'queue_mode':True})
        self.assertFalse(self.path.exists())

    def test_runtime_save_cannot_revert_default_room_from_web(self):
        cfg=self.read();cfg.set('bot','default_channel','/new-web-room');cfg.set('bot','channel_password','new-secret')
        with self.path.open('w') as handle:cfg.write(handle)
        self.handler.save_bot_config({'default_channel':'/old','channel_password':'old-secret','nickname':'Updated'})
        actual=self.read();self.assertEqual(actual.get('bot','default_channel'),'/new-web-room')
        self.assertEqual(actual.get('bot','channel_password'),'new-secret')
        self.assertEqual(actual.get('bot','nickname'),'Updated')

    def test_concurrent_settings_updates_preserve_all_fields(self):
        threads=[threading.Thread(target=self.handler.update_playback_settings,args=({f'field_{i}':i},)) for i in range(10)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        actual=self.read()
        for i in range(10):self.assertEqual(actual.getint('playback',f'field_{i}'),i)
        self.assertEqual(actual.get('server','address'),'original.example')

if __name__=='__main__':unittest.main()
