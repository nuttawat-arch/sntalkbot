# -*- coding: utf-8 -*-
"""Small in-memory activity/audit ring for TeamTalk runtime events.

The tracker is intentionally dependency-free and bounded. It never owns TeamTalk
objects, so it cannot keep stale ctypes structures alive or affect playback.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import threading
import time


class ActivityLog:
    def __init__(self, max_items: int = 200):
        self.max_items = max(20, int(max_items or 200))
        self._items = deque(maxlen=self.max_items)
        self._lock = threading.RLock()
        self.started_at = time.time()

    def record(self, category: str, action: str, message: str, **metadata):
        item = {
            "timestamp": time.time(),
            "category": str(category or "system"),
            "action": str(action or "event"),
            "message": str(message or ""),
            "metadata": {k: v for k, v in metadata.items() if v is not None},
        }
        with self._lock:
            self._items.append(item)
        return item

    def recent(self, limit: int = 10, category: str | None = None):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 25))
        category = str(category).strip().lower() if category else None
        with self._lock:
            items = list(self._items)
        if category:
            items = [item for item in items if item.get("category", "").lower() == category]
        return items[-limit:]

    def clear(self):
        with self._lock:
            self._items.clear()

    @staticmethod
    def format_age(timestamp: float, now: float | None = None):
        now = time.time() if now is None else float(now)
        age = max(0, int(now - float(timestamp or now)))
        if age < 60:
            return f"{age}s"
        if age < 3600:
            return f"{age // 60}m"
        if age < 86400:
            return f"{age // 3600}h"
        return f"{age // 86400}d"

    @staticmethod
    def iso_time(timestamp: float):
        return datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat()
