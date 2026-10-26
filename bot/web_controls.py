"""Typed owner controls. No shell, command parser, or arbitrary method lookup."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlparse
import json
import math
import re
import secrets
import threading
import time
from bot.teamtalk_admin import ADMIN_ACTIONS, AdminInputError, as_text

WEB_ACTOR_ID = -2147483647
# action -> (handler, field, type, min, max)
PLAYER_ACTIONS = {
    'play_youtube': ('handle_play_search_or_pause_command', 'query', 'text', 1, 500),
    'play_music': ('handle_ytmusic_search_command', 'query', 'text', 1, 500),
    'play_url': ('handle_play_url_command', 'url', 'url', 1, 4096),
    'append_playlist': ('handle_append_playlist_command', 'url', 'url', 1, 4096),
    'playlist_search': (None, 'query', 'text', 1, 500),
    'playlist_choose': (None, 'position', 'int', 1, 15),
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
    'player_channel_messages': ('handle_channel_messages_command', 'value', 'choice', 0, 0),
    'player_tts_tracks': ('handle_player_tts_command', 'value', 'choice', 0, 0),
    'player_tts_queue': ('handle_player_tts_command', 'value', 'choice', 0, 0),
    'player_tts_engine': ('handle_player_tts_mode_command', 'value', 'engine', 0, 0),
    'player_tts_voice': ('handle_player_voice_command', 'value', 'text', 1, 120),
    'player_tts_rate': ('handle_player_tts_rate_command', 'value', 'int', -100, 100),
    'player_tts_speed': ('handle_player_tts_speed_command', 'value', 'float', 0.25, 4),
}
MANAGER_SETTINGS = {
    'manager_channel_input': 'handle_channel_input_command',
    'manager_intercept': 'handle_intercept_command',
    'manager_filter': 'handle_filter_toggle_command',
    'manager_welcome': 'handle_welcome_toggle_command',
    'manager_welcome_broadcast': 'handle_welcome_broadcast_toggle_command',
    'manager_vpn': 'handle_vpn_toggle_command',
    'manager_noname': 'handle_noname_toggle_command',
    'manager_global_broadcast': 'handle_central_global_broadcast_command',
    'manager_global_broadcast_tts': 'handle_central_global_broadcast_command',
    'manager_global_broadcast_interval': 'handle_central_global_broadcast_command',
}
MANAGER_OPERATIONS = {
    'manager_jail': ('jail_cog', 'handle_jail_command'),
    'manager_unjail': ('jail_cog', 'handle_unjail_command'),
    'manager_timed_ban_ip': ('admin_cog', 'handle_duration_ban_ip'),
    'manager_timed_ban_user': ('admin_cog', 'handle_duration_ban_user'),
    'manager_timed_kick': ('admin_cog', 'handle_duration_kick_nickname'),
    'manager_timed_kick_user': ('admin_cog', 'handle_duration_kick_by_username'),
    'manager_clear_timed': ('admin_cog', 'handle_clear_command'),
}
MANAGER_ACTIONS = {'announce_server', 'announce_channel', 'speak_channel',
                   'kick_user', 'ban_user', 'move_user', 'join_channel',
                   *MANAGER_SETTINGS, *MANAGER_OPERATIONS}


class ControlError(ValueError):
    pass


class WebControls:
    def __init__(self, bot):
        self.bot = bot
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='WebControls')
        self.slots = threading.BoundedSemaphore(8)
        self.lock = threading.Lock()
        self.last = {'state': 'idle'}
        self.history = []
        self.pending = {}
        self.early_responses = {}
        self.playlist_results = []
        self.playlist_search_query = ''
        self.playlist_search_token = ''
        self.playlist_search_expires_at = 0.0

    def available(self):
        result = set()
        if self.bot.player_enabled:
            result.update(PLAYER_ACTIONS)
            if not getattr(self.bot, 'tts_enabled', False) or getattr(self.bot, 'tts_cog', None) is None:
                result.difference_update(action for action in PLAYER_ACTIONS if action.startswith('player_tts_'))
        if self.bot.server_management_enabled:
            result.update(MANAGER_ACTIONS)
            if not getattr(self.bot, 'tts_enabled', False) or getattr(self.bot, 'tts_cog', None) is None:
                result.discard('speak_channel')
            admin = getattr(self.bot, 'teamtalk_admin', None)
            if admin is not None:
                result.update(admin.available())
            if admin is None or not admin.is_admin():
                result.difference_update(MANAGER_OPERATIONS)
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
        if action in ADMIN_ACTIONS:
            try:
                return action, self.bot.teamtalk_admin.validate(action, payload)
            except AdminInputError as exc:
                raise ControlError(str(exc)) from exc
        if action in MANAGER_SETTINGS:
            value = str(payload.get('value', '')).strip().lower()
            if action == 'manager_global_broadcast_interval':
                return action, [str(self.integer(payload, 'value', 1, 10080))]
            if value not in ('on', 'off'):
                raise ControlError('กรุณาเลือกเปิดหรือปิด')
            return action, [value]
        if action in MANAGER_OPERATIONS:
            admin = getattr(self.bot, 'teamtalk_admin', None)
            if admin is None or not admin.is_admin():
                raise ControlError('การจัดการโทษต้องใช้บัญชี TeamTalk Administrator')
            if action == 'manager_clear_timed':
                target = str(payload.get('target') or '').strip()
                if len(target) > 120 or any(ch in target for ch in '\r\n\x00'):
                    raise ControlError('ชื่อบัญชีหรือ IP ไม่ถูกต้อง')
                if not target and payload.get('confirm') != 'CLEAR':
                    raise ControlError('พิมพ์ CLEAR เพื่อยืนยันล้างโทษตามเวลาทั้งหมด')
                return action, [target] if target else []
            name = payload.get('nickname')
            if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 120
                    or any(ch in name for ch in '\r\n\x00')):
                raise ControlError('กรุณาเลือกผู้ใช้หรือกรอกชื่อบัญชีให้ถูกต้อง')
            args = [name.strip()]
            if action.startswith(('manager_timed_ban', 'manager_timed_kick')):
                duration = str(payload.get('duration') or '').strip().lower()
                if not re.fullmatch(r'[1-9][0-9]*[smhdw](?::[1-9][0-9]*[smhdw])*', duration):
                    raise ControlError('ระยะเวลาใช้รูปแบบ 30m, 2h หรือ 1h:30m')
                scale = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
                seconds = sum(int(part[:-1]) * scale[part[-1]] for part in duration.split(':'))
                if not 1 <= seconds <= 30 * 86400:
                    raise ControlError('ระยะเวลาต้องไม่เกิน 30 วัน')
                args.append(duration)
            return action, args
        args = []
        if action in PLAYER_ACTIONS:
            handler, field, kind, low, high = PLAYER_ACTIONS[action]
            if action == 'playlist_choose':
                with self.lock:
                    token = payload.get('search_token', '')
                    if (not isinstance(token, str) or not token
                            or token != self.playlist_search_token
                            or time.monotonic() >= self.playlist_search_expires_at):
                        raise ControlError('ผลค้นหา Playlist หมดอายุ กรุณาค้นหาอีกครั้ง')
            if action in ('search_next', 'search_previous') and 'position' in payload:
                if not getattr(getattr(self.bot, 'player', None), 'queue_mode', False):
                    raise ControlError('ต้องเปิดโหมดคิวก่อนเลือกผลค้นหาของรายการ')
                return action, [str(self.integer(payload, 'position', 1, 2147483647))]
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
                elif kind == 'engine':
                    if raw not in ('microsoft', 'google'):
                        raise ControlError('เลือก Microsoft หรือ Google')
                    value = raw
                args = [str(value)]
            if action == 'playlist_choose':
                with self.lock:
                    if int(args[0]) > len(self.playlist_results):
                        raise ControlError('ไม่พบ Playlist หมายเลขที่เลือก')
                args.append(payload['search_token'])
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
        if action not in ADMIN_ACTIONS and action not in MANAGER_SETTINGS and action not in MANAGER_OPERATIONS and action not in ('announce_server', 'join_channel', 'kick_user', 'ban_user', 'move_user') and not self.bot.getMyChannelID():
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
            self.history.append(self.last)
            del self.history[:-30]
        try:
            self.bot.state_store.set_meta('web_control_feedback', '')
            command_id = None
            if action in PLAYER_ACTIONS:
                cog = self.bot.player_cog
                # Values are structured fields. Never pass text to CommandHandler.
                if action == 'playlist_search':
                    results = self.bot.player.search_playlists(args[0], limit=10)
                    with self.lock:
                        self.playlist_results = [dict(row) for row in results]
                        self.playlist_search_query = args[0]
                        self.playlist_search_token = secrets.token_urlsafe(18) if results else ''
                        self.playlist_search_expires_at = time.monotonic() + 180 if results else 0
                    self.bot.state_store.set_meta('web_control_feedback',
                        f'พบ Playlist {len(results)} รายการ เลือกจากรายการด้านล่างเพื่อเพิ่มท้ายคิว')
                elif action == 'playlist_choose':
                    with self.lock:
                        if (not self.playlist_search_token or args[1] != self.playlist_search_token
                                or time.monotonic() >= self.playlist_search_expires_at):
                            raise ControlError('ผลค้นหา Playlist หมดอายุ กรุณาค้นหาอีกครั้ง')
                        chosen = self.playlist_results[int(args[0]) - 1]
                        self.playlist_search_token = ''
                        self.playlist_results = []
                    cog.handle_append_playlist_command(SimpleNamespace(nFromUserID=WEB_ACTOR_ID), chosen['link'])
                    self.bot.state_store.set_meta('web_control_feedback',
                        'ส่งคำขอเพิ่ม Playlist ท้ายรายการแล้ว โปรดตรวจสถานะคิวเมื่อโหลดเพลงเสร็จ')
                elif action == 'retry_failed':
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
                    prefix = ('tracks',) if action == 'player_tts_tracks' else (
                        ('queue',) if action == 'player_tts_queue' else ())
                    handler(SimpleNamespace(nFromUserID=WEB_ACTOR_ID), *prefix, *args)
            elif action in ADMIN_ACTIONS:
                try:
                    command_id = self.bot.teamtalk_admin.dispatch(action, args)
                except AdminInputError as exc:
                    raise ControlError(str(exc)) from exc
            elif action in MANAGER_SETTINGS:
                cog = (self.bot.general_cog if action in ('manager_channel_input', 'manager_intercept')
                       else self.bot.admin_cog)
                if cog is None:
                    raise ControlError('ระบบจัดการเซิร์ฟเวอร์ยังไม่พร้อม')
                handler = getattr(cog, MANAGER_SETTINGS[action])
                prefix = ('interval',) if action == 'manager_global_broadcast_interval' else (
                    ('tts',) if action == 'manager_global_broadcast_tts' else ())
                handler(SimpleNamespace(nFromUserID=WEB_ACTOR_ID), *prefix, *args)
                self.bot.state_store.set_meta('web_control_feedback', 'บันทึกการตั้งค่า Manager แล้ว')
            elif action in MANAGER_OPERATIONS:
                owner_name, method_name = MANAGER_OPERATIONS[action]
                cog = getattr(self.bot, owner_name, None)
                if cog is None:
                    raise ControlError('ระบบดูแลผู้ใช้ยังไม่พร้อม')
                getattr(cog, method_name)(SimpleNamespace(nFromUserID=WEB_ACTOR_ID), *args)
                self.bot.state_store.set_meta('web_control_feedback',
                    'ส่งคำสั่งจัดการผู้ใช้แล้ว กรุณาตรวจสถานะจริงกับ TeamTalk')
            elif action == 'announce_server':
                self.bot.send_broadcast_message(args[0])
            elif action == 'announce_channel':
                for chunk in self.bot._split_private_message(args[0]):
                    self.bot.send_message(chunk)
            elif action == 'speak_channel':
                if not self.bot.tts_cog.speak_global_broadcast(args[0], filename='web-announcement.mp3'):
                    raise ControlError('ยังอ่านออกเสียงไม่ได้ ระบบเสียงพูดอาจกำลังใช้งานหรือบริการเสียงไม่พร้อม')
            elif action == 'kick_user':
                if not self.bot.getUser(args[0]):
                    raise ControlError('ผู้ใช้ออกจากเซิร์ฟเวอร์แล้ว')
                command_id = self.bot.doKickUser(args[0], 0)
                if command_id <= 0:
                    raise ControlError('TeamTalk ไม่รับคำขอเตะผู้ใช้ออกจากเซิร์ฟเวอร์')
            elif action == 'ban_user':
                from TeamTalk5 import BanType, BannedUser, ttstr
                user = self.bot.getUser(args[0])
                if not user or not as_text(user.szUsername).strip():
                    raise ControlError('ไม่พบชื่อบัญชี TeamTalk สำหรับแบน')
                ban = BannedUser()
                ban.uBanTypes = BanType.BANTYPE_USERNAME
                ban.szUsername = ttstr(user.szUsername)
                command_id = self.bot.doBan(ban)
                if command_id <= 0:
                    raise ControlError('TeamTalk ไม่รับคำขอแบนผู้ใช้')
            elif action == 'move_user':
                if not self.bot.getChannel(args[1]):
                    raise ControlError('ไม่พบห้องปลายทาง')
                command_id = self.bot.doMoveUser(*args)
                if command_id <= 0:
                    raise ControlError('ส่งคำขอย้ายไม่สำเร็จ')
            elif action == 'join_channel':
                from TeamTalk5 import ttstr
                if not self.bot.getChannel(args[0]):
                    raise ControlError('ไม่พบห้องปลายทาง')
                command_id = self.bot.doJoinChannelByID(args[0], ttstr(args[1]))
                if command_id <= 0:
                    raise ControlError('ส่งคำขอเข้าห้องไม่สำเร็จ')
            with self.lock:
                if command_id is not None:
                    self.last.update(state='awaiting_server', command_id=command_id)
                    self.pending[command_id] = self.last
                    early = self.early_responses.pop(command_id, None)
                    if early:
                        self.last.update(early)
                        self.pending.pop(command_id, None)
                    if len(self.pending) > 50:
                        for old in sorted(self.pending)[:len(self.pending) - 50]:
                            self.pending.pop(old, None)
                else:
                    self.last.update(state='dispatched')
        except Exception as exc:
            with self.lock:
                self.last.update(state='error', error=str(exc) if isinstance(exc, ControlError) else type(exc).__name__)
        finally:
            self.slots.release()

    def on_command_processing(self, command_id, complete):
        if not complete:
            return
        with self.lock:
            entry = self.pending.pop(int(command_id), None)
            if entry:
                entry.update(state='confirmed', finished_at=time.time())
            elif int(command_id) not in self.early_responses:
                self.early_responses[int(command_id)] = {'state': 'confirmed', 'finished_at': time.time()}
                if len(self.early_responses) > 100:
                    self.early_responses.pop(next(iter(self.early_responses)))

    def on_command_error(self, command_id, error):
        message = as_text(getattr(error, 'szErrorMsg', 'TeamTalk rejected the command'))[:300]
        with self.lock:
            entry = self.pending.pop(int(command_id), None)
            if entry:
                entry.update(state='rejected', error=message, finished_at=time.time())
            else:
                self.early_responses[int(command_id)] = {'state': 'rejected', 'error': message, 'finished_at': time.time()}
                if len(self.early_responses) > 100:
                    self.early_responses.pop(next(iter(self.early_responses)))

    def snapshot(self):
        with self.lock:
            return dict(self.last)

    def history_snapshot(self):
        with self.lock:
            return [dict(row) for row in reversed(self.history)]

    def playlist_search_snapshot(self):
        with self.lock:
            if time.monotonic() >= self.playlist_search_expires_at:
                return {'query': '', 'token': '', 'items': []}
            return {'query': self.playlist_search_query,
                    'token': self.playlist_search_token,
                    'items': [dict(row) for row in self.playlist_results]}

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
