from __future__ import annotations

import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class LocalStatusApi:
    """Loopback-only, read-only realtime status API for a helper-managed bot.

    The API is disabled unless both SNTALKBOT_API_PORT and SNTALKBOT_API_TOKEN
    are supplied. TTUHelper allocates a unique high port per instance and keeps
    the token in local instance metadata. No management action is exposed here;
    lifecycle/configuration still goes through TTUHelper/Web Manager allowlists.
    """

    def __init__(self, bot):
        self.bot = bot
        self.bind = os.getenv("SNTALKBOT_API_BIND", "127.0.0.1").strip() or "127.0.0.1"
        try:
            self.port = int(os.getenv("SNTALKBOT_API_PORT", "0") or 0)
        except ValueError:
            self.port = 0
        self.token = os.getenv("SNTALKBOT_API_TOKEN", "").strip()
        self.server = None
        self.thread = None

    @property
    def enabled(self):
        return bool(self.port and self.token)

    def start(self):
        if not self.enabled or self.server is not None:
            return False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "SNTalkBotLocalAPI/1"
            sys_version = ""

            def log_message(self, fmt, *args):
                return

            def _authorized(self):
                expected = f"Bearer {outer.token}"
                supplied = self.headers.get("Authorization", "")
                return hmac.compare_digest(supplied, expected)

            def _json(self, status, payload):
                data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if not self._authorized():
                    self._json(401, {"ok": False, "error": "unauthorized"})
                    return
                if self.path == "/healthz":
                    self._json(200, {"ok": True})
                    return
                if self.path == "/v1/status":
                    try:
                        writer = getattr(outer.bot, "runtime_state_writer", None)
                        payload = writer.build_snapshot() if writer is not None else {"connected": False}
                        payload["api"] = {"schema": 1, "realtime": True}
                        self._json(200, payload)
                    except Exception as exc:
                        logging.exception("Local status API snapshot failed")
                        self._json(500, {"ok": False, "error": type(exc).__name__})
                    return
                self._json(404, {"ok": False, "error": "not_found"})

        try:
            self.server = _QuietServer((self.bind, self.port), Handler)
        except Exception:
            logging.exception("Unable to start local status API on %s:%s", self.bind, self.port)
            self.server = None
            return False
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="SNTalkBotLocalAPI",
            daemon=True,
        )
        self.thread.start()
        logging.info("Local status API listening on %s:%s (read-only, token protected)", self.bind, self.port)
        return True

    def stop(self):
        server = self.server
        self.server = None
        if server is None:
            return
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        thread = self.thread
        self.thread = None
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
