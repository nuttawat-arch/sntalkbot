from __future__ import annotations

import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.parse import parse_qs, urlparse


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class LocalStatusApi:
    """Loopback-only realtime/status API for a helper-managed bot.

    Reads are live snapshots from memory/SQLite. Write-like actions are limited
    to narrowly scoped local events: verified GitHub releases and central Global
    Broadcast delivery for enabled Manager/Full bots. Lifecycle/config/delete
    operations remain behind TTUHelper/Web Manager privileged allowlists.
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
            server_version = "SNTalkBotLocalAPI/2"
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

            def _body_json(self, max_bytes=65536):
                try:
                    length = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError:
                    length = 0
                if length <= 0 or length > max_bytes:
                    return None
                try:
                    return json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:
                    return None

            def do_GET(self):
                if not self._authorized():
                    self._json(401, {"ok": False, "error": "unauthorized"})
                    return
                parsed = urlparse(self.path)
                if parsed.path == "/healthz":
                    self._json(200, {"ok": True})
                    return
                if parsed.path == "/v1/status":
                    try:
                        builder = getattr(outer.bot, "runtime_snapshot_builder", None)
                        payload = builder.build_snapshot() if builder is not None else {"connected": False}
                        payload["api"] = {"schema": 2, "realtime": True, "transport": "memory+sqlite"}
                        self._json(200, payload)
                    except Exception as exc:
                        logging.exception("Local status API snapshot failed")
                        self._json(500, {"ok": False, "error": type(exc).__name__})
                    return
                if parsed.path == "/v1/queue-export":
                    # No total queue ceiling. Pagination keeps each HTTP response
                    # bounded while allowing TTUHelper to preserve arbitrarily large
                    # queues before replacing a container.
                    try:
                        query = parse_qs(parsed.query)
                        cursor_raw = (query.get("cursor") or [""])[0]
                        cursor = int(cursor_raw) if str(cursor_raw).strip() else None
                        limit_raw = (query.get("limit") or ["1000"])[0]
                        limit = max(1, min(int(limit_raw), 5000))
                        store = outer.bot.state_store
                        items, last_seq = store.queue_page(after_seq=cursor, limit=limit)
                        total = store.queue_count()
                        next_cursor = last_seq if items and len(items) == limit else None
                        self._json(200, {
                            "ok": True,
                            "queue_count": total,
                            "queue_index": int(getattr(getattr(outer.bot, "player", None), "queue_index", -1) or -1),
                            "items": items,
                            "next_cursor": next_cursor,
                            "complete": next_cursor is None,
                        })
                    except Exception as exc:
                        logging.exception("Queue export failed")
                        self._json(500, {"ok": False, "error": type(exc).__name__})
                    return
                self._json(404, {"ok": False, "error": "not_found"})

            def do_POST(self):
                if not self._authorized():
                    self._json(401, {"ok": False, "error": "unauthorized"})
                    return
                parsed = urlparse(self.path)
                payload = self._body_json()
                if not isinstance(payload, dict):
                    self._json(400, {"ok": False, "error": "invalid_json"})
                    return
                if parsed.path == "/v1/events/release":
                    notifier = getattr(outer.bot, "update_notifier", None)
                    if notifier is None:
                        self._json(503, {"ok": False, "error": "notifier_disabled"})
                        return
                    try:
                        accepted = bool(notifier.handle_release_event(payload))
                        self._json(202 if accepted else 200, {"ok": True, "accepted": accepted})
                    except Exception as exc:
                        logging.exception("Release event handling failed")
                        self._json(500, {"ok": False, "error": type(exc).__name__})
                    return
                if parsed.path == "/v1/events/global-broadcast":
                    if not bool(getattr(outer.bot, "server_management_enabled", False)):
                        self._json(403, {"ok": False, "error": "manager_feature_disabled"})
                        return
                    cfg = dict(getattr(outer.bot, "global_broadcast_config", {}) or {})
                    if not bool(cfg.get("enabled", False)):
                        self._json(409, {"ok": False, "error": "global_broadcast_disabled"})
                        return
                    message = str(payload.get("message") or "").strip()
                    if not message or len(message.encode("utf-8")) > 12000:
                        self._json(400, {"ok": False, "error": "invalid_message"})
                        return
                    try:
                        outer.bot.send_broadcast_message(message)
                        tts_queued = bool(outer.bot.queue_global_broadcast_tts(message))
                        self._json(202, {"ok": True, "accepted": True, "tts_queued": tts_queued})
                    except Exception as exc:
                        logging.exception("Central global broadcast failed")
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
        logging.info("Local realtime API listening on %s:%s (loopback/token protected)", self.bind, self.port)
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
