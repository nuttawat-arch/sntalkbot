#!/usr/bin/env python3
"""Compile gettext .po files to .mo using only the Python standard library."""
from __future__ import annotations

import ast
import struct
from pathlib import Path


def _q(text: str) -> str:
    return ast.literal_eval(text)


def read_po(path: Path):
    messages = {}
    msgid = None
    msgstr = None
    mode = None

    def commit():
        nonlocal msgid, msgstr, mode
        if msgid is not None:
            messages[msgid] = msgstr or ""
        msgid = msgstr = mode = None

    for raw in path.read_text(encoding="utf-8-sig").splitlines() + [""]:
        line = raw.strip()
        if line.startswith("msgid "):
            commit()
            msgid = _q(line[6:].strip())
            msgstr = ""
            mode = "id"
        elif line.startswith("msgstr "):
            msgstr = _q(line[7:].strip())
            mode = "str"
        elif line.startswith('"'):
            if mode == "id":
                msgid = (msgid or "") + _q(line)
            elif mode == "str":
                msgstr = (msgstr or "") + _q(line)
        elif not line:
            commit()
    return messages


def write_mo(messages, output: Path):
    # GNU MO format, little endian, revision 0.
    items = sorted((k, v) for k, v in messages.items() if v is not None)
    ids = b""
    strs = b""
    id_offsets = []
    str_offsets = []
    for msgid, msgstr in items:
        ib = msgid.encode("utf-8")
        sb = msgstr.encode("utf-8")
        id_offsets.append((len(ib), len(ids)))
        str_offsets.append((len(sb), len(strs)))
        ids += ib + b"\0"
        strs += sb + b"\0"

    n = len(items)
    header_size = 7 * 4
    orig_table = header_size
    trans_table = orig_table + n * 8
    ids_offset = trans_table + n * 8
    strs_offset = ids_offset + len(ids)

    out = bytearray()
    out += struct.pack("<7I", 0x950412DE, 0, n, orig_table, trans_table, 0, 0)
    for length, offset in id_offsets:
        out += struct.pack("<2I", length, ids_offset + offset)
    for length, offset in str_offsets:
        out += struct.pack("<2I", length, strs_offset + offset)
    out += ids
    out += strs
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(out)


def main():
    root = Path(__file__).resolve().parent
    po_files = sorted(root.glob("*/LC_MESSAGES/messages.po"))
    if not po_files:
        raise SystemExit("No locale .po files found")
    failed = False
    for po in po_files:
        try:
            messages = read_po(po)
            mo = po.with_suffix(".mo")
            write_mo(messages, mo)
            print(f"Compiled {po.relative_to(root)} -> {mo.name} ({len(messages)} messages)")
        except Exception as exc:
            failed = True
            print(f"ERROR {po}: {exc}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
