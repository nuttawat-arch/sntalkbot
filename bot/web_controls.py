"""Typed owner controls. No shell, command parser, or arbitrary method lookup."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlparse
import json
import math
import threading
import time

WEB_ACTOR_ID = -2147483647
# action -> (handler, field, type, min, max)
PLAYER_ACTIONS = {
    'play_youtube': ('handle_play_search_or_pause_command', 'query', 'text', 1, 500),
    'play_music': ('handle_ytmusic_search_command', 'query', 'text', 1, 500),
    'play_url': ('handle_play_url_command', 'url', 'url', 1, 4096),
    'append_playlist': ('handle_append_playlist_command', 'url', 'url', 1, 4096),
    'retry_failed': (None, 'failure_id', 'int', 1, 2147483647),
    'restart_track': ('handle_play_search_or_pause_command', None, None, 0, 0),
    'pause_resume': ('handle_pause_resume_command', None, None, 0, 0),
    'stop': ('handle_stop_command', None, None, 0, 0),
    'search_next': ('handle_next_search_result_selection', None, None, 0, 0),
    'search_previous': ('handle_prev_search_result_selection', None, None, 0, 0),
    'next': ('handle_next_track_command', None, None, 0, 0),
    'previous': ('handle_previous_track_command', None, None, 0, 0),
    'seek': ('handle_seek_to_time_command', 'seconds', 'int', 0, 604800),
    'volume': ('handle_change_volume_command', 'value', 'int', 0, 150),
    'speed': ('handle_speed_command', 'value', 'float', 0.25, 4),
    'select': ('handle_select_command', 'position', 'int', 1, 2147483647),
    'delete_queue': ('handle_delete_queue_command', 'position', 'int', 1, 2147483647),
    'clear_queue': ('handle_clear_queue_command', None, None, 0, 0),
    'shuffle': ('handle_shuffle_command', None, None, 0, 0),
    'queue_mode': ('handle_queue_toggle_command', 'value', 'choice', 0, 0),
    'mode': ('handle_mode_command', 'value', 'mode', 1, 3),
    'favorite_add': ('handle_fav_command', None, None, 0, 0),
    'favorite_play': ('handle_playfav_command', None, None, 0, 0),
    'favorite_delete': ('handle_delfav_command', 'position', 'int', 1, 2147483647),
    'stereo': ('handle_3d_command', None, None, 0, 0),
    'extra_stereo': ('handle_3d2_command', None, None, 0, 0),
    'bass': ('handle_bass_command', None, None, 0, 0),
    'fade': ('handle_fade_command', None, None, 0, 0),
}
COMMON_ACTIONS = {'announce_channel', 'speak_channel'}
MANAGER_ACTIONS = {'announce_server', 'kick_user', 'ban_user', 'move_user', 'join_channel'}


class ControlError(ValueError):
    pass


class WebControls:
    def __init__(self, bot):
        self.bot = bot
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='WebControls')
        self.slots = threading.BoundedSemaphore(8)
        self.lock = threading.Lock()
        self.last = {'state': 'idle'}

    def available(self):
        result = set(COMMON_ACTIONS)
        if not getattr(self.bot, 'tts_enabled', False) or getattr(self.bot, 'tts_cog', None) is None:
            result.discard('speak_channel')
        if self.bot.player_enabled:
            result.update(PLAYER_ACTIONS)
        if self.bot.server_management_enabled:
            result.update(MANAGER_ACTIONS)
        return sorted(result)

    @staticmethod
    def integer(payload, name, low, high):
        raw = payload.get(name)
        if isinstance(raw, bool):
            raise ControlError('ค่าตัวเลขไม่ถูกต้อง')
        try:
            value = int(str(raw))
        except (ValueError, TypeError):
            raise ControlError('ค่าตัวเลขไม่ถูกต้อง')
        if not low <= value <= high:
            raise ControlError(f'ค่าต้องอยู่ระหว่าง {low} ถึง {high}')
        return value

    def validate(self, payload):
        action = payload.get('action')
        if not isinstance(action, str) or action not in self.available():
            raise ControlError('บอตนี้ไม่รองรับรายการที่เลือก')
        args = []
        if action in PLAYER_ACTIONS:
            handler, field, kind, low, high = PLAYER_ACTIONS[action]
            if field:
                raw = payload.get(field, '')
                if kind in ('text', 'url'):
                    if not isinstance(raw, str) or not low <= len(raw.strip()) <= high:
                        raise ControlError('กรุณากรอกข้อมูลให้ครบและไม่เกินความยาวที่กำหนด')
                    value = raw.strip()
                    if kind == 'url':
                        parsed = urlparse(value)
                        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                            raise ControlError('ใช้ลิงก์ http หรือ https เท่านั้น')
                elif kind in ('int', 'mode'):
                    value = self.integer(payload, field, low, high)
                    if action == 'volume':
                        max_volume = int(self.bot.playback_config.get('max_volume', 150))
                        if value > max_volume:
                            raise ControlError('เกินระดับเสียงสูงสุดของบอต')
                elif kind == 'float':
                    try:
                        value = float(raw)
                    except (ValueError, TypeError):
                        raise ControlError('ความเร็วไม่ถูกต้อง')
                    if not math.isfinite(value) or not low <= value <= high:
                        raise ControlError('ความเร็วต้องอยู่ระหว่าง 0.25 ถึง 4')
                elif kind == 'choice':
                    if raw not in ('on', 'off'):
                        raise ControlError('เลือกเปิดหรือปิด')
                    value = raw
                args = [str(value)]
        elif action.startswith('announce_') or action == 'speak_channel':
            message = payload.get('message')
            if not isinstance(message, str) or not message.strip() or len(message.encode('utf-8')) > 12000:
                raise ControlError('กรุณากรอกข้อความไม่เกิน 12000 ไบต์')
            args = [message.strip()]
            if action == 'speak_channel' and (not self.bot.tts_enabled or self.bot.tts_cog is None):
                raise ControlError('ยังไม่ได้เปิดระบบเสียงพูด')
        elif action in ('kick_user', 'ban_user', 'move_user'):
            user_id = self.integer(payload, 'user_id', 1, 2147483647)
            if user_id == self.bot.getMyUserID() or not self.bot.getUser(user_id):
                raise ControlError('ไม่พบผู้ใช้หรือเป็นตัวบอตเอง')
            args = [user_id]
            if action == 'move_user':
                args.append(self.integer(payload, 'channel_id', 1, 2147483647))
        elif action == 'join_channel':
            channel_id = self.integer(payload, 'channel_id', 1, 2147483647)
            password = payload.get('password', '')
            if not isinstance(password, str) or len(password) > 512:
                raise ControlError('รหัสห้องไม่ถูกต้อง')
            args = [channel_id, password]
        return action, args

    def submit(self, payload):
        action, args = self.validate(payload)
        if not self.bot.getMyUserID():
            raise ControlError('บอตยังไม่ได้เชื่อมต่อ TeamTalk')
        if action not in ('announce_server', 'join_channel', 'kick_user', 'ban_user', 'move_user') and not self.bot.getMyChannelID():
            raise ControlError('บอตยังไม่ได้เข้าห้อง')
        if not self.slots.acquire(blocking=False):
            raise ControlError('มีงานรออยู่มาก กรุณาลองใหม่ภายหลัง')
        try:
            self.pool.submit(self._run, action, args)
        except Exception:
            self.slots.release()
            raise
        return {'ok': True, 'accepted': True}

    def _run(self, action, args):
        with self.lock:
            self.last = {'action': action, 'state': 'dispatching', 'at': time.time()}
        try:
            self.bot.state_store.set_meta('web_control_feedback', '')
            if action in PLAYER_ACTIONS:
                cog = self.bot.player_cog
                # Values are structured fields. Never pass text to CommandHandler.
                if action == 'retry_failed':
                    if not self.bot.state_store.restore_queue_failure(int(args[0])):
                        raise ControlError('รายการนี้ถูกส่งกลับคิวไปแล้วหรือไม่พบรายการ')
                    self.bot.state_store.set_meta('web_control_feedback', 'ส่งรายการกลับท้ายคิวแล้ว')
                elif action == 'favorite_delete':
                    index = int(args[0]) - 1
                    if not 0 <= index < len(cog.favorites):
                        raise ControlError('ไม่พบรายการโปรดตำแหน่งนี้')
                    del cog.favorites[index]
                    cog.save_favorites()
                elif action == 'mode':
                    cog._set_play_mode(int(args[0]))
                else:
                    handler = getattr(cog, PLAYER_ACTIONS[action][0])
                    handler(SimpleNamespace(nFromUserID=WEB_ACTOR_ID), *args)
            elif action == 'announce_server':
                self.bot.send_broadcast_message(args[0])
            elif action == 'announce_channel':
                for chunk in self.bot._split_private_message(args[0]):
                    self.bot.send_message(chunk)
            elif action == 'speak_channel':
                if not self.bot.tts_cog.speak_global_broadcast(args[0], filename='web-announcement.mp3'):
                    raise ControlError('ยังอ่านออกเสียงไม่ได้ ระบบเสียงพูดอาจกำลังใช้งานหรือบริการเสียงไม่พร้อม')
            elif action == 'kick_user':
                if not self.bot.kick_user(args[0]):
                    raise ControlError('ผู้ใช้ออกจากเซิร์ฟเวอร์แล้ว')
            elif action == 'ban_user':
                if not self.bot.admin_cog.ban_user(args[0]):
                    raise ControlError('ไม่สามารถส่งคำขอแบนได้')
            elif action == 'move_user':
                if not self.bot.getChannel(args[1]):
                    raise ControlError('ไม่พบห้องปลายทาง')
                if self.bot.doMoveUser(*args) <= 0:
                    raise ControlError('ส่งคำขอย้ายไม่สำเร็จ')
            elif action == 'join_channel':
                from TeamTalk5 import ttstr
                if not self.bot.getChannel(args[0]) or self.bot.doJoinChannelByID(args[0], ttstr(args[1])) <= 0:
                    raise ControlError('ส่งคำขอเข้าห้องไม่สำเร็จ')
            with self.lock:
                self.last.update(state='dispatched')
        except Exception as exc:
            with self.lock:
                self.last.update(state='error', error=str(exc) if isinstance(exc, ControlError) else type(exc).__name__)
        finally:
            self.slots.release()

    def snapshot(self):
        with self.lock:
            return dict(self.last)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
