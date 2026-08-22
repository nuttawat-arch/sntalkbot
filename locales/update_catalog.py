#!/usr/bin/env python3
"""Update messages.pot and locale PO catalogs from literal self._("...") calls.

This tool uses only Python's standard library. Existing translations are preserved;
new strings are added with an empty msgstr so translators can fill them in.
"""
from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from pathlib import Path

from compile_locales import read_po


def quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def extract(root: Path):
    refs = defaultdict(list)
    files = [root / "main.py"] + sorted((root / "bot").rglob("*.py"))
    for path in files:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "_":
                continue
            arg = node.args[0]
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str) or not arg.value:
                continue
            rel = path.relative_to(root).as_posix()
            refs[arg.value].append(f"{rel}:{getattr(node, 'lineno', 1)}")
    return dict(sorted(refs.items()))


def write_po(path: Path, messages, translations, language=None, template=False):
    lines = []
    if template:
        lines.extend([
            '# SNTalkBot gettext template',
            'msgid ""',
            'msgstr ""',
            '"Project-Id-Version: SNTalkBot 2026\\n"',
            '"MIME-Version: 1.0\\n"',
            '"Content-Type: text/plain; charset=UTF-8\\n"',
            '"Content-Transfer-Encoding: 8bit\\n"',
            '',
        ])
    else:
        header = (
            "Project-Id-Version: SNTalkBot 2026\n"
            f"Language: {language or ''}\n"
            "MIME-Version: 1.0\n"
            "Content-Type: text/plain; charset=UTF-8\n"
            "Content-Transfer-Encoding: 8bit\n"
            "Plural-Forms: nplurals=1; plural=0;\n"
        )
        lines.extend([
            f'# {language or "Locale"} translation for SNTalkBot',
            '# Update msgstr values, then run: python locales/compile_locales.py',
            'msgid ""',
            f'msgstr {quote(header)}',
            '',
        ])
    for msgid, refs in messages.items():
        lines.append('#: ' + ' '.join(refs))
        lines.append('msgid ' + quote(msgid))
        lines.append('msgstr ' + (quote("") if template else quote(translations.get(msgid, ""))))
        lines.append('')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--locale', action='append', help='Locale code to update, e.g. th. May be repeated.')
    args = parser.parse_args()
    locales_dir = Path(__file__).resolve().parent
    root = locales_dir.parent
    messages = extract(root)
    write_po(locales_dir / 'messages.pot', messages, {}, template=True)
    locales = args.locale or []
    for locale in locales:
        po = locales_dir / locale / 'LC_MESSAGES' / 'messages.po'
        existing = read_po(po) if po.exists() else {}
        existing.pop('', None)
        write_po(po, messages, existing, language=locale)
        untranslated = sum(1 for msgid in messages if not existing.get(msgid))
        print(f'Updated {locale}: {len(messages)} messages; {untranslated} untranslated')
    print(f'Updated messages.pot: {len(messages)} messages')


if __name__ == '__main__':
    main()
