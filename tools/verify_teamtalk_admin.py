#!/usr/bin/env python3
"""One-shot TeamTalk Administrator credential verifier.

Reads a small JSON object from stdin so the password never appears in argv.
Prints a secret-free JSON result to stdout and exits non-zero on failure.
Designed to run inside the SNTalkBot Docker image where TeamTalk5 is installed.
"""
from __future__ import annotations

import json
import sys
import threading
import time

from TeamTalk5 import TeamTalk, UserType, ttstr

MAX_STDIN = 16384


def fail(message: str, code: int = 2) -> int:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    return code


class AdminProbe(TeamTalk):
    def __init__(self, username: str, password: str):
        super().__init__()
        self.username = username
        self.password = password
        self.done = threading.Event()
        self.result = None
        self.error = None

    def _finish_error(self, message: str):
        if not self.done.is_set():
            self.error = message
            self.done.set()

    def onConnectSuccess(self):
        try:
            cmdid = self.doLogin(
                ttstr("SNTalkBot Web verification"),
                ttstr(self.username),
                ttstr(self.password),
                ttstr("SNTalkBot Web verifier"),
            )
            if int(cmdid) < 0:
                self._finish_error("TeamTalk rejected the login command")
        except Exception:
            self._finish_error("Unable to send TeamTalk login command")

    def onConnectFailed(self):
        self._finish_error("Unable to connect to the TeamTalk server")

    def onConnectionLost(self):
        self._finish_error("TeamTalk connection was lost during verification")

    def onCmdMyselfLoggedIn(self, userid, useraccount):
        try:
            user_type = int(getattr(useraccount, "uUserType", 0) or 0)
            account_username = ttstr(getattr(useraccount, "szUsername", "")) or self.username
            is_admin = user_type == int(UserType.USERTYPE_ADMIN)
            self.result = {
                "ok": bool(is_admin),
                "authenticated": True,
                "administrator": bool(is_admin),
                "username": account_username,
                "user_id": int(userid or 0),
                "user_type": user_type,
            }
            if not is_admin:
                self.result["error"] = "TeamTalk credentials are valid, but the account is not an Administrator"
        except Exception:
            self._finish_error("Unable to inspect the authenticated TeamTalk account type")
            return
        self.done.set()

    def onCmdError(self, cmdid, error):
        # Never echo the password or raw structures. The common invalid-account
        # path is intentionally collapsed to one safe message.
        self._finish_error("TeamTalk login failed; check username/password and server access")


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_STDIN + 1)
    if len(raw) > MAX_STDIN:
        return fail("verification request is too large")
    try:
        req = json.loads(raw.decode("utf-8"))
    except Exception:
        return fail("invalid verification request")

    host = str(req.get("hostname") or "").strip()
    username = str(req.get("username") or "").strip()
    password = str(req.get("password") or "")
    try:
        tcp_port = int(req.get("tcp_port") or 10333)
        udp_port = int(req.get("udp_port") or 10333)
    except Exception:
        return fail("invalid TeamTalk port")
    encrypted = bool(req.get("encrypted"))
    timeout = max(3.0, min(float(req.get("timeout") or 15.0), 30.0))

    if not host or not username:
        return fail("hostname and TeamTalk username are required")
    if not (1 <= tcp_port <= 65535 and 1 <= udp_port <= 65535):
        return fail("TeamTalk ports must be 1-65535")

    probe = None
    loop_thread = None
    try:
        probe = AdminProbe(username, password)
        if not probe.connect(ttstr(host), tcp_port, udp_port, bEncrypted=encrypted):
            return fail("Unable to start TeamTalk connection")
        loop_thread = threading.Thread(target=probe.runEventLoop, daemon=True, name="TeamTalkAdminVerify")
        loop_thread.start()
        if not probe.done.wait(timeout):
            return fail("Timed out while verifying TeamTalk credentials")
        if probe.error:
            return fail(probe.error)
        if not probe.result:
            return fail("TeamTalk verification ended without an account result")
        print(json.dumps(probe.result, ensure_ascii=False))
        return 0 if probe.result.get("ok") else 3
    except Exception:
        return fail("Unexpected TeamTalk verification failure")
    finally:
        if probe is not None:
            try:
                probe.doLogout()
            except Exception:
                pass
            try:
                probe.disconnect()
            except Exception:
                pass
            try:
                probe.closeTeamTalk()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
