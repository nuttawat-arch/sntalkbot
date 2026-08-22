from queue import Empty, Queue
from threading import Event, Lock, Thread


class LinkPrefetcher:
    """Small bounded prefetch worker adapted from TTMediaBot's worker model.

    It deduplicates URLs and keeps yt-dlp extraction off the TeamTalk event thread.
    """
    def __init__(self, fetch_callback, max_pending=5):
        self.fetch_callback = fetch_callback
        self.max_pending = max(1, int(max_pending))
        self._queue = Queue()
        self._stop = Event()
        self._lock = Lock()
        self._queued = set()
        self._worker = Thread(target=self._run, daemon=True, name="TTBot_Prefetch")
        self._worker.start()

    def schedule(self, links):
        added = 0
        for link in links:
            if not link or added >= self.max_pending:
                break
            with self._lock:
                if link in self._queued:
                    continue
                self._queued.add(link)
            self._queue.put(link)
            added += 1

    def clear(self):
        while True:
            try:
                link = self._queue.get_nowait()
                with self._lock:
                    self._queued.discard(link)
                self._queue.task_done()
            except Empty:
                break

    def _run(self):
        while not self._stop.is_set():
            link = self._queue.get()
            try:
                if link is None:
                    return
                try:
                    self.fetch_callback(link)
                except Exception:
                    pass
            finally:
                if link is not None:
                    with self._lock:
                        self._queued.discard(link)
                self._queue.task_done()

    def close(self):
        self._stop.set()
        self._queue.put(None)
        self._worker.join(timeout=1.5)
