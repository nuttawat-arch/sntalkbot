"""Bounded, typed TeamTalk server administration for the loopback web bridge.

Only TeamTalk SDK commands are issued here.  No shell, dynamic method names,
arbitrary struct fields, or credentials in snapshots/audit records.
"""
from __future__ import annotations

from copy import copy
import hashlib
from ipaddress import ip_address
import json
import re
from threading import Lock
import time


class AdminInputError(ValueError):
    pass


RIGHT_OPTIONS = {
    "voice": "USERRIGHT_TRANSMIT_VOICE",
    "channel_text": "USERRIGHT_TEXTMESSAGE_CHANNEL",
    "private_text": "USERRIGHT_TEXTMESSAGE_USER",
    "view_users": "USERRIGHT_VIEW_ALL_USERS",
    "create_channel": "USERRIGHT_CREATE_TEMPORARY_CHANNEL",
    "files_upload": "USERRIGHT_UPLOAD_FILES",
    "files_download": "USERRIGHT_DOWNLOAD_FILES",
    "media": "USERRIGHT_TRANSMIT_MEDIAFILE",
    "broadcast": "USERRIGHT_TEXTMESSAGE_BROADCAST",
    "kick": "USERRIGHT_KICK_USERS",
    "ban": "USERRIGHT_BAN_USERS",
    "move": "USERRIGHT_MOVE_USERS",
    "modify_channels": "USERRIGHT_MODIFY_CHANNELS",
    "operator": "USERRIGHT_OPERATOR_ENABLE",
    "server_settings": "USERRIGHT_UPDATE_SERVERPROPERTIES",
}

ADMIN_ACTIONS = frozenset({
    "server_update", "server_save", "server_stats", "accounts_refresh",
    "account_create", "account_delete", "bans_refresh", "unban_ip",
    "ban_ip", "channel_create", "channel_update", "channel_delete",
    "operator_set", "kick_channel", "ban_username", "unban_username",
})

SERVER_INT_FIELDS = {
    "max_users": ("nMaxUsers", 1, 1000),
    "max_login_attempts": ("nMaxLoginAttempts", 0, 1000),
    "logins_per_ip": ("nMaxLoginsPerIPAddress", 0, 1000),
    "user_timeout": ("nUserTimeout", 10, 3600),
    "login_delay_ms": ("nLoginDelayMSec", 0, 600000),
}


def as_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def number(value):
    """TeamTalkPy uses ctypes-derived enums, whose int() may not work."""
    return int(getattr(value, "value", value))


def bounded_text(payload, field, minimum=1, maximum=500):
    value = payload.get(field)
    if (not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum
            or len(value.strip().encode('utf-8')) > 500 or "\x00" in value):
        raise AdminInputError(f"ข้อมูล {field} ไม่ถูกต้อง (สูงสุด {maximum} ตัวอักษร)")
    return value.strip()


def bounded_int(payload, field, minimum, maximum):
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r"[0-9]+", str(value)):
        raise AdminInputError(f"{field} ต้องเป็นตัวเลข")
    result = int(value)
    if not minimum <= result <= maximum:
        raise AdminInputError(f"{field} ต้องอยู่ระหว่าง {minimum} ถึง {maximum}")
    return result


