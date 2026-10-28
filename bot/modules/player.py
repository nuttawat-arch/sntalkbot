from TeamTalk5 import ttstr
from bot.utils import BotUtils as utils
import os
import yt_dlp
import threading
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# yt-dlp flat-search usually returns a page of metadata at once. Keeping a
# useful first page avoids trapping queue-selection users on a single hit.
INITIAL_SEARCH_RESULTS = 1

class PlayerCog:
    """
    A module for handling all music and media player related commands.
    """
    def __init__(self, bot):
        self.bot = bot
        self.player = bot.player
        self._ = bot._        
        self.download_in_progress = False
        self.loading_new_track = False
        self._deferred_playback_end = False
        # Playback failure state is scoped to one logical item, not one mpv load.
        # This allows exactly one retry for transient errors without carrying the
        # retry budget into the next queue/playlist/radio item.
        self._failure_lock = threading.RLock()
        self._playback_context = None
        self._failure_key = None
        self._failure_count = 0
        self._deletion_stop = threading.Event()
        self._deletion_wakeup = threading.Event()        
        self.autoplay_enabled = bool(self.bot.playback_config.get("autoplay_enabled", self.player.play_mode == 2))
        self.pending_channel_tabs = {}
        self.pending_playlist_tabs = {}
        self.pending_playlist_searches = {}
        self.pending_playlist_search_lock = threading.Lock()
        self.pending_channel_timeout = 60
        # Playback handoffs must not wait behind downloads, searches or other
        # long-running tasks in the general I/O executor. One ordered worker
        # preserves FIFO and keeps native libmpv callbacks lightweight.
        self._playback_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="TTBot_Playback")
        # Related Radio discovery is warmed independently from the ordered
        # playback worker. The current track may play for minutes, which is the
        # ideal time to resolve recommendations and prefetch the next stream.
        self._radio_warm_lock = threading.RLock()
        self._radio_warm_seed = None
        self._radio_warm_event = threading.Event()
        self._radio_warm_event.set()
        self.player.end_callback = self._schedule_playback_end
        data_dir = os.getenv("TTUTIL_DATA_DIR", ".")
        os.makedirs(data_dir, exist_ok=True)
        self.favorites_file = os.path.join(data_dir, "favorites.json")
        self.favorites = self.load_favorites()
        self._deletion_worker = threading.Thread(
            target=self._deletion_worker_loop, daemon=True, name="SNTalkBot_FileDeletion"
        )
        self._deletion_worker.start()

    def _log_action(self, action, **metadata):
        logger = getattr(self.bot, "log_runtime_action", None)
        if callable(logger):
            logger(action, **metadata)

    def load_favorites(self):
        store = getattr(self.bot, "state_store", None)
        if store is None:
            return []
        current = store.load_favorites()
        # One-time import from pre-SQLite releases. Successful import removes the
        # mutable JSON source so there is one canonical store afterwards.
        if not current and os.path.exists(self.favorites_file):
            try:
                with open(self.favorites_file, 'r', encoding='utf-8') as handle:
                    legacy = json.load(handle)
                if isinstance(legacy, list):
                    store.save_favorites(legacy)
                    current = store.load_favorites()
                    os.remove(self.favorites_file)
            except Exception:
                pass
        return current

    def save_favorites(self):
        try:
            self.bot.state_store.save_favorites(self.favorites)
        except Exception as exc:
            print(f"Error saving favorites: {exc}")

    def shutdown(self):
        self._cancel_pending_retry()
        playback_pool = getattr(self, "_playback_pool", None)
        if playback_pool is not None:
            playback_pool.shutdown(wait=False, cancel_futures=True)
        self._deletion_stop.set()
        self._deletion_wakeup.set()
        worker = getattr(self, "_deletion_worker", None)
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=1.0)

    def _deletion_worker_loop(self):
        store = self.bot.state_store
        while not self._deletion_stop.is_set():
            now = time.time()
            for row in store.due_deletions(now=now, limit=100):
                if self._delete_scheduled_row(row):
                    store.delete_deletion(row["id"])
                else:
                    # TeamTalk may be reconnecting or the filesystem may be
                    # temporarily unavailable. Keep the persistent job and retry
                    # instead of turning a transient failure into leaked files.
                    store.reschedule_deletion(row["id"], time.time() + 30.0)
            next_at = store.next_deletion_time()
            if next_at is None:
                timeout = 60.0
            else:
                timeout = max(0.05, min(60.0, next_at - time.time()))
            self._deletion_wakeup.wait(timeout)
            self._deletion_wakeup.clear()

    def _delete_scheduled_row(self, row):
        filename = str(row.get("local_path") or "")
        channel_id = int(row.get("channel_id") or 0)
        remote_name = str(row.get("remote_name") or os.path.basename(filename))
        remote_ok = True
        local_ok = True
        try:
            if channel_id and remote_name:
                file_id = self.get_file_id_by_name(channel_id, remote_name)
                if file_id:
                    result = self.bot.doDeleteFile(channel_id, file_id)
                    remote_ok = result != -1
        except Exception as exc:
            remote_ok = False
            print(self._("Error deleting remote file: {e}").format(e=str(exc)))
        try:
            if filename and os.path.exists(filename):
                os.remove(filename)
        except OSError as exc:
            local_ok = False
            print(self._("Error deleting file: {e}").format(e=str(exc)))
        return remote_ok and local_ok

    # ---------------- Queue state machine ----------------
    def _submit_playback(self, callback, *args):
        pool = getattr(self, "_playback_pool", None) or self.bot.io_pool
        future = pool.submit(callback, *args)
        def _report(done):
            try:
                exc = done.exception()
            except Exception:
                return
            if exc is not None:
                self._trace("playback_worker_error", callback=getattr(callback, "__name__", "callback"), error=repr(exc))
                print(f"Playback worker error in {getattr(callback, '__name__', 'callback')}: {exc!r}")
        if future is not None and hasattr(future, "add_done_callback"):
            future.add_done_callback(_report)
        return future

    def _trace(self, event, **fields):
        tracer = getattr(self.player, "trace_playback", None)
        if callable(tracer):
            fields.setdefault("loading", bool(getattr(self, "loading_new_track", False)))
            fields.setdefault("queue_transition", bool(getattr(self.player, "queue_transition", False)))
            fields.setdefault("playback_end_transition", bool(getattr(self.player, "playback_end_transition", False)))
            return tracer(event, **fields)
        return None

    def _queue_owns_current_playback(self):
        context = getattr(self, "_playback_context", None) or {}
        return str(context.get("kind") or "") == "queue"

    def _schedule_playback_end(self):
        # Called from libmpv/watchdog threads; never do SQL or media extraction
        # on an MPV callback thread.
        self._submit_playback(self.on_playback_end)

    def _stop_transport_for_replacement(self):
        """Stop only when media is actually active.

        A natural EOF is already idle. Calling stop again there closes/restarts
        the audio path and defeats MPV's gapless handoff. Manual next/select
        still stops the active item exactly as before.
        """
        try:
            active = bool(self.player.transport_is_active())
        except Exception:
            active = bool(getattr(self.player, "is_playing", False) or getattr(self.player, "pause", False))
        if active:
            self.player.stop_transport()
        return active

    # Do not use mpv's is_playing flag alone to decide whether a newly-added
    # item should start. mpv flips it to False before playback-end callbacks,
    # which used to let a last-second enqueue jump ahead of older pending items.
    def _enqueue_queue_items(self, items, *, user_id=None, nickname=None):
        """Append items atomically and return (start, end, should_start).

        Every queued item keeps lightweight audit metadata (`added_by`,
        `added_by_user_id`, `added_at`) so ql can tell users who added what and
        when without changing FIFO semantics. Returning the range lets channel
        text and Player TTS announce exact positions without re-reading a queue
        that may already have changed on a worker thread.
        """
        queued_by = (nickname or (self._nickname(user_id) if user_id else None) or self._("Unknown")).strip()
        queued_at = int(time.time())
        normalized = []
        for item in (items or []):
            if not item or not item.get("link"):
                continue
            entry = dict(item)
            entry["added_by"] = queued_by
            if user_id is not None:
                entry["added_by_user_id"] = int(user_id)
            entry["added_at"] = queued_at
            entry.setdefault("_queue_token", f"{queued_at}-{time.time_ns()}-{len(normalized)}")
            normalized.append(entry)
        items = normalized
        if not items:
            return None
        with self.player.queue_lock:
            start_position = len(self.player.queue) + 1
            self.player.queue.extend(items)
            end_position = len(self.player.queue)
            should_start = (
                self.player.queue_mode
                and self.player.queue_index < 0
                and not self.player.queue_transition
                and not self.player.playback_end_transition
                and not self.player.is_playing
            )
            if should_start:
                # Reserve item 1 atomically, but do not start it here.  The caller
                # must first enqueue the human-visible/Player-TTS "added to queue"
                # announcement and then call _after_queue_enqueue().  This fixes
                # the first-item ordering bug where "Now playing" was spoken first.
                self.player.queue_index = 0
                self.player.queue_transition = True
        self._trace("queue_enqueue", added=len(items), start=start_position, end=end_position, should_start=should_start)
        return start_position, end_position, should_start

    def _finish_loading_transition(self):
        """Finish a track-load transition and replay any terminal event that arrived during it."""
        self.loading_new_track = False
        if getattr(self, "_deferred_playback_end", False):
            self._deferred_playback_end = False
            self._submit_playback(self.on_playback_end)

    def _ensure_failure_state(self):
        """Lazily initialize retry state for normal runtime and validator fixtures."""
        lock = getattr(self, "_failure_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._failure_lock = lock
        if not hasattr(self, "_failure_key"):
            self._failure_key = None
        if not hasattr(self, "_failure_count"):
            self._failure_count = 0
        if not hasattr(self, "_playback_context"):
            self._playback_context = None
        if not hasattr(self, "_retry_pending"):
            self._retry_pending = None
        return lock

    def _set_playback_context(self, kind, link, token=None):
        key = (str(kind or "normal"), str(token or ""), str(link or ""))
        with self._ensure_failure_state():
            if key != self._failure_key:
                if self._retry_pending:
                    self._retry_pending["cancel"].set()
                    self._retry_pending = None
                self._failure_key = key
                self._failure_count = 0
            self._terminal_cancelled = False
            self._playback_context = {
                "kind": key[0], "token": key[1], "link": key[2], "key": key,
            }
        return key

    def _reset_failure_budget(self):
        with self._ensure_failure_state():
            self._failure_count = 0

    def _claim_one_retry(self):
        with self._ensure_failure_state():
            context = dict(self._playback_context or {})
            if not context or not context.get("link"):
                return None
            if self._retry_pending:
                return None
            cfg = getattr(self.bot, "playback_config", {})
            maximum = max(1, min(5, int(cfg.get("playback_retry_attempts", 3))))
            if self._failure_count >= maximum:
                return None
            self._failure_count += 1
            context["attempt"] = self._failure_count
            context["cancel"] = threading.Event()
            self._retry_pending = context
            return context

    def _cancel_pending_retry(self, invalidate=False):
        with self._ensure_failure_state():
            pending = self._retry_pending
            if pending:
                pending["cancel"].set()
                self._retry_pending = None
            if pending or invalidate:
                self._terminal_cancelled = True
                self._playback_context = None
                self._failure_key = None
            self._deferred_playback_end = False
            return bool(pending)

    def _queue_token(self, index):
        with self.player.queue_lock:
            if index < 0 or index >= len(self.player.queue):
                return ""
            entry = self.player.queue[index]
            token = str(entry.get("_queue_token") or "")
            if not token:
                token = f"legacy-{time.time_ns()}"
                entry["_queue_token"] = token
                self.player.queue[index] = entry
            return token

    def _mark_sync_play_error(self, exc):
        """Convert a synchronous play_stream exception into the normal end path."""
        self._deferred_playback_end = False
        self._sync_error_serial = int(getattr(self, "_sync_error_serial", 0)) + 1
        self.player.is_playing = False
        self.player.last_end_reason = "error"
        self.player.last_error_category = getattr(exc, "category", None)
        try:
            code = int(getattr(exc, "errno", 0) or -1)
        except Exception:
            code = -1
        self.player.last_end_error = code

    def _retry_current_playback_once(self):
        if getattr(self.player, "last_error_category", None) == "age_auth":
            return False  # Keep in failed history; account access must be fixed first.
        context = self._claim_one_retry()
        if not context:
            return False
        # MPV -13 in the live logs means the CDN URL failed immediately after
        # START_FILE. Waiting the generic retry delay only adds dead air, so
        # retry this specific transport failure immediately with a fresh
        # public-fast/stable yt-dlp stream.
        context["immediate"] = int(getattr(self.player, "last_end_error", 0) or 0) == -13
        title = self.player.media_title or context.get("link") or self._("Unknown")
        self._send_playback_message(
            self._("Playback error for {title}. Retrying the same item with a fresh stream URL...").format(title=title)
            + f" ({context['attempt']}/{max(1, min(5, int(self.bot.playback_config.get('playback_retry_attempts', 3))))})"
        )
        self.bot.io_pool.submit(self._retry_playback_context_task, context)
        return True

    def _retry_playback_context_task(self, context):
        link = str(context.get("link") or "")
        if not link:
            return
        cancel = context["cancel"]
        delay = max(0.0, min(30.0, float(self.bot.playback_config.get("playback_retry_delay", 2.0))))
        if context.get("immediate"):
            delay = 0.0
        if cancel.wait(min(30.0, delay * context["attempt"])):
            return
        # The delay may run on the general IO pool, but the actual MPV
        # stop/play sequence must join the same ordered executor as EOF and
        # manual next. Concurrent retries used to stop a newly selected song.
        self._submit_playback(self._perform_retry_playback_context, context)

    def _perform_retry_playback_context(self, context):
        link = str(context.get("link") or "")
        cancel = context["cancel"]
        with self._ensure_failure_state():
            if self._retry_pending is not context or self._failure_key != context["key"]:
                return
            if context.get("kind") == "queue":
                with self.player.queue_lock:
                    index = self.player.queue_index
                    if index < 0 or index >= len(self.player.queue):
                        self._retry_pending = None
                        return
                    item = self.player.queue[index]
                    if item.get("link") != link or str(item.get("_queue_token") or "") != str(context.get("token") or ""):
                        self._retry_pending = None
                        return
        self.loading_new_track = True
        error = None
        try:
            self.player.stop_transport()
            self.player.current_link = link
            self.bot.enableVoiceTransmission(True)
            # A cached CDN URL is never reused for retry. Re-resolve with the
            # current cookie snapshot using the existing extractor path.
            if hasattr(self.player, "invalidate_stream_info"):
                self.player.invalidate_stream_info(link)
            self.player.play_stream(link, cancel_event=cancel, stable_only=True)
            if cancel.is_set():
                return
            self.bot.doChangeStatus(
                ttstr(self.bot.bot_config['gender']),
                ttstr(self._("Playing: {title}").format(title=self.player.media_title)),
            )
            self._prefetch_next_for_current()
        except Exception as exc:
            error = exc
            self._mark_sync_play_error(exc)
        finally:
            with self._ensure_failure_state():
                if self._retry_pending is context:
                    self._retry_pending = None
            if cancel.is_set():
                # A manual skip can cancel a retry after it has begun. Leaving
                # loading_new_track=True here silently discards every future
                # end-of-song callback (and leaves the queue stuck).
                self._deferred_playback_end = False
                self.loading_new_track = False
            else:
                self._finish_loading_transition()
        if error is not None and not cancel.is_set():
            self._submit_playback(self.on_playback_end)

    def _teamtalk_voice_tx_active(self):
        """Read our actual TeamTalk voice state when SDK state is available."""
        try:
            user = self.bot.getUser(self.bot.getMyUserID())
            if not user:
                return False
            flag = int(self.bot._state_flag("USERSTATE_VOICE") or 0)
            state = int(getattr(user, "uUserState", 0) or 0)
            return bool(flag and state & flag)
        except Exception:
            return False

    def _transport_or_voice_active(self):
        try:
            transport = bool(self.player.transport_is_active())
        except Exception:
            transport = bool(self.player.is_playing or getattr(self.player, "pause", False))
        return transport or self._teamtalk_voice_tx_active()

    def _after_queue_enqueue(self, should_start):
        """Start a newly-reserved first queue item only after its queue announcement.

        If playback is already active, schedule/preload the oldest pending queue
        items immediately so the end-of-track handoff does not wait on metadata.
        """
        self._trace("queue_after_enqueue", should_start=bool(should_start))
        if should_start:
            self._submit_playback(self._play_from_queue, 0)
        else:
            self._prefetch_next_for_current()

    def _advance_queue_after_current(self, *, remember=True):
        """Consume only the current queue item and continue with the oldest pending item."""
        self._trace("queue_advance_begin", remember=bool(remember), end_reason=getattr(self.player, "last_end_reason", None))
        next_index = None
        with self.player.queue_lock:
            if self.player.queue_index >= 0 and self.player.queue:
                idx = min(self.player.queue_index, len(self.player.queue) - 1)
                store = getattr(self.bot, "state_store", None)
                if not remember and getattr(self.player, "last_end_reason", None) == "error" and store is not None:
                    finished = store.archive_failed_queue_item(
                        idx, f"{getattr(self.player, 'last_error_category', None) or 'playback'}: {getattr(self.player, 'last_end_error', -1)}",
                        1 + int(getattr(self, "_failure_count", 0)),
                    )
                else:
                    finished = self.player.queue.pop(idx)
                if remember:
                    self.player.queue_history.append(dict(finished))
                    if len(self.player.queue_history) > 64:
                        del self.player.queue_history[:-64]
                self.player.queue_index = -1
            if self.player.queue_mode and self.player.queue:
                next_index = 0
                self.player.queue_index = 0
                self.player.queue_transition = True
            else:
                self.player.queue_transition = False
        if next_index is not None:
            self._trace("queue_advance_schedule", next_index=next_index)
            self._submit_playback(self._play_from_queue, next_index)
            return True
        self._trace("queue_advance_empty")
        return False

    def _play_next_queue_manual(self, user_id=None):
        self._trace("queue_manual_next")
        with self.player.queue_lock:
            has_current = self.player.queue_index >= 0 and bool(self.player.queue)
            has_pending = bool(self.player.queue)
        if has_current:
            if self._advance_queue_after_current(remember=True):
                return
            self.loading_new_track = True
            try:
                self.player.stop_transport()
                self.player.current_link = None
                self.bot.enableVoiceTransmission(False)
            finally:
                self._finish_loading_transition()
            if user_id:
                self.bot.privateMessage(user_id, self._("You've reached the end of the list."))
            return
        if has_pending:
            with self.player.queue_lock:
                self.player.queue_index = 0
                self.player.queue_transition = True
            self._play_from_queue(0)
            return
        if user_id:
            self.bot.privateMessage(user_id, self._("The queue is empty."))

    def _play_previous_queue_manual(self, user_id=None):
        with self.player.queue_lock:
            if not self.player.queue_history:
                previous = None
            else:
                previous = self.player.queue_history.pop()
                # Preserve the current/pending queue exactly; replaying a previous
                # item inserts it temporarily at the front instead of deleting or
                # reordering anything that has not yet played.
                self.player.queue.insert(0, dict(previous))
                self.player.queue_index = 0
                self.player.queue_transition = True
        if previous is None:
            if user_id:
                self.bot.privateMessage(user_id, self._("You are at the beginning of the list."))
            return
        self._play_from_queue(0)

    # ---------------- Normal discovery/radio navigation ----------------
    def _normal_discovery_available(self):
        return not self.player.queue_mode and not self.player.collection_results

    def _current_radio_seed(self):
        if self.player.radio_history and 0 <= self.player.radio_index < len(self.player.radio_history):
            seed = dict(self.player.radio_history[self.player.radio_index])
            if seed.get("link"):
                return seed
        if self.player.current_link:
            return {
                "title": self.player.media_title or "Unknown title",
                "link": self.player.current_link,
                "source": self.player.radio_source or "youtube",
            }
        return None

    def _schedule_related_radio_warm(self):
        """Discover and prefetch the next Related Radio item while music is playing."""
        if self.player.queue_mode:
            return False
        if not (self.player.play_mode == 2 or self.autoplay_enabled):
            return False
        seed = self._current_radio_seed()
        if not seed or not seed.get("link"):
            return False
        seed_link = str(seed["link"])

        # If candidates already exist, prefetch the exact item autoplay will use.
        if self.player.radio_candidates:
            next_link = str(self.player.radio_candidates[0].get("link") or "")
            if next_link:
                self._trace("radio_prefetch_schedule", link=next_link, source="existing_candidates")
                self.player.prefetcher.schedule([next_link])
                return True

        with self._radio_warm_lock:
            if self._radio_warm_seed == seed_link and not self._radio_warm_event.is_set():
                return True
            self._radio_warm_seed = seed_link
            self._radio_warm_event.clear()
        self._trace("radio_warm_schedule", link=seed_link)
        self.bot.io_pool.submit(self._warm_related_radio_task, seed)
        return True

    def _warm_related_radio_task(self, seed):
        seed_link = str(seed.get("link") or "")
        candidates = []
        try:
            candidates = self.player.related_radio(seed, seed.get("source") or self.player.radio_source, limit=30)
            used = {str(item.get("link") or "") for item in self.player.radio_history}
            candidates = [
                dict(item) for item in candidates
                if item.get("link") and str(item.get("link") or "") not in used
            ]
            current = self._current_radio_seed()
            if (self.player.queue_mode or not current
                    or str(current.get("link") or "") != seed_link):
                self._trace("radio_warm_discard", link=seed_link, reason="seed_changed")
                return
            # Do not overwrite a newer synchronous discovery result.
            if not self.player.radio_candidates:
                self.player.radio_candidates = candidates
            if self.player.radio_candidates:
                next_link = str(self.player.radio_candidates[0].get("link") or "")
                if next_link:
                    self.player.prefetcher.schedule([next_link])
                    self._trace("radio_prefetch_schedule", link=next_link, source="warm_complete")
            self._trace("radio_warm_done", link=seed_link, count=len(self.player.radio_candidates))
        except Exception as exc:
            self._trace("radio_warm_error", link=seed_link, error=type(exc).__name__)
            print(f"Related Radio warmup failed: {type(exc).__name__}: {exc}")
        finally:
            with self._radio_warm_lock:
                if self._radio_warm_seed == seed_link:
                    self._radio_warm_event.set()

    def _wait_for_radio_warm(self, seed_link, timeout=0.35):
        with self._radio_warm_lock:
            same = self._radio_warm_seed == str(seed_link or "")
            event = self._radio_warm_event
        if same and not event.is_set():
            event.wait(max(0.0, min(1.0, float(timeout))))

    def _play_radio_item(self, item, user_id=None, announce_private=False, autoplay=False):
        if not item or not item.get("link"):
            return False
        # Related Radio is a separate normal-mode history. Once it begins, an
        # exhausted or manually-abandoned playlist must not resume behind it.
        self.player.clear_collection()
        self.loading_new_track = True
        play_error = None
        try:
            self._stop_transport_for_replacement()
            self.player.current_link = item["link"]
            self._set_playback_context("radio", item["link"], self.player.radio_index)
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(item["link"])
            # radio_candidates is the list autoplay will actually consume.
            # Prefetch from it immediately instead of warming unrelated search
            # results that "."/"," navigation uses.
            self._prefetch_next_for_current()
            if announce_private and user_id:
                self.bot.privateMessage(user_id, self._("Playing: {title}").format(title=item.get("title", self.player.media_title)))
            elif autoplay:
                self._send_playback_message(self._("Autoplaying related track: {title}").format(title=item.get("title", self.player.media_title)))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
        except Exception as exc:
            play_error = exc
            self._send_playback_message(self._("Error playing {title}: {e}").format(title=item.get('title', 'Unknown'), e=str(exc)))
            self._mark_sync_play_error(exc)
        finally:
            self._finish_loading_transition()
        if play_error is not None:
            self._submit_playback(self.on_playback_end)
        return True

    def _ensure_radio_seed(self):
        if self.player.radio_history and 0 <= self.player.radio_index < len(self.player.radio_history):
            return True
        if not self.player.current_link:
            return False
        source = "ytmusic" if "music.youtube.com" in str(self.player.current_link) else "youtube"
        self.player.reset_radio_history({
            "title": self.player.media_title or "Unknown title",
            "link": self.player.current_link,
            "source": source,
        }, source)
        return True

    def _play_next_related(self, user_id=None, announce_private=False, autoplay=False):
        if not self._ensure_radio_seed():
            if user_id:
                self.bot.privateMessage(user_id, self._("No related track is available."))
            return False

        # If the user previously moved backward with b, n first walks forward
        # through already-played radio history without asking YouTube again.
        if self.player.radio_index < len(self.player.radio_history) - 1:
            self.player.radio_index += 1
            return self._play_radio_item(
                self.player.radio_history[self.player.radio_index],
                user_id=user_id, announce_private=announce_private, autoplay=autoplay,
            )

        current = self.player.radio_history[self.player.radio_index]
        used = {str(item.get("link") or "") for item in self.player.radio_history}
        while self.player.radio_candidates and str(self.player.radio_candidates[0].get("link") or "") in used:
            self.player.radio_candidates.pop(0)
        if not self.player.radio_candidates:
            self._wait_for_radio_warm(current.get("link"), timeout=0.35)
        if not self.player.radio_candidates:
            self.player.radio_candidates = self.player.related_radio(current, self.player.radio_source, limit=30)
            self.player.radio_candidates = [
                item for item in self.player.radio_candidates
                if str(item.get("link") or "") not in used
            ]
        if not self.player.radio_candidates:
            if user_id:
                self.bot.privateMessage(user_id, self._("No related track is available."))
            return False

        next_item = self.player.radio_candidates.pop(0)
        self.player.radio_history.append(dict(next_item))
        self.player.radio_index = len(self.player.radio_history) - 1
        if self._play_radio_item(next_item, user_id=user_id, announce_private=announce_private, autoplay=autoplay):
            return True
        # A broken recommendation should not poison navigation history.
        self.player.radio_history.pop()
        self.player.radio_index = len(self.player.radio_history) - 1
        return self._play_next_related(user_id=user_id, announce_private=announce_private, autoplay=autoplay) if self.player.radio_candidates else False

    def _autoplay_related_or_finish(self):
        """A finished radio track must not leave voice enabled if discovery ends."""
        try:
            if self._play_next_related(None, False, True):
                return
        except Exception as exc:
            print(f"Autoplay continuation failed: {type(exc).__name__}: {exc}")
        self._finish_natural_playback()

    def _finish_natural_playback(self):
        """Release the TeamTalk microphone and clear stale now-playing state."""
        self.player.is_playing = False
        self.player.pause = False
        self.player.current_link = None
        self.player.media_title = ""
        try:
            self.bot.enableVoiceTransmission(False)
        except Exception as exc:
            print(f"Unable to disable TeamTalk voice after playback: {type(exc).__name__}: {exc}")
        try:
            self.bot.doChangeStatus(
                ttstr(self.bot.bot_config['gender']),
                ttstr(self.bot.get_idle_status_message()),
            )
        except Exception as exc:
            print(f"Unable to set TeamTalk idle status: {type(exc).__name__}: {exc}")

    def _play_previous_related(self, user_id=None, announce_private=False):
        if not self._ensure_radio_seed() or self.player.radio_index <= 0:
            if user_id:
                self.bot.privateMessage(user_id, self._("No previous related track."))
            return False
        self.player.radio_index -= 1
        return self._play_radio_item(
            self.player.radio_history[self.player.radio_index],
            user_id=user_id, announce_private=announce_private, autoplay=False,
        )

    def register(self, command_handler):
        """Registers all the player commands with the command handler."""
        command_handler.register_command('u', self.handle_play_url_command)
        command_handler.register_command('pp', self.handle_append_playlist_command)
        command_handler.register_command('pps', self.handle_playlist_search_selection_command)
        command_handler.register_command('p', self.handle_play_search_or_pause_command)
        command_handler.register_command('pm', self.handle_ytmusic_search_command)
        command_handler.register_command('n', self.handle_next_track_command)
        command_handler.register_command('b', self.handle_previous_track_command)
        command_handler.register_command('v', self.handle_change_volume_command)
        command_handler.register_command('l', self.handle_get_current_link_command) # ขอลิ้งค์เพลงที่กำลังเล่น
        command_handler.register_command('pg', self.handle_playing_info_command) # ดูข้อมูลเพลงที่กำลังเล่นอยู่
        command_handler.register_command('d', self.handle_get_duration_command) # Alias for pg or specific duration info
        command_handler.register_command('r', self.handle_history_command)
        command_handler.register_command('dl', self.handle_download_command)
        command_handler.register_command('s', self.handle_stop_command)
        command_handler.register_command('x', self.handle_pause_resume_command)
        command_handler.register_command('t', self.handle_seek_to_time_command)
        command_handler.register_command('autoplay', self.handle_autoplay_command)
        command_handler.register_command('channel', self.handle_channel_command)
        command_handler.register_command('q', self.handle_queue_toggle_command)
        command_handler.register_command('ql', self.handle_queue_list_command)
        command_handler.register_command('qc', self.handle_queue_check_command)
        command_handler.register_command('dq', self.handle_delete_queue_command)
        command_handler.register_command('cq', self.handle_clear_queue_command)
        command_handler.register_command('.', self.handle_next_search_result_selection)
        command_handler.register_command(',', self.handle_prev_search_result_selection)
        command_handler.register_command('+', self.handle_seek_forward_command)
        command_handler.register_command('-', self.handle_seek_back_command)
        command_handler.register_command('fav', self.handle_fav_command)
        command_handler.register_command('playfav', self.handle_playfav_command)
        command_handler.register_command('delfav', self.handle_delfav_command)
        command_handler.register_command('3d', self.handle_3d_command)
        command_handler.register_command('3d2', self.handle_3d2_command)
        command_handler.register_command('bass', self.handle_bass_command)
        command_handler.register_command('sp', self.handle_speed_command)
        command_handler.register_command('f', self.handle_fade_command)
        command_handler.register_command('m', self.handle_mode_command)
        command_handler.register_command('m1', self.handle_mode1_command)
        command_handler.register_command('m2', self.handle_mode2_command)
        command_handler.register_command('m3', self.handle_mode3_command)
        command_handler.register_command('hide', self.handle_hide_command)
        command_handler.register_command('select', self.handle_select_command)
        command_handler.register_command('favorites', self.handle_favorites_list_command)
        command_handler.register_command('shuffle', self.handle_shuffle_command)
        command_handler.register_command('ptts', self.handle_player_tts_command, admin_only=True)
        command_handler.register_command('pttsmode', self.handle_player_tts_mode_command, admin_only=True)
        command_handler.register_command('pvoice', self.handle_player_voice_command, admin_only=True)
        command_handler.register_command('pvoices', self.handle_player_voices_command)
        command_handler.register_command('pttsrate', self.handle_player_tts_rate_command, admin_only=True)
        command_handler.register_command('pttsspeed', self.handle_player_tts_speed_command, admin_only=True)
        command_handler.register_command('cc', self.handle_clear_cache_command, admin_only=True)
        command_handler.register_command('csize', self.handle_cache_size_command, admin_only=True)
        command_handler.register_command('cm', self.handle_channel_messages_command, admin_only=True)

    def handle_channel_messages_command(self, textmessage, *args):
        """Control playback announcements sent to the TeamTalk channel.

        No argument preserves the legacy toggle behavior. Explicit on/off/status
        is easier for screen-reader users and automation.
        """
        current = bool(self.bot.playback_config.get("send_channel_messages", True))
        if not args:
            enabled = not current
        else:
            value = str(args[0]).strip().lower()
            if value == "status":
                state = self._("enabled") if current else self._("disabled")
                self.bot.privateMessage(
                    textmessage.nFromUserID,
                    self._("Playback channel messages are now {state}.").format(state=state),
                )
                return
            if value not in ("on", "off"):
                self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: cm on|off|status"))
                return
            enabled = value == "on"

        self.bot.playback_config["send_channel_messages"] = enabled
        self.bot.config_handler.update_playback_settings({"send_channel_messages": enabled})
        state = self._("enabled") if enabled else self._("disabled")
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Playback channel messages are now {state}.").format(state=state),
        )

    def handle_clear_cache_command(self, textmessage, *args):
        prefetched, temporary = self.player.clear_cache()
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Cache cleared. Prefetched entries: {prefetched}; temporary files: {temporary}.").format(
                prefetched=prefetched, temporary=temporary
            ),
        )

    def handle_cache_size_command(self, textmessage, *args):
        size_mb = self.player.cache_size_bytes() / (1024 * 1024)
        self.bot.privateMessage(
            textmessage.nFromUserID,
            self._("Cache size: {size:.2f} MB").format(size=size_mb),
        )

    def handle_player_tts_command(self, textmessage, *args):
        """Control Player track/queue speech independently from Manager chat TTS."""
        user_id = textmessage.nFromUserID
        playback = self.bot.playback_config
        if not args or args[0].lower() == "status":
            tracks = "ON" if playback.get("announce_tracks", True) else "OFF"
            queue_state = "ON" if playback.get("announce_queue", True) else "OFF"
            mode = self.bot.tts_cog.get_player_tts_mode()
            self.bot.privateMessage(user_id, self._("Player TTS: tracks={tracks}, queue={queue}, mode={mode}").format(
                tracks=tracks, queue=queue_state, mode=mode))
            return

        target = "all"
        value_index = 0
        first = args[0].lower()
        if first in ("tracks", "track", "queue"):
            target = "tracks" if first in ("tracks", "track") else "queue"
            value_index = 1
        if len(args) <= value_index or args[value_index].lower() not in ("on", "off"):
            self.bot.privateMessage(user_id, self._("Usage: ptts on|off|status or ptts tracks on|off or ptts queue on|off"))
            return
        enabled = args[value_index].lower() == "on"
        updates = {}
        if target in ("all", "tracks"):
            updates["announce_tracks"] = enabled
            playback["announce_tracks"] = enabled
        if target in ("all", "queue"):
            updates["announce_queue"] = enabled
            playback["announce_queue"] = enabled
        self.bot.config_handler.update_playback_settings(updates)
        state = "ON" if enabled else "OFF"
        self.bot.privateMessage(user_id, self._("Player TTS {target}: {state}").format(target=target, state=state))

    def handle_player_tts_mode_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if not args or args[0].lower() not in ("microsoft", "google"):
            self.bot.privateMessage(user_id, self._("Usage: pttsmode microsoft|google"))
            return
        mode = args[0].lower()
        self.bot.playback_config["announcement_tts_mode"] = mode
        self.bot.config_handler.update_playback_settings({"announcement_tts_mode": mode})
        self.bot.privateMessage(user_id, self._("Player TTS mode set to {mode}.").format(mode=mode))

    def handle_player_voice_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        mode = self.bot.tts_cog.get_player_tts_mode()
        if not args:
            if mode == "google":
                self.bot.privateMessage(user_id, self._("Usage: pvoice <language_code>, for example pvoice th"))
            else:
                self.bot.privateMessage(user_id, self._("Usage: pvoice <voice_name>"))
            return
        value = " ".join(args).strip()
        if mode == "google":
            lang = self.bot.tts_cog._resolve_google_lang(value)
            if not lang:
                self.bot.privateMessage(user_id, self._("Unknown Google standard TTS language: {lang}. Use pvoices to list languages.").format(lang=value))
                return
            key = "announcement_google_lang"
            value = lang
            label = self._("Google standard language")
        else:
            key = "announcement_microsoft_voice"
            label = self._("Microsoft voice")
        self.bot.playback_config[key] = value
        self.bot.config_handler.update_playback_settings({key: value})
        self.bot.privateMessage(user_id, self._("Player {label} set to {value}.").format(label=label, value=value))

    def handle_player_voices_command(self, textmessage, *args):
        lang_code = args[0] if args else None
        self.bot.tts_cog.list_player_voices(textmessage.nFromUserID, lang_code)

    def handle_player_tts_rate_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if self.bot.tts_cog.get_player_tts_mode() != "microsoft":
            self.bot.privateMessage(user_id, self._("Player TTS rate is available in Microsoft mode. For Google use pttsspeed."))
            return
        if not args:
            self.bot.privateMessage(user_id, self._("Usage: pttsrate <-100..100>"))
            return
        try:
            value = int(args[0])
        except ValueError:
            value = 999
        if not -100 <= value <= 100:
            self.bot.privateMessage(user_id, self._("Player TTS rate must be between -100 and 100."))
            return
        self.bot.playback_config["announcement_rate"] = value
        self.bot.config_handler.update_playback_settings({"announcement_rate": value})
        self.bot.privateMessage(user_id, self._("Player TTS rate set to {value}.").format(value=value))

    def handle_player_tts_speed_command(self, textmessage, *args):
        user_id = textmessage.nFromUserID
        if self.bot.tts_cog.get_player_tts_mode() != "google":
            self.bot.privateMessage(user_id, self._("Player TTS speed is available in Google mode. For Microsoft use pttsrate."))
            return
        if not args:
            self.bot.privateMessage(user_id, self._("Usage: pttsspeed <0.25..4.0>"))
            return
        try:
            value = float(args[0])
        except ValueError:
            value = -1.0
        if not 0.25 <= value <= 4.0:
            self.bot.privateMessage(user_id, self._("Player Google TTS speed must be between 0.25 and 4.0."))
            return
        self.bot.playback_config["announcement_google_speed"] = value
        self.bot.config_handler.update_playback_settings({"announcement_google_speed": value})
        self.bot.privateMessage(user_id, self._("Player Google standard TTS speed set to {value}.").format(value=value))

    def handle_prefixed_message(self, textmessage):
        """
        Legacy Player text-prefix shortcuts are disabled; registered commands are handled centrally.
        """
        return False

    def _is_in_same_channel(self, user_id):
        """Helper to check if a user is in the bot's channel."""
        from bot.web_controls import WEB_ACTOR_ID
        if user_id == WEB_ACTOR_ID:
            return bool(self.bot.getMyChannelID())
        user = self.bot.getUser(user_id)
        if not user or user.nChannelID != self.bot.getMyChannelID():
            print(f"Player command ignored: user {user_id} is not in bot channel {self.bot.getMyChannelID()}")
            self.bot.privateMessage(user_id, self._("You are not in the same channel"))
            return False
        return True

    def _nickname(self, user_id):
        """Return a safe nickname even if an async task finishes after logout."""
        from bot.web_controls import WEB_ACTOR_ID
        if user_id == WEB_ACTOR_ID:
            return "Web Manager"
        try:
            user = self.bot.getUser(user_id)
            if user:
                return utils.ensure_text(ttstr(user.szNickname)).strip() or self._("Unknown")
        except Exception:
            pass
        return self._("Unknown")

    def _send_playback_message(self, message, user_id=None):
        if self.bot.playback_config.get("send_channel_messages", True):
            self.bot.send_message(message)
            return
        if self.bot.playback_config.get("channel_messages_mode", "private") == "private" and user_id:
            self.bot.privateMessage(user_id, message)

    def _announce_track(self, title):
        """Announce only after the current generation is genuinely producing audio.

        TTS is mixed with music on the same PulseAudio sink. Announcing directly
        after play_stream() used to let TTS finish while mpv was still buffering,
        creating an apparent 2-5 second "dead gap" even though transport startup
        was still in progress.
        """
        if not self.bot.playback_config.get("announce_tracks", True):
            return
        expected_link = str(getattr(self.player, "current_link", "") or "")
        expected_epoch = int(getattr(self.player, "active_playback_epoch", 0) or 0)
        text = self._("Now playing: {title}").format(title=title)

        def announce_when_ready():
            waiter = getattr(self.player, "wait_for_audio_ready", None)
            ready = True
            if callable(waiter):
                try:
                    ready = bool(waiter(expected_epoch=expected_epoch, timeout=6.0))
                except Exception:
                    ready = False
            if not ready:
                self._trace("track_announce_skipped", reason="audio_not_ready", title=title)
                return
            if (int(getattr(self.player, "active_playback_epoch", 0) or 0) != expected_epoch
                    or str(getattr(self.player, "current_link", "") or "") != expected_link
                    or not bool(getattr(self.player, "is_playing", False))):
                self._trace("track_announce_skipped", reason="stale_generation", title=title)
                return
            try:
                self.bot.tts_cog.announce_player(text)
                self._trace("track_announce_queued", title=title)
            except Exception as exc:
                print(f"Track announcement failed: {exc}")

        pool = getattr(self.bot, "quick_task_pool", None)
        if pool is not None and hasattr(pool, "submit"):
            pool.submit(announce_when_ready)
        else:
            announce_when_ready()

    def _announce_queue(self, title=None, count=None, start=None, end=None, collection_title=None, nickname=None, collection_kind="playlist"):
        if not self.bot.playback_config.get("announce_queue", True):
            return
        try:
            who = nickname or self._("Unknown")
            if count is not None and start is not None and end is not None:
                name = collection_title or self._("playlist")
                if collection_kind == "favorites":
                    text = self._("{nickname} added all favorites to queue {start}-{end}.").format(
                        nickname=who, start=start, end=end
                    )
                else:
                    text = self._("{nickname} added playlist {title} to queue {start}-{end}.").format(
                        nickname=who, title=name, start=start, end=end
                    )
            elif start is not None:
                text = self._("{nickname} added to queue {position}: {title}").format(
                    nickname=who, position=start, title=title or self._("Unknown")
                )
            elif count is not None:
                text = self._("{nickname} added {count} tracks to the queue.").format(nickname=who, count=count)
            else:
                text = self._("{nickname} added to queue: {title}").format(nickname=who, title=title or self._("Unknown"))
            self.bot.tts_cog.announce_player(text)
        except Exception as exc:
            print(f"Queue announcement failed: {exc}")

    def handle_play_url_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        self._cancel_pending_retry(invalidate=True)
            
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: u <link>"))
            return

        link = " ".join(args)
        collection_type = self.player.classify_collection_link(link)
        if collection_type:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Loading {collection_type}...").format(collection_type=collection_type))
            self.bot.io_pool.submit(self._play_collection_task, link, textmessage.nFromUserID)
            return
            
        if self.player.queue_mode:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Adding URL to queue..."))
            self.bot.io_pool.submit(self._enqueue_url_task, link, textmessage.nFromUserID)
            return

        self.player.clear_collection()
        self.loading_new_track = True
        try:
            if self.player.is_playing:
                self.player.stop_transport()
            self.player.current_link = link
            self._set_playback_context("direct", link, f"request-{time.time_ns()}")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(link)
        except Exception as e:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Error playing stream: {e}").format(e=str(e)))
            self._mark_sync_play_error(e)
            self._finish_loading_transition()
            self._submit_playback(self.on_playback_end)
            return
        finally:
            if self.loading_new_track:
                self._finish_loading_transition()
        user_nickname = self._nickname(textmessage.nFromUserID)
        self._send_playback_message(self._("{nickname} requested playing from a URL").format(nickname=user_nickname))
        self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
        self._announce_track(self.player.media_title)
        try:
            host = (urlparse(str(link)).hostname or "").lower()
        except Exception:
            host = ""
        self._log_action(
            "playback_started", source="url", host=host or "unknown", title=self.player.media_title, mode="direct"
        )
        if "youtube.com" in str(link) or "youtu.be" in str(link):
            source = "ytmusic" if "music.youtube.com" in str(link) else "youtube"
            self.player.reset_radio_history({"title": self.player.media_title, "link": link, "source": source}, source)
        else:
            self.player.clear_radio_history()

    def _enqueue_url_task(self, link, user_id):
        try:
            info = None
            ydl_error = None
            try:
                with self.player._ydl_lock:
                    info = self.player._extract_play_info_resilient(link)
                    # Store before releasing the shared extraction lock so a first
                    # queue playback cannot slip between extraction and cache commit.
                    if info and info.get('url'):
                        self.player._prefetch_cache[link] = info
                        self.player._prefetch_times[link] = time.monotonic()
            except Exception as exc:
                ydl_error = exc

            # Queue mode must use the same broad URL fallback as immediate `u`.
            # A station homepage often gives yt-dlp metadata but no direct URL, or
            # generic extraction may fail completely. Resolve its embedded player
            # dynamically and cache a synthetic playable info object for handoff.
            if not info or not info.get('url'):
                host = (urlparse(str(link)).hostname or "").lower()
                is_public_web_url = str(link).lower().startswith(("http://", "https://"))
                is_youtube = any(x in host for x in ("youtube.com", "youtu.be", "music.youtube.com"))
                resolved = None
                if is_public_web_url and not is_youtube:
                    resolved = self.player._resolve_radio_webpage(link)
                if resolved and resolved.get('url'):
                    info = {
                        'title': resolved.get('title') or str(link),
                        'url': resolved['url'],
                        'webpage_url': str(link),
                        '_sntalkbot_resolved_stream': True,
                    }
                    self.player._prefetch_cache[link] = info
                    self.player._prefetch_times[link] = time.monotonic()
                elif ydl_error is not None:
                    raise ydl_error
                else:
                    raise ValueError("No playable URL found for the requested link.")

            video = {
                'title': info.get('title') or "Unknown title",
                'link': link
            }
            # _enqueue_url_task already paid the full yt-dlp extraction cost;
            # queue playback now consumes the cached result.
            queue_range = self._enqueue_queue_items([video], user_id=user_id)
            start, _end, should_start = queue_range or (None, None, False)
            user_nickname = self._nickname(user_id)
            self._send_playback_message(self._("{nickname} added to queue {position}: {title}").format(
                nickname=user_nickname, position=start or "?", title=video['title']))
            self._announce_queue(title=video['title'], start=start, nickname=user_nickname)
            self._after_queue_enqueue(should_start)
            try:
                host = (urlparse(str(link)).hostname or "").lower()
            except Exception:
                host = ""
            self._log_action(
                "queue_added", source="url", position=start or "?", host=host or "unknown", title=video.get("title", "")
            )
        except Exception as e:
            self.bot.privateMessage(user_id, self._("Error adding to queue: {e}").format(e=str(e)))

    def handle_append_playlist_command(self, textmessage, *args):
        """Append a playlist URL or search playlists by name without altering the queue."""
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: pp <playlist link or name>; pps <number> selects a search result."))
            return
        link = " ".join(args).strip()
        if self.player.classify_collection_link(link) == "playlist":
            self.bot.privateMessage(textmessage.nFromUserID, self._("Appending playlist..."))
            self.bot.io_pool.submit(self._play_collection_task, link, textmessage.nFromUserID, True)
            return
        if link.lower().startswith(("http://", "https://")):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Use a YouTube or YouTube Music playlist link, or search by playlist name."))
            return
        if len(link) > 500:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Playlist search is too long (maximum 500 characters)."))
            return
        self.bot.privateMessage(textmessage.nFromUserID, self._("Searching YouTube playlists..."))
        self.bot.io_pool.submit(self._search_playlists_for_user, link, textmessage.nFromUserID)

    def _search_playlists_for_user(self, query, user_id):
        try:
            playlists = self.player.search_playlists(query, limit=10)
        except Exception as exc:
            self.bot.privateMessage(user_id, self._("Playlist search failed: {error}").format(error=type(exc).__name__))
            return
        with self.pending_playlist_search_lock:
            if playlists:
                self.pending_playlist_searches[user_id] = {
                    "options": playlists, "expires_at": time.monotonic() + 180,
                }
            else:
                self.pending_playlist_searches.pop(user_id, None)
        if not playlists:
            self.bot.privateMessage(user_id, self._("No playlists found. Try another name or paste a playlist link."))
            return
        self.bot.privateMessage(user_id, self._("Playlist search results (use pps <number> to add to the end):"))
        for number, item in enumerate(playlists, 1):
            self.bot.privateMessage(user_id, f"{number}. {item['title'][:160]} — {item.get('channel') or 'YouTube'}")

    def handle_playlist_search_selection_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        user_id = textmessage.nFromUserID
        with self.pending_playlist_search_lock:
            pending = self.pending_playlist_searches.get(user_id)
            if not pending or time.monotonic() >= pending["expires_at"]:
                self.pending_playlist_searches.pop(user_id, None)
                self.bot.privateMessage(user_id, self._("No active playlist search. Search with pp <name> first."))
                return
            try:
                selection = int(args[0]) if len(args) == 1 else 0
            except (TypeError, ValueError):
                selection = 0
            if not 1 <= selection <= len(pending["options"]):
                self.bot.privateMessage(user_id, self._("Invalid playlist number. Choose a number shown in your search results."))
                return
            chosen = pending["options"][selection - 1]
            del self.pending_playlist_searches[user_id]
        self.bot.privateMessage(user_id, self._("Adding selected playlist to the end: {title}").format(title=chosen["title"]))
        self.bot.io_pool.submit(self._play_collection_task, chosen["link"], user_id, True)

    def _play_collection_task(self, link, user_id, append=False):
        collection_type, collection_title, results = self.player.fetch_collection_details(link)
        if not results:
            self.bot.privateMessage(user_id, self._("No videos found in the {collection_type}.").format(collection_type=collection_type or "playlist/channel"))
            return

        if append and collection_type != "playlist":
            self.bot.privateMessage(user_id, self._("pp accepts playlists only."))
            return

        if self.player.queue_mode:
            queue_range = self._enqueue_queue_items(results, user_id=user_id)
            start, end, should_start = queue_range or (None, None, False)
            title = collection_title or collection_type or self._("playlist")
            self._send_playback_message(self._("{nickname} added playlist {title} to queue {start}-{end}.").format(
                nickname=self._nickname(user_id), title=title, start=start or "?", end=end or "?"
            ))
            self._announce_queue(
                count=len(results), start=start, end=end, collection_title=title, nickname=self._nickname(user_id)
            )
            self._after_queue_enqueue(should_start)
            return

        if append:
            # pp never interrupts the currently playing track.  If a collection is
            # already active, simply extend it.  If a normal single track is active,
            # make that track the synthetic first item so the appended playlist starts
            # only after it ends.  With nothing playing, pp is tolerant and starts the
            # playlist immediately.
            if self.player.collection_results:
                start_position = len(self.player.collection_results) + 1
                self.player.collection_results.extend(results)
                end_position = len(self.player.collection_results)
                self._prefetch_next_for_current()
                self._send_playback_message(self._("{nickname} appended playlist {title} as items {start}-{end}.").format(
                    nickname=self._nickname(user_id), title=collection_title or self._("playlist"),
                    start=start_position, end=end_position
                ))
                return

            if self.player.is_playing and self.player.current_link:
                current = {
                    "title": self.player.media_title or self._("Current track"),
                    "link": self.player.current_link,
                    "source": "ytmusic" if "music.youtube.com" in str(self.player.current_link) else "youtube",
                }
                self.player.search_results = []
                self.player.current_search_index = 0
                self.player.collection_results = [current] + results
                self.player.current_collection_index = 0
                self.player.collection_source = "playlist_session"
                self._prefetch_next_for_current()
                self._send_playback_message(self._("{nickname} appended playlist {title}; it will play next.").format(
                    nickname=self._nickname(user_id), title=collection_title or self._("playlist")
                ))
                return
            # Nothing is playing: pp may serve as the first playlist for convenience.

        self.player.search_results = []
        self.player.current_search_index = 0
        self.player.collection_results = results
        self.player.current_collection_index = 0
        self.player.collection_source = collection_type
        self.player.clear_radio_history()
        first_video = results[0]
        play_error = None
        self.loading_new_track = True
        try:
            if self.player.is_playing:
                self.player.stop_transport()
            self.player.current_link = first_video["link"]
            self._set_playback_context("collection", first_video["link"], f"{collection_type}:0")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(first_video["link"])
        except Exception as e:
            play_error = e
            self._send_playback_message(self._("Error playing {title}: {e}").format(title=first_video['title'], e=str(e)))
            self._mark_sync_play_error(e)
        finally:
            self._finish_loading_transition()
        if play_error is not None:
            self._submit_playback(self.on_playback_end)
            return
        self._prefetch_next_for_current()
        user_nickname = self._nickname(user_id)
        self._send_playback_message(self._("{nickname} requested to play from a {collection_type}").format(
            nickname=user_nickname, collection_type=collection_type or "playlist/channel"))
        self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
        self._announce_track(self.player.media_title)

    def handle_channel_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        if not self.player.is_playing or not self.player.current_link:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return

        self.bot.privateMessage(textmessage.nFromUserID, self._("Loading channel tabs..."))
        self.bot.io_pool.submit(self._fetch_channel_tabs_task, textmessage.nFromUserID, self.player.current_link)

    def _fetch_channel_tabs_task(self, user_id, current_link):
        channel_link = self.player.get_channel_link(current_link)
        if not channel_link:
            self.bot.privateMessage(user_id, self._("Unable to determine the channel for the current video."))
            return
        tabs = self.player.get_channel_tabs(channel_link)
        if not tabs:
            self.bot.privateMessage(user_id, self._("No channel tabs with playable videos were found."))
            return
        self.pending_channel_tabs[user_id] = {
            "options": tabs,
            "expires_at": time.time() + self.pending_channel_timeout,
        }
        lines = [self._("Choose a tab by number:")]
        for idx, tab in enumerate(tabs, start=1):
            lines.append(f"{idx}) {tab['name']}")
        self.bot.privateMessage(user_id, "\n".join(lines))

    def handle_channel_selection_message(self, textmessage):
        user_id = textmessage.nFromUserID
        pending = self.pending_channel_tabs.get(user_id)
        if not pending:
            return False
        message_text = utils.ensure_text(ttstr(textmessage.szMessage)).strip()
        if time.time() > pending["expires_at"]:
            del self.pending_channel_tabs[user_id]
            if message_text.isdigit():
                self.bot.privateMessage(user_id, self._("Channel selection expired. Use channel again."))
                return True
            return False
        if not message_text.isdigit():
            return False
        selection = int(message_text)
        options = pending["options"]
        if selection < 1 or selection > len(options):
            self.bot.privateMessage(user_id, self._("Invalid selection. Choose a number from the list."))
            return True
        del self.pending_channel_tabs[user_id]
        chosen = options[selection - 1]
        self.bot.privateMessage(user_id, self._("Loading {tab}...").format(tab=chosen["name"]))
        self.bot.io_pool.submit(self._play_channel_tab_task, user_id, chosen)
        return True

    def _play_channel_tab_task(self, user_id, chosen):
        try:
            if chosen.get("kind") == "playlists":
                playlists = self.player.get_channel_playlists(chosen["link"])
                if not playlists:
                    self.bot.privateMessage(user_id, self._("No playlists found on this channel."))
                    return
                self.pending_playlist_tabs[user_id] = {
                    "options": playlists,
                    "expires_at": time.time() + self.pending_channel_timeout,
                }
                lines = [self._("Choose a playlist by number:")]
                for idx, playlist in enumerate(playlists, start=1):
                    lines.append(f"{idx}) {playlist['title']}")
                self.bot.privateMessage(user_id, "\n".join(lines))
                return
            self._play_collection_task(chosen["link"], user_id)
        except Exception as e:
            self.bot.privateMessage(user_id, self._("Failed to load the selected tab: {e}").format(e=str(e)))

    def handle_playlist_selection_message(self, textmessage):
        user_id = textmessage.nFromUserID
        pending = self.pending_playlist_tabs.get(user_id)
        if not pending:
            return False
        message_text = utils.ensure_text(ttstr(textmessage.szMessage)).strip()
        if time.time() > pending["expires_at"]:
            del self.pending_playlist_tabs[user_id]
            if message_text.isdigit():
                self.bot.privateMessage(user_id, self._("Playlist selection expired. Use channel again."))
                return True
            return False
        if not message_text.isdigit():
            return False
        selection = int(message_text)
        options = pending["options"]
        if selection < 1 or selection > len(options):
            self.bot.privateMessage(user_id, self._("Invalid selection. Choose a number from the list."))
            return True
        del self.pending_playlist_tabs[user_id]
        chosen = options[selection - 1]
        self.bot.privateMessage(user_id, self._("Loading playlist..."))
        self.bot.io_pool.submit(self._play_collection_task, chosen["link"], user_id)
        return True

    def handle_play_search_or_pause_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        self._cancel_pending_retry(invalidate=True)

        if args: # This is a search request
            query = " ".join(args)
            if self.player.queue_mode:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Searching to add to queue..."))
                self.bot.io_pool.submit(self._search_and_enqueue_task, query, textmessage.nFromUserID)
            else:
                if self.player.is_playing:
                    self.loading_new_track = True
                    try:
                        self.player.fade_out_and_stop()
                        self.bot.enableVoiceTransmission(False)
                    finally:
                        self._finish_loading_transition()
                self.player.clear_collection()
                self.bot.privateMessage(textmessage.nFromUserID, self._("Searching..."))
                self.bot.io_pool.submit(self._search_and_play_task, query, textmessage.nFromUserID)
        else: # Restart the current item from the beginning. Pause/resume is x.
            self._restart_current_item(textmessage.nFromUserID)

    def _restart_current_item(self, user_id):
        if self.player.queue_mode and self.player.queue:
            with self.player.queue_lock:
                index = self.player.queue_index
                if index < 0 or index >= len(self.player.queue):
                    index = 0
                    self.player.queue_index = 0
            self._submit_playback(self._play_from_queue, index)
            return
        link = self.player.current_link
        if not link:
            self.bot.privateMessage(user_id, self._("Nothing is currently available to play."))
            return
        self.loading_new_track = True
        play_error = None
        try:
            self.player.stop_transport()
            self.player.current_link = link
            self._set_playback_context("restart", link, f"manual-{time.time_ns()}")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(link)
            self.bot.doChangeStatus(
                ttstr(self.bot.bot_config['gender']),
                ttstr(self._("Playing: {title}").format(title=self.player.media_title)),
            )
            self._announce_track(self.player.media_title)
            self._prefetch_next_for_current()
        except Exception as exc:
            play_error = exc
            self.bot.privateMessage(user_id, self._("Error playing track: {error}").format(error=str(exc)))
            self._mark_sync_play_error(exc)
        finally:
            self._finish_loading_transition()
        if play_error is not None:
            self._submit_playback(self.on_playback_end)

    def handle_ytmusic_search_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        self._cancel_pending_retry(invalidate=True)
        
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: pm <name>"))
            return
        
        query = " ".join(args)
        if self.player.queue_mode:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Searching YouTube Music to add to queue..."))
            self.bot.io_pool.submit(self._search_and_enqueue_task, query, textmessage.nFromUserID, source='ytmusic')
        else:
            if self.player.is_playing:
                self.loading_new_track = True
                try:
                    self.player.fade_out_and_stop()
                    self.bot.enableVoiceTransmission(False)
                finally:
                    self._finish_loading_transition()
            self.player.clear_collection()
            self.bot.privateMessage(textmessage.nFromUserID, self._("Searching YouTube Music..."))
            self.bot.io_pool.submit(self._search_and_play_task, query, textmessage.nFromUserID, source='ytmusic')

    def _search_and_play_task(self, query, user_id, source='youtube'):
        """Search and play with visible failure reporting for async workers."""
        try:
            search_started = time.monotonic()
            # Start from one result so audio wins the cold-start race,
            # while the historical 50/20 options can arrive in the background.
            if source == 'ytmusic':
                results = self.player.search_ytmusic(query, limit=INITIAL_SEARCH_RESULTS)
            else:
                results = self.player.search_youtube(query, limit=INITIAL_SEARCH_RESULTS)
            needs_expansion = bool(results)
            if not results:
                # Keep the historical complete-search recovery when YouTube's
                # one-hit search temporarily gives no usable result.
                results = (self.player.search_ytmusic(query) if source == 'ytmusic'
                           else self.player.search_youtube(query))
            search_elapsed = time.monotonic() - search_started
            if search_elapsed >= 2.0:
                print(f"First-track search took {search_elapsed:.2f}s (source={source})")

            if results:
                # This list object acts as the search-session identity. A
                # subsequent p/pm creates a different list, so an older
                # background completion cannot overwrite a newer search.
                search_session = list(results)
                self.player.search_results = search_session
                self.player.current_search_index = 0
                first_video = results[0]
                self.player.reset_radio_history(first_video, source)
                self.player.current_link = first_video['link']
                self._set_playback_context("search", first_video['link'], f"{source}:0")
                self.bot.enableVoiceTransmission(True)
                try:
                    self.player.play_stream(first_video['link'])
                except Exception as e:
                    print(f"{source} playback failed for query {query!r}: {type(e).__name__}: {e}")
                    self._send_playback_message(
                        self._("Error playing {title}: {e}").format(title=first_video['title'], e=str(e)),
                        user_id,
                    )
                    self._mark_sync_play_error(e)
                    self._submit_playback(self.on_playback_end)
                    return
                self._prefetch_next_for_current()
                user_nickname = self._nickname(user_id)
                self._send_playback_message(
                    self._("{nickname} requested to play: {title}").format(nickname=user_nickname, title=first_video['title']),
                    user_id,
                )
                self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
                self._announce_track(self.player.media_title)
                self._log_action(
                    "playback_started", source=source, title=first_video.get("title", ""), mode="search"
                )
                if needs_expansion:
                    self.bot.io_pool.submit(self._expand_active_search_results, query, source, search_session)
            else:
                print(f"{source} search returned no results for query {query!r}")
                self._send_playback_message(self._("No results found for '{query}'.").format(query=query), user_id)
        except Exception as exc:
            print(f"{source} search/play worker failed for query {query!r}: {type(exc).__name__}: {exc}")
            self.bot.privateMessage(
                user_id,
                self._("Error playing track: {error}").format(error=f"{type(exc).__name__}: {exc}"),
            )

    def _expand_active_search_results(self, query, source, search_session):
        """Load navigation results after playback without hijacking newer p/pm."""
        try:
            results = (self.player.search_ytmusic(query) if source == 'ytmusic'
                       else self.player.search_youtube(query))
        except Exception as exc:
            print(f"Background search expansion failed: {type(exc).__name__}")
            return
        if not results or self.player.search_results is not search_session:
            return
        seen = {str(item.get("link") or "") for item in search_session}
        for item in results:
            link = str(item.get("link") or "")
            if link and link not in seen:
                seen.add(link)
                search_session.append(dict(item))
        if not self.player.queue_mode:
            self._prefetch_next_for_current()

    def _search_and_enqueue_task(self, query, user_id, source='youtube'):
        """Search and enqueue with visible failure reporting for async workers."""
        try:
            search_started = time.monotonic()
            # Fetch only the first choice on a cold queue, matching the fastest reference path, not
            # all 50 metadata entries before starting a cold queue.
            # A non-empty/busy queue retains the complete original search path.
            with self.player.queue_lock:
                fast_start = (
                    self.player.queue_mode and not self.player.queue
                    and self.player.queue_index < 0
                    and not self.player.queue_transition
                    and not self.player.playback_end_transition
                    and not self.player.is_playing
                )
            if source == 'ytmusic':
                results = self.player.search_ytmusic(query, limit=INITIAL_SEARCH_RESULTS) if fast_start else self.player.search_ytmusic(query)
            else:
                results = self.player.search_youtube(query, limit=INITIAL_SEARCH_RESULTS) if fast_start else self.player.search_youtube(query)
            if fast_start and not results:
                results = (self.player.search_ytmusic(query) if source == 'ytmusic'
                           else self.player.search_youtube(query))
                fast_start = False
            search_elapsed = time.monotonic() - search_started
            if search_elapsed >= 2.0:
                print(f"Queue search took {search_elapsed:.2f}s (source={source}; first_only={fast_start})")

            if results:
                # Keep this result set attached to the queue item instead of only in
                # the Player-global search buffer. Multiple users can therefore have
                # independent pending searches in the same FIFO queue.
                video = dict(results[0])
                video["_search_results"] = [dict(item) for item in results]
                video["_search_index"] = 0
                video["_search_source"] = source
                queue_range = self._enqueue_queue_items([video], user_id=user_id)
                start, _end, should_start = queue_range or (None, None, False)
                expansion_token = None
                if fast_start and start is not None:
                    with self.player.queue_lock:
                        if 0 < start <= len(self.player.queue):
                            expansion_token = self.player.queue[start - 1].get("_queue_token")
                user_nickname = self._nickname(user_id)
                self._send_playback_message(
                    self._("{nickname} added to queue {position}: {title}").format(
                        nickname=user_nickname, position=start or "?", title=video['title']
                    ),
                    user_id,
                )
                self._announce_queue(title=video['title'], start=start, nickname=user_nickname)
                self._after_queue_enqueue(should_start)
                if expansion_token:
                    # The initial play() has already been invoked here. Do not
                    # delay it while fetching the remaining search alternatives.
                    self.bot.io_pool.submit(self._expand_queued_search_results, query, source, expansion_token)
                self._log_action(
                    "queue_added", source=source, position=start or "?", title=video.get("title", "")
                )
            else:
                print(f"{source} queue search returned no results for query {query!r}")
                self._send_playback_message(self._("No results found for '{query}'.").format(query=query), user_id)
        except Exception as exc:
            print(f"{source} search/enqueue worker failed for query {query!r}: {type(exc).__name__}: {exc}")
            self.bot.privateMessage(
                user_id,
                self._("Error playing track: {error}").format(error=f"{type(exc).__name__}: {exc}"),
            )

    def _expand_queued_search_results(self, query, source, queue_token):
        """Restore full search navigation without delaying first-song playback.

        A queue token, not an array index or URL, identifies the original
        request. Deleted/replaced entries cannot receive stale search results.
        """
        try:
            results = (self.player.search_ytmusic(query) if source == 'ytmusic'
                       else self.player.search_youtube(query))
        except Exception as exc:
            print(f"Background queue search expansion failed: {type(exc).__name__}")
            return
        if not results:
            return
        with self.player.queue_lock:
            for index, entry in enumerate(self.player.queue):
                if not isinstance(entry, dict) or entry.get("_queue_token") != queue_token:
                    continue
                # The quick hit must stay at index 0 even if YouTube changes
                # ranking between the two searches. Preserve any selection
                # the user made while the full results were loading.
                existing = list(entry.get("_search_results") or [])
                merged = []
                seen = set()
                for item in existing + list(results):
                    link = str(item.get("link") or "") if isinstance(item, dict) else ""
                    if not link or link in seen:
                        continue
                    seen.add(link)
                    merged.append(dict(item))
                updated = dict(entry)
                updated["_search_results"] = merged
                self.player.queue[index] = updated
                return

    def _play_from_queue(self, index, expected_token=None, expected_link=None):
        self._trace("queue_play_request", requested_index=index, has_expected_token=bool(expected_token), has_expected_link=bool(expected_link))
        with self.player.queue_lock:
            if index < 0 or index >= len(self.player.queue):
                self.player.queue_index = -1
                self.player.queue_transition = False
                return
            selected = self.player.queue[index]
            if (expected_token is not None and selected.get("_queue_token") != expected_token) or (
                expected_link is not None and selected.get("link") != expected_link
            ):
                return  # A newer . / , choice superseded this pending restart.
            self.player.queue_index = index
            self.player.queue_transition = True
            video = dict(self.player.queue[index])

        self._trace("queue_play_selected", requested_index=index, link=video.get("link"), token=str(video.get("_queue_token") or "")[-16:])
        self.loading_new_track = True
        error = None
        try:
            # Queue playback is its own state machine. Do not leave a stale
            # playlist/channel/radio behind that could resume after cq/q off.
            self.player.clear_collection()
            self.player.clear_radio_history()
            self._stop_transport_for_replacement()
            self.player.current_link = video['link']
            self._set_playback_context("queue", video['link'], str(video.get("_queue_token") or self._queue_token(index)))
            # Open TeamTalk transmission before MPV emits the first samples.
            # The old order could clip/delay the beginning of a queue track.
            self.bot.enableVoiceTransmission(True)
            self._trace("queue_voice_enabled", requested_index=index)
            self.player.play_stream(video['link'])
            self._trace("queue_play_loaded", requested_index=index, title=self.player.media_title)
            # As soon as current playback is live, prepare the next FIFO items.
            # This keeps queue-to-queue handoff fast even for short tracks.
            self._prefetch_next_for_current()
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
        except Exception as e:
            error = e
            self._send_playback_message(self._("Error playing {title}: {e}").format(title=video.get('title', 'Unknown'), e=str(e)))
            self._mark_sync_play_error(e)
        finally:
            # A synchronous play_stream exception already has an explicit skip
            # path below. Drop any duplicate terminal event that raced with it.
            if error is not None:
                self._deferred_playback_end = False
            with self.player.queue_lock:
                self.player.queue_transition = False
            self._trace("queue_play_finish", requested_index=index, error=type(error).__name__ if error else "")
            self._finish_loading_transition()
        if error is not None:
            # Send synchronous failures through the same retry/skip state machine
            # used by asynchronous END_FILE errors.
            self._submit_playback(self.on_playback_end)

    def handle_pause_resume_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
            
        title = self.player.media_title
        if self.player.is_playing and not self.player.pause:
            self.player.pause_stream()
            self.bot.enableVoiceTransmission(False)
            user_nickname = self._nickname(textmessage.nFromUserID)
            self._send_playback_message(self._("{nickname} paused the playback").format(nickname=user_nickname))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Paused: {title}").format(title=title)))
        elif self.player.pause:
            self.player.pause = False
            self.bot.enableVoiceTransmission(True)
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=title)))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing to pause or resume."))

    def handle_seek_forward_command(self, textmessage, *args):
        arg_str = args[0] if args else "10"
        self.handle_seek_forward(textmessage, arg_str)

    def handle_seek_back_command(self, textmessage, *args):
        arg_str = args[0] if args else "10"
        self.handle_seek_back(textmessage, arg_str)

    def handle_seek_forward(self, textmessage, arg_str):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return
        
        try:
            amount = int(arg_str) if arg_str else 10
            self.player.seek_forward(amount)
        except ValueError:
            self.player.seek_forward(10)
            
    def handle_seek_back(self, textmessage, arg_str):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return
        
        try:
            amount = int(arg_str) if arg_str else 10
            self.player.seek_back(amount)
        except ValueError:
            self.player.seek_back(10)

    def handle_seek_to_time_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: t <time> (e.g., 1:30 or 90)"))
            return
        
        time_str = args[0]
        try:
            if ":" in time_str:
                parts = time_str.split(":")
                if len(parts) == 2:
                    seconds = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                else:
                    raise ValueError
            else:
                seconds = int(time_str)
            
            self.player.seek(seconds, reference="absolute")
        except ValueError:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid time format. Use seconds or M:S or H:M:S."))

    def handle_next_track_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        self._cancel_pending_retry(invalidate=True)

        def play_next_track():
            if self.player.queue_mode:
                self._play_next_queue_manual(user_id=textmessage.nFromUserID)
            else:
                self._play_next_related(user_id=textmessage.nFromUserID, announce_private=True)
        self._submit_playback(play_next_track)

    def handle_previous_track_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        self._cancel_pending_retry(invalidate=True)

        def play_previous_track():
            if self.player.queue_mode:
                self._play_previous_queue_manual(user_id=textmessage.nFromUserID)
            else:
                self._play_previous_related(user_id=textmessage.nFromUserID, announce_private=True)
        self._submit_playback(play_previous_track)
        
    def handle_stop_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        pending_retry = self._cancel_pending_retry(invalidate=True)
        if pending_retry or self._transport_or_voice_active():
            # Stop transport only. Queue/playlist/search/current link remain intact so
            # p can restart the same item from 00:00; cq is the explicit queue clear.
            self.loading_new_track = True
            try:
                self.player.stop_transport()
                self.player.pause = False
                self.bot.enableVoiceTransmission(False)
            finally:
                self._finish_loading_transition()
            user_nickname = self._nickname(textmessage.nFromUserID)
            self._send_playback_message(self._("{nickname} stopped the playback").format(nickname=user_nickname))
            status_msg = self.bot.get_idle_status_message()
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(status_msg))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))

    def handle_change_volume_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        try:
            if not args:
                self.bot.privateMessage(textmessage.nFromUserID, self._("The current volume is {volume}").format(volume=int(self.player.volume)))
                return
            
            volume = int(args[0])
            max_volume = self.bot.playback_config['max_volume']
            if volume > max_volume:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Maximum allowed volume is {max_volume}").format(max_volume=max_volume))
            else:
                self.player.volume = volume
                user_nickname = self._nickname(textmessage.nFromUserID)
                self._send_playback_message(self._("{name} has changed the volume to {volume}").format(name=user_nickname, volume=volume))
        except (ValueError, IndexError):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: v [volume_level]"))

    def on_playback_end(self):
        """Advance without losing queue order at the mpv end-of-track boundary."""
        self._trace("cog_playback_end_enter", end_reason=getattr(self.player, "last_end_reason", None), end_error=getattr(self.player, "last_end_error", 0))
        if self.loading_new_track:
            self._deferred_playback_end = True
            self._trace("cog_playback_end_deferred")
            return
        if hasattr(self.player, "last_end_reason") and self.player.last_end_reason is None:
            return  # A queued callback from an older load, not this live item.

        # Inspect the terminal reason before generic retry/cancel guards. A clean
        # Queue EOF is generation-deduped by Player._dispatch_end_once() and must
        # never be suppressed by stale failure flags from an older load.
        end_reason = str(getattr(self.player, "last_end_reason", "") or "").lower()
        end_error = int(getattr(self.player, "last_end_error", 0) or 0)
        if end_reason == "eof":
            with self.player.queue_lock:
                queue_has_current = self.player.queue_index >= 0 and bool(self.player.queue)
                queue_has_pending = bool(self.player.queue)
            queue_owns_current = queue_has_current and self._queue_owns_current_playback()
            queue_takeover = bool(self.player.queue_mode and queue_has_pending)
            if queue_owns_current or queue_takeover:
                self._trace(
                    "queue_clean_eof_fastpath",
                    queue_has_current=queue_has_current,
                    queue_has_pending=queue_has_pending,
                    queue_owns_current=queue_owns_current,
                    queue_takeover=queue_takeover,
                )
                with self._ensure_failure_state():
                    pending = self._retry_pending
                    if pending:
                        pending["cancel"].set()
                    self._retry_pending = None
                    self._terminal_cancelled = False
                    self._failure_count = 0
                if self._advance_queue_after_current(remember=queue_owns_current):
                    return
                # If Queue mode was turned off while its current item was
                # playing, consume that item but continue through normal
                # autoplay/radio logic. Only an enabled/exhausted Queue owns the
                # natural-stop behavior.
                if self.player.queue_mode:
                    self._finish_natural_playback()
                    return

        with self._ensure_failure_state():
            if getattr(self, "_terminal_cancelled", False):
                self._trace("terminal_ignored_cancelled", reason=end_reason)
                return
            if self._retry_pending:
                self._trace("terminal_ignored_retry_pending", reason=end_reason)
                return  # Duplicate callback while the same item awaits retry.

        with self._ensure_failure_state():
            if hasattr(self.player, "active_playback_epoch") or getattr(self, "_sync_error_serial", 0):
                marker = (self._failure_key, getattr(self.player, "active_playback_epoch", None),
                          int(getattr(self, "_sync_error_serial", 0)), end_reason, end_error)
                if marker == getattr(self, "_handled_terminal", None):
                    return
                self._handled_terminal = marker

        # A transient failure uses the configured retry budget for the same item before
        # Queue/Playlist/Radio state is advanced. This covers synchronous yt-dlp
        # failures and asynchronous libmpv END_FILE errors with one rule.
        if end_reason == "error" and self._retry_current_playback_once():
            return
        if end_reason != "error":
            self._reset_failure_budget()
        with self.player.queue_lock:
            queue_has_current = self.player.queue_index >= 0 and bool(self.player.queue)
            queue_has_pending = bool(self.player.queue)
            queue_owns_current = queue_has_current and self._queue_owns_current_playback()
            failed_title = None
            if queue_owns_current and end_reason == "error":
                try:
                    failed_title = str(self.player.queue[self.player.queue_index].get("title") or self._("Unknown"))
                except Exception:
                    failed_title = self._("Unknown")
        self._trace(
            "cog_playback_end_state",
            queue_has_current=queue_has_current,
            queue_has_pending=queue_has_pending,
            queue_owns_current=queue_owns_current,
            end_reason=end_reason,
        )
        if queue_owns_current or (self.player.queue_mode and queue_has_pending):
            if failed_title is not None:
                self._send_playback_message(
                    self._("Playback failed for {title} (player error {error}). Skipping to the next queue item...").format(
                        title=failed_title, error=end_error
                    )
                )
            if failed_title is not None and getattr(self.bot, "state_store", None) is not None:
                self._send_playback_message("เก็บรายการที่เล่นไม่สำเร็จไว้ในหน้าเว็บแล้ว สามารถส่งกลับท้ายคิวได้โดยไม่ต้องหาเพลงใหม่")
            if self._advance_queue_after_current(remember=queue_owns_current and end_reason != "error"):
                return
            if queue_owns_current and self.player.queue_mode:
                self._finish_natural_playback()
                return

        # Queue Mode is isolated from normal Related Radio. If q is still ON but
        # the queue is empty (for example after cq), the current audio may finish
        # naturally but must not fall through into M2/Autoplay recommendations.
        if self.player.queue_mode:
            self._finish_natural_playback()
            return

        # Explicit playlists/channels/favorites keep their authored order. Ordinary
        # search playback deliberately does NOT auto-walk search results anymore.
        if self.player.play_mode == 3 and self.player.current_link:
            if end_reason == "error":
                # Repeat-one must not loop a permanently broken item forever.
                self._finish_natural_playback()
                return
            self._submit_playback(self._repeat_current_track)
            return
        if (self.player.play_mode == 2 or self.autoplay_enabled) and self.player.collection_results and self._has_next_in_active_list():
            self._submit_playback(self._play_next_from_active_list, None, False)
            return
        if (self.player.play_mode == 2 or self.autoplay_enabled) and self.player.current_link:
            self._submit_playback(self._autoplay_related_or_finish)
            return

        self._finish_natural_playback()


    def _repeat_current_track(self):
        """Replay the current link for M3 repeat mode without rebuilding the active collection."""
        link = self.player.current_link
        if not link:
            return
        self.loading_new_track = True
        try:
            self._set_playback_context("repeat", link, "m3")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(link)
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
        except Exception as exc:
            self._send_playback_message(self._("Error playing {title}: {e}").format(title=self.player.media_title or "Unknown", e=str(exc)))
            self._mark_sync_play_error(exc)
        finally:
            self._finish_loading_transition()
        if str(getattr(self.player, "last_end_reason", "") or "").lower() == "error":
            self._submit_playback(self.on_playback_end)

    def handle_autoplay_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        if args:
            arg = args[0].strip().lower()
            if arg in ("on", "1", "true", "yes"):
                self.autoplay_enabled = True
            elif arg in ("off", "0", "false", "no"):
                self.autoplay_enabled = False
            else:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: autoplay [on|off]"))
                return
        else:
            self.autoplay_enabled = not self.autoplay_enabled

        if self.autoplay_enabled and self.player.play_mode != 3:
            self.player.play_mode = 2
        elif not self.autoplay_enabled and self.player.play_mode == 2:
            self.player.play_mode = 1
        self.bot.playback_config["autoplay_enabled"] = self.autoplay_enabled
        self.bot.playback_config["play_mode"] = self.player.play_mode
        self.bot.config_handler.update_playback_settings({
            "autoplay_enabled": self.autoplay_enabled,
            "play_mode": self.player.play_mode,
        })
        state = self._("enabled") if self.autoplay_enabled else self._("disabled")
        self.bot.privateMessage(textmessage.nFromUserID, self._("Autoplay is {state}.").format(state=state))
        if self.autoplay_enabled:
            self._prefetch_next_for_current()

    def _get_active_results(self):
        if self.player.queue_mode and self.player.queue:
            return self.player.queue, "queue"
        if self.player.collection_results:
            return self.player.collection_results, "collection"
        if self.player.search_results:
            return self.player.search_results, "search"
        return None, None

    def _get_active_index(self):
        if self.player.queue_mode and self.player.queue:
            return self.player.queue_index
        if self.player.collection_results:
            return self.player.current_collection_index
        return self.player.current_search_index

    def _set_active_index(self, value):
        if self.player.queue_mode and self.player.queue:
            self.player.queue_index = value
        elif self.player.collection_results:
            self.player.current_collection_index = value
        else:
            self.player.current_search_index = value

    def _has_next_in_active_list(self):
        results, _ = self._get_active_results()
        if not results:
            return False
        current_index = self._get_active_index()
        return current_index < len(results) - 1

    def _play_next_from_active_list(self, user_id=None, announce_private=False):
        results, list_type = self._get_active_results()
        if not results:
            if user_id:
                self.bot.privateMessage(user_id, self._("No list to play from."))
            return

        current_index = self._get_active_index()
        if current_index >= len(results) - 1:
            if user_id:
                self.bot.privateMessage(user_id, self._("You've reached the end of the list."))
            return

        self.loading_new_track = True
        self._set_active_index(current_index + 1)
        next_video = results[self._get_active_index()]
        
        play_error = None
        try:
            self._stop_transport_for_replacement()
            self.player.current_link = next_video['link']
            self._set_playback_context("collection", next_video['link'], f"{self.player.collection_source}:{self._get_active_index()}")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(next_video['link'])
            if announce_private and user_id:
                self.bot.privateMessage(user_id, self._("Playing: {title}").format(title=next_video['title']))
            elif user_id is None:
                self._send_playback_message(self._("Autoplaying: {title}").format(title=next_video['title']))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
            self._prefetch_next_for_current()
        except Exception as e:
            play_error = e
            self._send_playback_message(self._("Error playing {title}: {e}").format(title=next_video.get('title', 'Unknown'), e=str(e)))
            self._mark_sync_play_error(e)
        finally:
            self._finish_loading_transition()
        if play_error is not None:
            self._submit_playback(self.on_playback_end)

    def _play_previous_from_active_list(self, user_id=None, announce_private=False):
        results, _ = self._get_active_results()
        if not results:
            if user_id:
                self.bot.privateMessage(user_id, self._("No list to play from."))
            return

        current_index = self._get_active_index()
        if current_index <= 0:
            if user_id:
                self.bot.privateMessage(user_id, self._("You are at the beginning of the list."))
            return

        self.loading_new_track = True
        self._set_active_index(current_index - 1)
        prev_video = results[self._get_active_index()]
        
        play_error = None
        try:
            self.player.stop_transport()
            self.player.current_link = prev_video['link']
            self._set_playback_context("collection", prev_video['link'], f"{self.player.collection_source}:{self._get_active_index()}")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(prev_video['link'])
            if announce_private and user_id:
                self.bot.privateMessage(user_id, self._("Playing: {title}").format(title=prev_video['title']))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._prefetch_next_for_current()
        except Exception as e:
            play_error = e
            self._send_playback_message(self._("Error playing {title}: {e}").format(title=prev_video.get('title', 'Unknown'), e=str(e)))
            self._mark_sync_play_error(e)
        finally:
            self._finish_loading_transition()
        if play_error is not None:
            self._submit_playback(self.on_playback_end)

    def _prefetch_next_for_current(self):
        # Queue Mode: resolve only the immediate FIFO successor. One expensive
        # extraction should never let songs 3-6 block song 2 at handoff.
        if self.player.queue_mode:
            with self.player.queue_lock:
                start = self.player.queue_index + 1 if self.player.queue_index >= 0 else 0
                links = [
                    item.get("link") for item in self.player.queue[start:start + 1]
                    if isinstance(item, dict) and item.get("link")
                ]
                if not links and 0 <= self.player.queue_index < len(self.player.queue):
                    entry = self.player.queue[self.player.queue_index]
                    results = entry.get("_search_results") or []
                    if len(results) > 1:
                        position = int(entry.get("_search_index", 0) or 0)
                        candidate = results[(position + 1) % len(results)]
                        if candidate.get("link") and candidate["link"] != entry.get("link"):
                            links.append(candidate["link"])
            if links:
                self._trace("queue_prefetch_schedule", count=len(links), link=links[0])
                self.player.prefetcher.schedule(links)
            else:
                self._trace("queue_prefetch_none")
            return

        # Authored playlist/channel/favorites order has priority while there is
        # still a next item in that collection.
        if self.player.collection_results:
            current_index = self.player.current_collection_index
            if current_index < len(self.player.collection_results) - 1:
                link = self.player.collection_results[current_index + 1].get("link")
                if link:
                    self._trace("collection_prefetch_schedule", link=link)
                    self.player.prefetcher.schedule([link])
                return

        # Normal M2/Autoplay does NOT auto-walk search_results; it consumes
        # radio_candidates. Warm that exact state machine instead of wasting the
        # prefetch worker on a search alternative that autoplay will never use.
        if self.player.radio_candidates:
            link = str(self.player.radio_candidates[0].get("link") or "")
            if link:
                self._trace("radio_prefetch_schedule", link=link, source="next_for_current")
                self.player.prefetcher.schedule([link])
            return
        if self.player.play_mode == 2 or self.autoplay_enabled:
            if self._schedule_related_radio_warm():
                return

        # With autoplay disabled, one search alternative is still useful for
        # immediate "."/"," navigation.
        if self.player.search_results:
            current_index = self.player.current_search_index
            if current_index < len(self.player.search_results) - 1:
                link = self.player.search_results[current_index + 1].get("link")
                if link:
                    self._trace("search_prefetch_schedule", link=link)
                    self.player.prefetcher.schedule([link])

    def handle_history_command(self, textmessage, *args):
        if args:
            self.handle_play_from_history(textmessage, *args)
        else:
            self.handle_recent_history(textmessage)

    def handle_recent_history(self, textmessage):
        history_str = self.player.get_recent_history()
        history_lines = history_str.splitlines()
        for i in range(0, len(history_lines), 4):
            chunk = "\n".join(history_lines[i:i + 4])
            self.bot.privateMessage(textmessage.nFromUserID, chunk)

    def handle_play_from_history(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return

        try:
            index = int(args[0])
            self.bot.enableVoiceTransmission(True)
            result_message = self.player.play_from_history(index)
            if "Playing" in result_message:
                user_nickname = self._nickname(textmessage.nFromUserID)
                self._send_playback_message(self._("{nickname} requested to play {title} from history").format(nickname=user_nickname, title=self.player.media_title))
                self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            else:
                self.bot.privateMessage(textmessage.nFromUserID, result_message)
        except (ValueError, IndexError):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: r <index>"))

    def handle_download_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        if self.download_in_progress:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Download already in progress. Please wait."))
            return

        link = " ".join(args) if args else self.player.current_link
        
        if not link:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: dl <youtube_link> or play a track first."))
            return

        self.bot.io_pool.submit(self._download_and_upload_task, textmessage.nFromUserID, link)

    def _download_and_upload_task(self, user_id, link):
        """Task for downloading and uploading audio, run in the thread pool."""
        self.download_in_progress = True
        self.bot.privateMessage(user_id, self._("Downloading audio. Please wait..."))
        try:
            cached_file = self.player.get_cached_media(link)
            if cached_file:
                filename = cached_file
            else:
                ydl_opts = self.player._base_ydl_opts(noplaylist=True)
                ydl_opts.update({
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'outtmpl': os.path.join("files", "%(title)s.%(ext)s"),
                    'skip_download': False,
                })
                with self.player._fresh_ydl(extra_opts=ydl_opts, noplaylist=True) as ydl:
                    info_dict = ydl.extract_info(link, download=True)
                    filename = ydl.prepare_filename(info_dict)

            user = self.bot.getUser(user_id)
            if not user:
                return
            channel_id = int(getattr(user, "nChannelID", 0) or 0)
            if not channel_id:
                return
            self.bot.doSendFile(channel_id, ttstr(filename))
            filename_only = os.path.basename(filename)
            self.bot.privateMessage(user_id, self._("File {filename} downloaded. Uploading...").format(filename=filename_only))
            
            if self.bot.bot_config['video_deletion_timer'] > 0:
                expires_at = time.time() + (self.bot.bot_config['video_deletion_timer'] * 60)
                self.bot.state_store.schedule_deletion(
                    filename, channel_id, filename_only, expires_at
                )
                self._deletion_wakeup.set()

        except Exception as e:
            self.bot.privateMessage(user_id, self._("Error downloading or uploading: {e}").format(e=str(e)))
        finally:
            self.download_in_progress = False

    def delete_uploaded_file(self, filename, channel_id):
        """Compatibility helper: perform one deletion immediately."""
        self._delete_scheduled_row({
            "local_path": filename,
            "channel_id": channel_id,
            "remote_name": os.path.basename(filename),
        })

    def get_file_id_by_name(self, channel_id, filename):
        """Gets the file ID from the TeamTalk server based on filename."""
        files = self.bot.getChannelFiles(channel_id)
        for file in files:
            if ttstr(file.szFileName) == filename:
                return file.nFileID
        return None

    def handle_queue_toggle_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        
        if args:
            arg = args[0].strip().lower()
            if arg in ("on", "1", "true", "yes"):
                self.player.queue_mode = True
            elif arg in ("off", "0", "false", "no"):
                self.player.queue_mode = False
            else:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid command. Usage: q [on|off]"))
                return
        else:
            self.player.queue_mode = not self.player.queue_mode
        
        start_pending = False
        with self.player.queue_lock:
            if not self.player.queue_mode:
                # Preserve pending items, but stale queue_index must not claim a
                # later normal-mode song. Keep ownership only while an actual
                # queue-context item is still playing.
                if not self._queue_owns_current_playback() or not self.player.is_playing:
                    self.player.queue_index = -1
                    self.player.queue_transition = False
            elif (
                self.player.queue
                and self.player.queue_index < 0
                and not self.player.is_playing
                and not self.player.queue_transition
                and not self.player.playback_end_transition
            ):
                self.player.queue_index = 0
                self.player.queue_transition = True
                start_pending = True

        self.bot.playback_config["queue_mode"] = self.player.queue_mode
        self.bot.config_handler.update_playback_settings({"queue_mode": self.player.queue_mode})
        state = self._("enabled") if self.player.queue_mode else self._("disabled")
        self.bot.privateMessage(textmessage.nFromUserID, self._("Queue system is {state}.").format(state=state))
        if start_pending:
            self._submit_playback(self._play_from_queue, 0)

    def handle_queue_list_command(self, textmessage, *args):
        total = len(self.player.queue)
        if total == 0:
            self.bot.privateMessage(textmessage.nFromUserID, self._("The queue is empty."))
            return

        # Queue storage has no application-level item limit. Listing is paged
        # only to keep TeamTalk messages and screen readers responsive.
        page_size = 50
        total_pages = max(1, (total + page_size - 1) // page_size)
        if args:
            try:
                page = int(args[0])
            except (TypeError, ValueError):
                self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: ql [page]"))
                return
        elif self.player.queue_index >= 0:
            page = self.player.queue_index // page_size + 1
        else:
            page = 1
        if page < 1 or page > total_pages:
            self.bot.privateMessage(
                textmessage.nFromUserID,
                self._("Queue page must be between 1 and {pages}.").format(pages=total_pages),
            )
            return

        start = (page - 1) * page_size
        end = min(total, start + page_size)
        lines = [
            self._("Current Queue: page {page}/{pages}, {total} item(s)").format(
                page=page, pages=total_pages, total=total
            )
        ]
        now = int(time.time())
        for offset, video in enumerate(self.player.queue[start:end], start=start):
            prefix = "-> " if offset == self.player.queue_index else f"{offset+1}. "
            added_by = str(video.get("added_by") or self._("Unknown"))
            try:
                age_seconds = max(0, now - int(video.get("added_at") or now))
            except (TypeError, ValueError):
                age_seconds = 0
            if age_seconds < 60:
                age = self._("just now")
            elif age_seconds < 3600:
                age = self._("{minutes} min ago").format(minutes=max(1, age_seconds // 60))
            elif age_seconds < 86400:
                age = self._("{hours} h ago").format(hours=max(1, age_seconds // 3600))
            else:
                age = self._("{days} d ago").format(days=max(1, age_seconds // 86400))
            detail = self._("{title} | added by {nickname} | {age}").format(
                title=video.get("title", self._("Unknown")), nickname=added_by, age=age
            )
            lines.append(prefix + detail)

        for chunk in self.bot._split_private_message("\n".join(lines)):
            self.bot.privateMessage(textmessage.nFromUserID, chunk)

    def handle_queue_check_command(self, textmessage, *args):
        if not self.player.queue:
            self.bot.privateMessage(textmessage.nFromUserID, self._("The queue is empty."))
            return
        
        msg = self._("Playing: {current} / {total}").format(
            current=self.player.queue_index + 1,
            total=len(self.player.queue)
        )
        self.bot.privateMessage(textmessage.nFromUserID, msg)

    def handle_delete_queue_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: dq <index|title>"))
            return

        selector = " ".join(args).strip()
        with self.player.queue_lock:
            idx = None
            if selector.isdigit():
                candidate = int(selector) - 1
                if 0 <= candidate < len(self.player.queue):
                    idx = candidate
            else:
                needle = selector.casefold()
                first_partial = None
                # Stream the queue instead of building two index arrays. This
                # stays bounded in Python memory even for very large queues.
                for i, item in enumerate(self.player.queue):
                    title_key = str(item.get("title", "")).casefold()
                    if title_key == needle:
                        idx = i
                        break
                    if first_partial is None and needle in title_key:
                        first_partial = i
                if idx is None:
                    idx = first_partial
            if idx is None:
                removed = None
                was_current = False
            else:
                was_current = idx == self.player.queue_index
                removed = self.player.queue.pop(idx)
                if self.player.queue_index >= 0:
                    if idx < self.player.queue_index:
                        self.player.queue_index -= 1
                    elif was_current:
                        self.player.queue_index = -1

        if removed is None:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Queue item not found."))
            return
        self.bot.privateMessage(textmessage.nFromUserID, self._("Removed from queue: {title}").format(title=removed['title']))
        if was_current:
            with self.player.queue_lock:
                has_next = self.player.queue_mode and bool(self.player.queue)
                if has_next:
                    self.player.queue_index = 0
                    self.player.queue_transition = True
            if has_next:
                self._submit_playback(self._play_from_queue, 0)
            else:
                self.loading_new_track = True
                try:
                    self.player.stop_transport()
                    self.player.current_link = None
                    self.bot.enableVoiceTransmission(False)
                finally:
                    self._finish_loading_transition()

    def handle_clear_queue_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        pending_retry = self._cancel_pending_retry()
        # cq removes queued entries only; unlike s it does not stop the audio that
        # is already playing. If that audio was a queue item it becomes detached.
        with self.player.queue_lock:
            self.player.queue.clear()
            self.player.queue_index = -1
            self.player.queue_transition = False
            self.player.queue_history = []
        if pending_retry:
            self.player.stop_transport()
            self.bot.enableVoiceTransmission(False)
        self.bot.privateMessage(textmessage.nFromUserID, self._("Queue cleared."))

    def handle_playing_info_command(self, textmessage, *args):
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing."))
            return
        
        title = self.player.media_title or self._("Unknown")
        elapsed = self.player.format_time(self.player.playback_time or 0)
        total = self.player.format_time(self.player.duration or 0)
        self.bot.privateMessage(textmessage.nFromUserID, self._("Currently playing: {title} [{elapsed}/{total}]").format(title=title, elapsed=elapsed, total=total))

    def handle_get_duration_command(self, textmessage, *args):
        if not self.player.is_playing:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing"))
            return

        elapsed_time = self.player.playback_time or 0
        total_duration = self.player.duration or 0
        remaining_time = total_duration - elapsed_time
        
        self.bot.privateMessage(textmessage.nFromUserID, 
            self._("Total duration: {total_duration}. Elapsed time: {elapsed_time}. Remaining time: {remaining_time}").format(
                total_duration=self.player.format_time(total_duration), 
                elapsed_time=self.player.format_time(elapsed_time), 
                remaining_time=self.player.format_time(remaining_time)))

    def handle_get_current_link_command(self, textmessage, *args):
        if self.player.current_link:
            self.bot.privateMessage(textmessage.nFromUserID, self.player.current_link)
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing."))

    def _play_search_result_at(self, index, user_id):
        if index < 0 or index >= len(self.player.search_results):
            return False
        video = self.player.search_results[index]
        self.loading_new_track = True
        play_error = None
        try:
            self.player.clear_collection()
            self.player.current_search_index = index
            self.player.reset_radio_history(video, video.get("source") or "youtube")
            self.player.stop_transport()
            self.player.current_link = video["link"]
            self._set_playback_context("search", video["link"], f"result:{index}")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(video["link"])
            self.bot.privateMessage(user_id, self._("Playing search result: {title}").format(title=video['title']))
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(self._("Playing: {title}").format(title=self.player.media_title)))
            self._announce_track(self.player.media_title)
        except Exception as exc:
            play_error = exc
            self.bot.privateMessage(user_id, self._("Error playing track: {error}").format(error=str(exc)))
            self._mark_sync_play_error(exc)
        finally:
            self._finish_loading_transition()
        if play_error is not None:
            self._submit_playback(self.on_playback_end)
            return False
        return True

    def _change_queue_search_selection(self, textmessage, delta, args):
        """Change the search candidate attached to one queued search item.

        Queue searches are intentionally stored on the queue entry itself.  A
        later search from another user must not overwrite the earlier user's
        result set.  With no position argument we preserve the old convenience
        behavior by targeting the newest search-backed queue item.  Supplying a
        1-based queue position (for example `. 34` or `, 34`) targets that item
        explicitly even when other users have appended more tracks afterwards.
        """
        user_id = textmessage.nFromUserID
        if len(args) > 1:
            self.bot.privateMessage(user_id, self._("Usage: . [queue_position] or , [queue_position]"))
            return

        explicit_position = None
        if args:
            try:
                explicit_position = int(str(args[0]).strip())
            except (TypeError, ValueError):
                self.bot.privateMessage(user_id, self._("Queue position must be a number."))
                return
            if explicit_position < 1:
                self.bot.privateMessage(user_id, self._("Queue position is out of range."))
                return

        with self.player.queue_lock:
            if not self.player.queue:
                self.bot.privateMessage(user_id, self._("The queue is empty."))
                return

            if explicit_position is not None:
                target_index = explicit_position - 1
                if target_index >= len(self.player.queue):
                    self.bot.privateMessage(user_id, self._("Queue position is out of range."))
                    return
            else:
                target_index = next(
                    (idx for idx in range(len(self.player.queue) - 1, -1, -1)
                     if self.player.queue[idx].get("_search_results")),
                    -1,
                )
                if target_index < 0:
                    self.bot.privateMessage(user_id, self._("No queued search item is available to change."))
                    return

            current_entry = dict(self.player.queue[target_index])
            results = current_entry.get("_search_results") or []
            if not results:
                self.bot.privateMessage(
                    user_id,
                    self._("Queue {position} was not added from a search, so it has no alternate search results.").format(
                        position=target_index + 1
                    ),
                )
                return

            try:
                current_index = int(current_entry.get("_search_index", 0) or 0)
            except (TypeError, ValueError):
                current_index = 0
            new_index = (current_index + delta) % len(results)
            video = dict(results[new_index])

            # Keep queue provenance and the private search session while replacing
            # only the selected media fields.  Dashboard snapshots never expose the
            # underscore-prefixed search metadata.
            for key in ("added_by", "added_by_user_id", "added_at", "_queue_token"):
                if key in current_entry:
                    video[key] = current_entry[key]
            video["_search_results"] = results
            video["_search_index"] = new_index
            video["_search_source"] = current_entry.get("_search_source") or video.get("source") or "youtube"
            self.player.queue[target_index] = video
            is_current = self.player.queue_index == target_index

        self.bot.privateMessage(
            user_id,
            self._("Queue {position} selection changed to: {title}").format(
                position=target_index + 1, title=video.get("title", self._("Unknown"))
            ),
        )
        if is_current:
            # Never resolve yt-dlp synchronously on the TeamTalk command thread.
            self._submit_playback(self._play_from_queue, target_index, video.get("_queue_token"), video.get("link"))

    def handle_next_search_result_selection(self, textmessage, *args):
        if self.player.queue_mode:
            self._change_queue_search_selection(textmessage, 1, args)
            return
        if args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Queue position can be used with . only while Queue Mode is enabled."))
            return
        if not self.player.search_results:
            self.bot.privateMessage(textmessage.nFromUserID, self._("No search results are available."))
            return
        target = self.player.current_search_index + 1
        if target >= len(self.player.search_results):
            self.bot.privateMessage(textmessage.nFromUserID, self._("You've reached the end of the search results."))
            return
        self._play_search_result_at(target, textmessage.nFromUserID)

    def handle_prev_search_result_selection(self, textmessage, *args):
        if self.player.queue_mode:
            self._change_queue_search_selection(textmessage, -1, args)
            return
        if args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Queue position can be used with , only while Queue Mode is enabled."))
            return
        if not self.player.search_results:
            self.bot.privateMessage(textmessage.nFromUserID, self._("No search results are available."))
            return
        target = self.player.current_search_index - 1
        if target < 0:
            self.bot.privateMessage(textmessage.nFromUserID, self._("You are at the beginning of the search results."))
            return
        self._play_search_result_at(target, textmessage.nFromUserID)

    def handle_fav_command(self, textmessage, *args):
        if not self.player.is_playing or not self.player.current_link:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Nothing is currently playing."))
            return
        
        track = {
            "title": self.player.media_title,
            "link": self.player.current_link
        }
        if track not in self.favorites:
            self.favorites.append(track)
            self.save_favorites()
            self.bot.privateMessage(textmessage.nFromUserID, self._("Added to favorites: {title}").format(title=track['title']))
        else:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Already in favorites."))

    def handle_playfav_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.favorites:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Your favorites list is empty."))
            return
        
        if self.player.queue_mode:
            queue_range = self._enqueue_queue_items(self.favorites, user_id=textmessage.nFromUserID)
            if queue_range:
                start, end, should_start = queue_range
                user_nickname = self._nickname(textmessage.nFromUserID)
                self._send_playback_message(self._("{nickname} added all favorites to queue {start}-{end}.").format(
                    nickname=user_nickname, start=start, end=end))
                self._announce_queue(
                    count=len(self.favorites), start=start, end=end,
                    collection_title=self._("Favorites"), nickname=user_nickname, collection_kind="favorites",
                )
                self._after_queue_enqueue(should_start)
        else:
            self.player.clear_collection()
            self.player.collection_results = self.favorites
            self.player.current_collection_index = 0
            self.player.collection_source = "favorites"
            self.player.clear_radio_history()
            self._play_from_queue_explicit(0, self.favorites)

    def _play_from_queue_explicit(self, index, results):
        first_video = results[index]
        play_error = None
        self.loading_new_track = True
        try:
            if self.player.is_playing:
                self.player.stop_transport()
            self.player.current_link = first_video["link"]
            self._set_playback_context("collection", first_video["link"], f"favorites:{index}")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(first_video["link"])
            self._send_playback_message(self._("Playing from favorites: {title}").format(title=self.player.media_title))
        except Exception as e:
            play_error = e
            self._send_playback_message(self._("Error playing {title}: {e}").format(title=first_video['title'], e=str(e)))
            self._mark_sync_play_error(e)
        finally:
            self._finish_loading_transition()
        if play_error is not None:
            self._submit_playback(self.on_playback_end)

    def handle_delfav_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        self.favorites = []
        self.save_favorites()
        self.bot.privateMessage(textmessage.nFromUserID, self._("Favorites list cleared."))

    def handle_3d_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        arg = args[0] if args else ""
        if arg == "on": self.player.is_stereo_wide = True
        elif arg == "off": self.player.is_stereo_wide = False
        else: self.player.is_stereo_wide = not self.player.is_stereo_wide
        self.player.update_filters()
        self.bot.config_handler.update_playback_settings({"is_stereo_wide": self.player.is_stereo_wide})
        self._send_playback_message(self._("Stereo 3D 1: {state}").format(state="ON" if self.player.is_stereo_wide else "OFF"))

    def handle_3d2_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        arg = args[0] if args else ""
        if arg == "on": self.player.is_stereo_echo = True
        elif arg == "off": self.player.is_stereo_echo = False
        else: self.player.is_stereo_echo = not self.player.is_stereo_echo
        self.player.update_filters()
        self.bot.config_handler.update_playback_settings({"is_stereo_echo": self.player.is_stereo_echo})
        self._send_playback_message(self._("Stereo 3D 2 (Extra Stereo): {state}").format(state="ON" if self.player.is_stereo_echo else "OFF"))

    def handle_bass_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        arg = args[0] if args else ""
        if arg == "on": self.player.is_bass_boosted = True
        elif arg == "off": self.player.is_bass_boosted = False
        else: self.player.is_bass_boosted = not self.player.is_bass_boosted
        self.player.update_filters()
        self.bot.config_handler.update_playback_settings({"is_bass_boosted": self.player.is_bass_boosted})
        self._send_playback_message(self._("Bass Boost: {state}").format(state="ON" if self.player.is_bass_boosted else "OFF"))

    def handle_speed_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Current speed: {speed}x").format(speed=self.player.speed))
            return
        try:
            val = float(args[0])
            self.player.speed = val
            self.player['speed'] = val
            self.bot.config_handler.update_playback_settings({"speed": val})
            self._send_playback_message(self._("Playback speed set to: {speed}x").format(speed=val))
        except:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Invalid speed value."))

    def handle_fade_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        self.player.fade_enabled = not getattr(self.player, "fade_enabled", True)
        self.bot.config_handler.update_playback_settings({"fade_enabled": self.player.fade_enabled})
        self._send_playback_message(self._("Fade effect: {state}").format(state="ON" if self.player.fade_enabled else "OFF"))

    def handle_mode_command(self, textmessage, *args):
        mode = getattr(self.player, "play_mode", 1)
        m_txt = {1: "Single", 2: "Auto/Next", 3: "Repeat"}
        self.bot.privateMessage(textmessage.nFromUserID, self._("Current mode: M{mode} - {txt}").format(mode=mode, txt=m_txt.get(mode, "")))

    def _set_play_mode(self, mode):
        self.player.play_mode = mode
        self.autoplay_enabled = mode == 2
        self.bot.playback_config["play_mode"] = mode
        self.bot.playback_config["autoplay_enabled"] = self.autoplay_enabled
        self.bot.config_handler.update_playback_settings({
            "play_mode": mode,
            "autoplay_enabled": self.autoplay_enabled,
        })

    def handle_mode1_command(self, textmessage, *args):
        self._set_play_mode(1)
        self._send_playback_message(self._("Mode set to: M1 (Single)"))

    def handle_mode2_command(self, textmessage, *args):
        self._set_play_mode(2)
        self._send_playback_message(self._("Mode set to: M2 (Auto/Next)"))
        self._prefetch_next_for_current()

    def handle_mode3_command(self, textmessage, *args):
        self._set_play_mode(3)
        self._send_playback_message(self._("Mode set to: M3 (Repeat)"))

    def _skip_queue_to_index(self, index):
        """Consume pending entries before *index* and make that item queue head.

        ``select N`` in Queue mode is a real skip-to-position operation.  Items
        before N are moved into bounded queue history, so after N finishes FIFO
        continues with N+1 instead of unexpectedly returning to item 1.
        """
        with self.player.queue_lock:
            if index < 0 or index >= len(self.player.queue):
                raise IndexError("queue index out of range")
            skipped = [dict(item) for item in self.player.queue[:index]]
            if index:
                del self.player.queue[:index]
            if skipped:
                self.player.queue_history.extend(skipped)
                if len(self.player.queue_history) > 64:
                    del self.player.queue_history[:-64]
            self.player.queue_index = 0
            self.player.queue_transition = True
            if getattr(self.player, "state_store", None) is not None:
                self.player.state_store.set_meta("queue_index", 0)
            return dict(self.player.queue[0])

    def handle_select_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        self._cancel_pending_retry(invalidate=True)
        if not args:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Usage: select <index>"))
            return
        try:
            index = int(args[0]) - 1
        except ValueError:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Index must be a number."))
            return
        # select/c is deliberately a media-position command only. Search-result
        # navigation already has its own ./, commands, so search candidates must
        # never become an implicit second meaning of select.
        if self.player.queue_mode and self.player.queue:
            results, list_type = self.player.queue, "queue"
        elif self.player.collection_results:
            results, list_type = self.player.collection_results, "collection"
        else:
            self.bot.privateMessage(
                textmessage.nFromUserID,
                self._("No queue or playlist is active. Use . and , to change search results."),
            )
            return
        if index < 0 or index >= len(results):
            self.bot.privateMessage(textmessage.nFromUserID, self._("Track index is out of range."))
            return

        # Queue has different semantics from a playlist: skipping to position N
        # consumes 1..N-1 so FIFO continuation is N+1.
        if list_type == "queue":
            try:
                item = self._skip_queue_to_index(index)
                self._send_playback_message(
                    self._("Queue {position} selection changed to: {title}").format(
                        position=index + 1, title=item.get("title", self._("Unknown"))
                    ),
                    textmessage.nFromUserID,
                )
                self._submit_playback(self._play_from_queue, 0)
            except Exception as exc:
                self.bot.privateMessage(textmessage.nFromUserID, self._("Error playing track: {error}").format(error=str(exc)))
            return

        self.loading_new_track = True
        try:
            self._set_active_index(index)
            item = results[index]
            self.player.stop_transport()
            self.player.current_link = item["link"]
            self._set_playback_context(list_type or "search", item["link"], f"select:{index}")
            self.bot.enableVoiceTransmission(True)
            self.player.play_stream(item["link"])
            self._send_playback_message(self._("Playing: {title}").format(title=self.player.media_title), textmessage.nFromUserID)
            self._announce_track(self.player.media_title)
            self._prefetch_next_for_current()
        except Exception as exc:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Error playing track: {error}").format(error=str(exc)))
        finally:
            self._finish_loading_transition()

    def handle_favorites_list_command(self, textmessage, *args):
        if not self.favorites:
            self.bot.privateMessage(textmessage.nFromUserID, self._("Your favorites list is empty."))
            return
        for index, track in enumerate(self.favorites, 1):
            self.bot.privateMessage(textmessage.nFromUserID, f"{index}. {track.get('title', 'Unknown')} - {track.get('link', '')}")

    def handle_shuffle_command(self, textmessage, *args):
        import random
        if not self._is_in_same_channel(textmessage.nFromUserID):
            return
        if not self.player.queue:
            self.bot.privateMessage(textmessage.nFromUserID, self._("The queue is empty."))
            return
        start = max(self.player.queue_index + 1, 0)
        if hasattr(self.player.queue, "shuffle_from"):
            self.player.queue.shuffle_from(start)
        else:
            pending = self.player.queue[start:]
            random.shuffle(pending)
            self.player.queue[start:] = pending
        self.bot.privateMessage(textmessage.nFromUserID, self._("The unplayed queue has been shuffled."))
        self._prefetch_next_for_current()

    def handle_hide_command(self, textmessage, *args):
        if not self._is_in_same_channel(textmessage.nFromUserID): return
        self.player.hide_status = not getattr(self.player, "hide_status", False)
        if self.player.hide_status:
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(""))
            self._send_playback_message(self._("Status hidden."))
        else:
            if self.player.is_playing:
                status = self._("Playing: {title}").format(title=self.player.media_title)
            else:
                status = self.bot.get_idle_status_message()
            self.bot.doChangeStatus(ttstr(self.bot.bot_config['gender']), ttstr(status))
            self._send_playback_message(self._("Status shown."))
