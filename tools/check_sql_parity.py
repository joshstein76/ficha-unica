#!/usr/bin/env python3
"""Check every column in llave/schema.sql (SQLite) appears in the matching table of supabase/migrations/0001_init.sql.
Usage: python3 tools/check_sql_parity.py   (exit 1 if anything is missing)"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_MAP = {'users': 'profiles'}              # renamed on purpose
SKIP_TABLES = {'sessions'}                     # replaced by Supabase Auth
EXEMPT = {('users', 'password_hash')}          # Supabase Auth owns passwords
KEYWORDS = {'primary', 'unique', 'foreign', 'check', 'constraint'}


def split_top(body):
    parts, depth, cur = [], 0, ''
    for ch in body:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    return parts + [cur]


def table_bodies(sql, pattern):
    out = {}
    for m in re.finditer(pattern, sql, re.I):
        i, depth = m.end(), 1
        while depth and i < len(sql):
            depth += {'(': 1, ')': -1}.get(sql[i], 0)
            i += 1
        out[m.group(1)] = sql[m.end():i - 1]
    return out


def main():
    sqlite = re.sub(r'--[^\n]*', '', (ROOT / 'llave/schema.sql').read_text())
    pg = re.sub(r'--[^\n]*', '', (ROOT / 'supabase/migrations/0001_init.sql').read_text())
    src = table_bodies(sqlite, r'CREATE TABLE IF NOT EXISTS (\w+)\s*\(')
    dst = table_bodies(pg, r'create table (?:public\.)?(\w+)\s*\(')
    missing = []
    for table, body in src.items():
        if table in SKIP_TABLES:
            continue
        target = TABLE_MAP.get(table, table)
        if target not in dst:
            missing.append('table %s -> %s' % (table, target))
            continue
        for part in split_top(body):
            words = part.split()
            if not words or words[0].lower() in KEYWORDS:
                continue
            col = words[0]
            if (table, col) in EXEMPT:
                continue
            if not re.search(r'(^|\s)%s\s' % re.escape(col), dst[target]):
                missing.append('%s.%s -> %s' % (table, col, target))
    if missing:
        print('MISSING:')
        print('\n'.join('  ' + m for m in missing))
        return 1
    print('OK: %d tables checked' % (len(src) - len(SKIP_TABLES)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