class TeamTalkAdministration:
    """Live administration cache and strict command dispatcher for Manager/Full."""

    def __init__(self, bot):
        self.bot = bot
        self.lock = Lock()
        self.accounts = []
        self.bans = []
        self.stats = {}
        self.accounts_at = 0.0
        self.bans_at = 0.0
        self.stats_at = 0.0

    def is_admin(self):
        try:
            from TeamTalk5 import UserType
            account = self.bot.getMyUserAccount()
            return number(account.uUserType) == number(UserType.USERTYPE_ADMIN)
        except (AttributeError, TypeError, ValueError):
            return False

    def available(self):
        return sorted(ADMIN_ACTIONS) if self.bot.server_management_enabled and self.is_admin() else []

    @staticmethod
    def revision(fields):
        return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

    @staticmethod
    def property_fields(props):
        return {"server_name": as_text(props.szServerName),
                "motd": as_text(props.szMOTDRaw),
                "version": as_text(props.szServerVersion),
                "auto_save": bool(props.bAutoSave),
                **{name: int(getattr(props, field)) for name, (field, _, _) in SERVER_INT_FIELDS.items()}}

    @staticmethod
    def channel_fields(ch):
        return {"id": int(ch.nChannelID), "parent_id": int(ch.nParentID),
                "name": as_text(ch.szName), "topic": as_text(ch.szTopic),
                "max_users": int(ch.nMaxUsers), "permanent": bool(number(ch.uChannelType) & 1),
                "has_password": bool(ch.bPassword)}

    def snapshot(self):
        result = {"is_admin": self.is_admin(), "properties": {}, "channels": [],
                  "accounts": [], "bans": [], "statistics": {}, "accounts_at": 0,
                  "bans_at": 0, "stats_at": 0, "rights": list(RIGHT_OPTIONS)}
        if not result["is_admin"]:
            return result
        try:
            props = self.bot.getServerProperties()
            if props:
                result["properties"] = self.property_fields(props)
                result["properties"]["revision"] = self.revision(result["properties"])
            channels = [self.channel_fields(ch) for ch in (self.bot.getServerChannels() or [])]
            for ch in channels:
                ch["revision"] = self.revision(ch)
            result["channels"] = sorted(channels, key=lambda x: (x["parent_id"], x["id"]))
        except Exception:
            # A disconnected bot should show unavailable, never an old server identity.
            result["properties"] = {}
            result["channels"] = []
        with self.lock:
            result.update(accounts=list(self.accounts), bans=list(self.bans),
                          statistics=dict(self.stats), accounts_at=self.accounts_at,
                          bans_at=self.bans_at, stats_at=self.stats_at)
        return result

    def on_account(self, account):
        row = {"username": as_text(account.szUsername), "user_type": number(account.uUserType),
               "rights": number(account.uUserRights),
               "init_channel": as_text(getattr(account, "szInitChannel", "")),
               "last_login": as_text(getattr(account, "szLastLoginTime", ""))}
        with self.lock:
            if len(self.accounts) < 500 and all(x["username"] != row["username"] for x in self.accounts):
                self.accounts.append(row)

    def on_ban(self, ban):
        row = {"ip": as_text(getattr(ban, "szIPAddress", "")),
               "username": as_text(getattr(ban, "szUsername", "")),
               "types": number(getattr(ban, "uBanTypes", 0))}
        with self.lock:
            if len(self.bans) < 500 and row not in self.bans:
                self.bans.append(row)

    def on_statistics(self, stats):
        fields = ("nTotalBytesTX", "nTotalBytesRX", "nVoiceBytesTX", "nVoiceBytesRX",
                  "nVideoCaptureBytesTX", "nVideoCaptureBytesRX", "nMediaFileBytesTX",
                  "nMediaFileBytesRX", "nServerUptimeMSec", "nUsersServed", "nUsersPeak")
        with self.lock:
            self.stats = {field: int(getattr(stats, field)) for field in fields if hasattr(stats, field)}
            self.stats_at = time.time()

    def validate(self, action, payload):
        if action not in self.available():
            raise AdminInputError("บัญชีบอตต้องมีสิทธิ์ TeamTalk Administrator")
        if action in {"server_save", "server_stats", "accounts_refresh", "bans_refresh"}:
            return {}
        if action == "server_update":
            result = {}
            if "revision" in payload:
                result["revision"] = bounded_text(payload, "revision", 64, 64)
                if not re.fullmatch(r"[0-9a-f]{64}", result["revision"]):
                    raise AdminInputError("ค่าอ้างอิงของเซิร์ฟเวอร์ไม่ถูกต้อง")
            for name in ("server_name", "motd"):
                if name in payload:
                    result[name] = bounded_text(payload, name, 0 if name == "motd" else 1, 500)
            for name, (_, low, high) in SERVER_INT_FIELDS.items():
                if name in payload:
                    result[name] = bounded_int(payload, name, low, high)
            if "auto_save" in payload:
                if payload["auto_save"] not in ("on", "off"):
                    raise AdminInputError("auto_save ไม่ถูกต้อง")
                result["auto_save"] = payload["auto_save"] == "on"
            if not (set(result) - {"revision"}):
                raise AdminInputError("กรุณาระบุการตั้งค่าที่ต้องการแก้")
            return result
        if action in {"channel_create", "channel_update"}:
            result = {"name": bounded_text(payload, "name", 1, 120),
                      "topic": bounded_text(payload, "topic", 0, 500),
                      "max_users": bounded_int(payload, "max_users", 0, 1000)}
            field = "parent_id" if action == "channel_create" else "channel_id"
            result[field] = bounded_int(payload, field, 1, 2147483647)
            value = payload.get("permanent", "off")
            if value not in ("on", "off"):
                raise AdminInputError("permanent ไม่ถูกต้อง")
            result["permanent"] = value == "on"
            password = payload.get("password", "")
            if not isinstance(password, str) or len(password) > 120 or "\x00" in password:
                raise AdminInputError("รหัสผ่านห้องไม่ถูกต้อง")
            if password:
                result["password"] = password
            if action == "channel_update" and "revision" in payload:
                result["revision"] = bounded_text(payload, "revision", 64, 64)
                if not re.fullmatch(r"[0-9a-f]{64}", result["revision"]):
                    raise AdminInputError("ค่าอ้างอิงของห้องไม่ถูกต้อง")
            return result
        if action in {"channel_delete", "account_delete"}:
            if payload.get("confirm") != "DELETE":
                raise AdminInputError("ต้องพิมพ์ DELETE เพื่อยืนยัน")
            return ({"channel_id": bounded_int(payload, "channel_id", 1, 2147483647)}
                    if action == "channel_delete" else
                    {"username": bounded_text(payload, "username", 1, 120)})
        if action == "account_create":
            username = bounded_text(payload, "username", 1, 120)
            if not re.fullmatch(r"[A-Za-z0-9_.@-]+", username):
                raise AdminInputError("ชื่อบัญชีใช้ได้เฉพาะตัวอักษร ตัวเลข และ _ . @ -")
            password = bounded_text(payload, "password", 8, 120)
            role = payload.get("role", "default")
            if role not in ("default", "admin"):
                raise AdminInputError("ประเภทบัญชีไม่ถูกต้อง")
            rights = payload.get("rights", "")
            if not isinstance(rights, str):
                raise AdminInputError("สิทธิ์บัญชีไม่ถูกต้อง")
            selections = [right for right in rights.split(",") if right]
            if len(selections) != len(set(selections)) or any(right not in RIGHT_OPTIONS for right in selections):
                raise AdminInputError("มีสิทธิ์ TeamTalk ที่ไม่รองรับ")
            return {"username": username, "password": password, "role": role, "rights": selections}
        if action in {"operator_set", "kick_channel"}:
            uid = bounded_int(payload, "user_id", 1, 2147483647)
            if uid == self.bot.getMyUserID() or not self.bot.getUser(uid):
                raise AdminInputError("ไม่สามารถเลือกบัญชีบอตหรือผู้ใช้ที่ไม่ออนไลน์")
            cid = bounded_int(payload, "channel_id", 1, 2147483647)
            if not self.bot.getChannel(cid):
                raise AdminInputError("ไม่พบห้อง")
            result = {"user_id": uid, "channel_id": cid}
            if action == "operator_set":
                if payload.get("enabled") not in ("on", "off"):
                    raise AdminInputError("เลือกเปิดหรือปิดสิทธิ์ Operator")
                result["enabled"] = payload["enabled"] == "on"
            return result
        if action in {"ban_ip", "unban_ip"}:
            raw = bounded_text(payload, "ip", 3, 45)
            try:
                ip_address(raw)
            except ValueError as exc:
                raise AdminInputError("กรุณากรอก IPv4 หรือ IPv6 ที่ถูกต้อง") from exc
            return {"ip": raw}
        if action in {"ban_username", "unban_username"}:
            username = bounded_text(payload, "username", 1, 120)
            if not re.fullmatch(r"[A-Za-z0-9_.@-]+", username):
                raise AdminInputError("ชื่อบัญชีไม่ถูกต้อง")
            return {"username": username}
        raise AdminInputError("ไม่พบรายการ")

    def dispatch(self, action, args):
        from TeamTalk5 import BanType, BannedUser, Channel, ChannelType, UserAccount, UserRight, UserType, ttstr
        if not self.is_admin():
            raise AdminInputError("บัญชีบอตไม่ได้รับสิทธิ์ Administrator แล้ว")
        bot = self.bot
        if action == "server_save":
            command = bot.doSaveConfig()
        elif action == "server_stats":
            command = bot.doQueryServerStats()
        elif action == "accounts_refresh":
            with self.lock:
                self.accounts = []
                self.accounts_at = time.time()
            command = bot.doListUserAccounts(0, 500)
        elif action == "bans_refresh":
            with self.lock:
                self.bans = []
                self.bans_at = time.time()
            command = bot.doListBans(0, 0, 500)
        elif action == "server_update":
            props = bot.getServerProperties()
            if not props:
                raise AdminInputError("ยังไม่ได้รับข้อมูลเซิร์ฟเวอร์")
            expected_revision = args.get("revision")
            if expected_revision and expected_revision != self.revision(self.property_fields(props)):
                raise AdminInputError("ค่าเซิร์ฟเวอร์ถูกแก้จากที่อื่นแล้ว กรุณารีเฟรชหน้าก่อนบันทึก")
            props = copy(props)
            for name, value in args.items():
                if name in SERVER_INT_FIELDS:
                    setattr(props, SERVER_INT_FIELDS[name][0], value)
                elif name == "server_name":
                    props.szServerName = ttstr(value)
                elif name == "motd":
                    props.szMOTDRaw = ttstr(value)
                elif name == "auto_save":
                    props.bAutoSave = value
            command = bot.doUpdateServer(props)
        elif action == "account_create":
            account = UserAccount()
            account.szUsername = ttstr(args["username"])
            account.szPassword = ttstr(args["password"])
            account.uUserType = (UserType.USERTYPE_ADMIN if args["role"] == "admin" else UserType.USERTYPE_DEFAULT)
            account.uUserRights = 0
            for right in args["rights"]:
                account.uUserRights = number(account.uUserRights) | number(getattr(UserRight, RIGHT_OPTIONS[right]))
            command = bot.doNewUserAccount(account)
        elif action == "account_delete":
            if args["username"].casefold() == str(bot.server_config.get("username", "")).casefold():
                raise AdminInputError("ไม่อนุญาตให้ลบบัญชีที่บอตกำลังใช้งาน")
            command = bot.doDeleteUserAccount(ttstr(args["username"]))
        elif action == "channel_create":
            parent = bot.getChannel(args["parent_id"])
            if not parent:
                raise AdminInputError("ไม่พบห้องแม่")
            channel = Channel()
            channel.nParentID = args["parent_id"]
            channel.szName = ttstr(args["name"])
            channel.szTopic = ttstr(args["topic"])
            channel.nMaxUsers = args["max_users"]
            channel.uChannelType = ChannelType.CHANNEL_PERMANENT if args["permanent"] else ChannelType.CHANNEL_DEFAULT
            if args.get("password"):
                channel.szPassword = ttstr(args["password"])
            channel.audiocodec = copy(parent.audiocodec)
            channel.audiocfg = copy(parent.audiocfg)
            command = bot.doMakeChannel(channel)
        elif action == "channel_update":
            current = bot.getChannel(args["channel_id"])
            if not current:
                raise AdminInputError("ไม่พบห้องที่จะแก้ไข")
            if args["name"] != as_text(current.szName):
                raise AdminInputError("TeamTalk SDK ไม่รองรับเปลี่ยนชื่อห้องด้วย UpdateChannel; กรุณาใช้ชื่อเดิม")
            expected_revision = args.get("revision")
            if expected_revision and expected_revision != self.revision(self.channel_fields(current)):
                raise AdminInputError("ข้อมูลห้องถูกเปลี่ยนจากที่อื่นแล้ว กรุณารีเฟรชหน้าก่อนแก้ไข")
            channel = copy(current)
            channel.szName = ttstr(args["name"])
            channel.szTopic = ttstr(args["topic"])
            channel.nMaxUsers = args["max_users"]
            if args["permanent"]:
                channel.uChannelType = number(channel.uChannelType) | number(ChannelType.CHANNEL_PERMANENT)
            else:
                channel.uChannelType = number(channel.uChannelType) & ~number(ChannelType.CHANNEL_PERMANENT)
            if args.get("password"):
                channel.szPassword = ttstr(args["password"])
            command = bot.doUpdateChannel(channel)
        elif action == "channel_delete":
            cid = args["channel_id"]
            if cid == bot.getRootChannelID() or not bot.getChannel(cid):
                raise AdminInputError("ไม่อนุญาตให้ลบห้องหลัก หรือห้องไม่อยู่แล้ว")
            command = bot.doRemoveChannel(cid)
        elif action == "operator_set":
            command = bot.doChannelOp(args["user_id"], args["channel_id"], args["enabled"])
        elif action == "kick_channel":
            user = bot.getUser(args["user_id"])
            if not user or int(user.nChannelID) != args["channel_id"]:
                raise AdminInputError("ผู้ใช้อยู่คนละห้องหรือออกไปแล้ว")
            command = bot.doKickUser(args["user_id"], args["channel_id"])
        elif action == "ban_ip":
            command = bot.doBanIPAddress(ttstr(args["ip"]), 0)
        elif action == "unban_ip":
            command = bot.doUnBanUser(ttstr(args["ip"]), 0)
        elif action in ("ban_username", "unban_username"):
            banned = BannedUser()
            banned.szUsername = ttstr(args["username"])
            banned.uBanTypes = BanType.BANTYPE_USERNAME
            command = bot.doBan(banned) if action == "ban_username" else bot.doUnbanUserEx(banned)
        else:
            raise AdminInputError("ไม่รองรับคำสั่ง")
        if not isinstance(command, int) or command <= 0:
            raise AdminInputError("TeamTalk ไม่รับคำขอ (อาจไม่มีสิทธิ์หรือขาดการเชื่อมต่อ)")
        return command
