"""Netscape cookie merge must keep unrelated domains and never corrupt defaults."""

from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cookie_merge", ROOT / "tools/merge_default_youtube_cookies.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

HEADER = "# Netscape HTTP Cookie File\n"


def record(domain: str, name: str, value: str) -> str:
    return f"{domain}\tTRUE\t/\tTRUE\t0\t{name}\t{value}"


class CookieMergeTests(unittest.TestCase):
    def test_youtube_only_replacement_preserves_other_domains_and_comments(self):
        original = HEADER + "# kept comment\n" + "\n".join([
            record(".youtube.com", "SID", "old"),
            record(".example.net", "KEEP", "untouched"),
            record("#HttpOnly_.youtube.com", "YSC", "stale"),
        ]) + "\n"
        incoming = HEADER + "\n".join([
            record(".youtube.com", "SID", "fresh"),
            record("#HttpOnly_.youtube.com", "YSC", "fresh2"),
            record(".other.example", "NOIMPORT", "forbidden"),
        ]) + "\n"
        merged, retained, imported = MODULE.merge_cookie_text(original, incoming)
        self.assertEqual((retained, imported), (1, 2))
        self.assertIn(record(".example.net", "KEEP", "untouched"), merged)
        self.assertIn(record(".youtube.com", "SID", "fresh"), merged)
        self.assertIn("# kept comment", merged)
        self.assertNotIn("\told\n", merged)
        self.assertNotIn("\tstale\n", merged)
        self.assertNotIn("NOIMPORT", merged)

    def test_reject_invalid_or_wrong_site_without_modifying_default(self):
        with TemporaryDirectory() as temporary:
            default = Path(temporary) / "default.txt"
            incoming = Path(temporary) / "new.txt"
            default.write_text(HEADER + record(".example.org", "KEEP", "value") + "\n", encoding="utf-8")
            incoming.write_text(HEADER + record(".other.example", "OTHER", "value") + "\n", encoding="utf-8")
            before = default.read_bytes()
            with self.assertRaisesRegex(ValueError, "no YouTube"):
                MODULE.merge_file(default, incoming)
            self.assertEqual(default.read_bytes(), before)
            incoming.write_text("not netscape\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Netscape"):
                MODULE.merge_file(default, incoming)
            self.assertEqual(default.read_bytes(), before)

    def test_write_uses_atomic_replacement_and_restrictive_permissions(self):
        with TemporaryDirectory() as temporary:
            default = Path(temporary) / "default.txt"
            incoming = Path(temporary) / "new.txt"
            default.write_text(HEADER + record(".example.org", "KEEP", "value") + "\n", encoding="utf-8")
            incoming.write_text(HEADER + record(".youtube.com", "SID", "updated") + "\n", encoding="utf-8")
            self.assertEqual(MODULE.merge_file(default, incoming), (1, 1))
            self.assertIn("updated", default.read_text(encoding="utf-8"))
            self.assertEqual(default.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
