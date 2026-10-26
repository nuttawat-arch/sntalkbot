"""Replace YouTube cookie rows while retaining unrelated Netscape cookies.

This tool handles sensitive session credentials. Never log cookie values or
write them to a public issue, build log, or release note.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

HEADER = ("# Netscape HTTP Cookie File", "# HTTP Cookie File")


def youtube_domain(domain: str) -> bool:
    normalized = domain.removeprefix("#HttpOnly_").lstrip(".").lower()
    return normalized == "youtube.com" or normalized.endswith(".youtube.com")


def parse_cookie_file(content: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    lines = content.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() not in HEADER:
        raise ValueError("Expected a Netscape HTTP Cookie File header")
    records: list[tuple[str, list[str]]] = []
    comments: list[str] = []
    for raw in lines:
        if not raw or (raw.startswith("#") and not raw.startswith("#HttpOnly_")):
            comments.append(raw)
            continue
        fields = raw.split("\t")
        if len(fields) != 7:
            raise ValueError("Malformed Netscape cookie row")
        if not fields[0] or not fields[2] or not fields[5]:
            raise ValueError("Required Netscape cookie fields are missing")
        if fields[1].upper() not in {"TRUE", "FALSE"} or fields[3].upper() not in {"TRUE", "FALSE"}:
            raise ValueError("Invalid Netscape cookie flags")
        try:
            int(fields[4])
        except ValueError as exc:
            raise ValueError("Invalid Netscape cookie expiry") from exc
        records.append((raw, fields))
    return comments, records


def merge_cookie_text(default_text: str, uploaded_text: str) -> tuple[str, int, int]:
    comments, current = parse_cookie_file(default_text)
    _source_comments, uploaded = parse_cookie_file(uploaded_text)
    replacement = [raw for raw, fields in uploaded if youtube_domain(fields[0])]
    if not replacement:
        raise ValueError("Uploaded file contains no YouTube cookies")
    retained = [raw for raw, fields in current if not youtube_domain(fields[0])]
    # Keep the original file's comments, including Netscape header, and every
    # non-YouTube cookie byte-for-byte at the row level. Source file comments
    # are not imported since they can describe unrelated browser sessions.
    output = "\n".join([*comments, *retained, *replacement]).rstrip("\n") + "\n"
    parse_cookie_file(output)
    return output, len(retained), len(replacement)


def merge_file(default_path: Path, uploaded_path: Path) -> tuple[int, int]:
    default_text = default_path.read_text(encoding="utf-8-sig")
    uploaded_text = uploaded_path.read_text(encoding="utf-8-sig")
    new_text, retained, added = merge_cookie_text(default_text, uploaded_text)
    fd, staging = tempfile.mkstemp(prefix="cookie-merge-", suffix=".tmp", dir=default_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(new_text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, default_path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)
    return retained, added


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge YouTube cookies without printing session values")
    parser.add_argument("--default", type=Path, required=True)
    parser.add_argument("--uploaded", type=Path, required=True)
    args = parser.parse_args()
    retained, added = merge_file(args.default, args.uploaded)
    print(f"Cookie merge complete: {added} YouTube records imported; {retained} other records preserved")


if __name__ == "__main__":
    main()
