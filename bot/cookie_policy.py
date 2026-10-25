"""Cookie selection by published/upload time, never by cookie expiration."""
from pathlib import Path
import time


def cookie_records(path):
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
        if not lines or lines[0] not in ("# Netscape HTTP Cookie File", "# HTTP Cookie File"):
            return False
        for line in lines[1:]:
            if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
                continue
            fields = line.split("\t")
            if len(fields) != 7:
                continue
            try:
                expiry = int(fields[4])
            except ValueError:
                continue
            if expiry == 0 or expiry > time.time():
                return True
    except (OSError, UnicodeError, TypeError):
        pass
    return False


def newest_cookie(local, shared, bundled):
    candidates = []
    bundled_bytes = None
    try:
        bundled_bytes = Path(bundled).read_bytes()
    except (OSError, TypeError):
        pass
    for priority, path in enumerate((bundled, local, shared)):
        if not path or not cookie_records(path):
            continue
        try:
            p = Path(path)
            stamp = p.stat().st_mtime_ns
            # Bootstrap copies are not a newly exported session. Compare them
            # using the bundled source timestamp, not their installation time.
            if priority == 1 and bundled_bytes is not None and p.read_bytes() == bundled_bytes:
                stamp = Path(bundled).stat().st_mtime_ns
            candidates.append((stamp, priority, str(p)))
        except OSError:
            continue
    return max(candidates)[2] if candidates else None
