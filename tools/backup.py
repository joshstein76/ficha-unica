#!/usr/bin/env python3
"""Ficha Única backups. Usage:
  python3 tools/backup.py [--db PATH] [--media DIR] [--dest DIR] [--prune] [--verify-latest] [--offsite-cmd CMD]

Defaults: env LLAVE_DB, LLAVE_MEDIA, LLAVE_BACKUP_DIR (data/backups). Backs up the db, and media if the dir exists.
--offsite-cmd 'rclone copy {file} remote:path' runs ONLY when passed explicitly, once per new file
(shlex-split, no shell). Never runs by default.
"""
import argparse
import os
import shlex
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import backup  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description='Ficha Única backups')
    ap.add_argument('--db', default=os.environ.get('LLAVE_DB', os.path.join(ROOT, 'data', 'llave.db')))
    ap.add_argument('--media', default=os.environ.get('LLAVE_MEDIA', os.path.join(ROOT, 'data', 'media')))
    ap.add_argument('--dest', default=os.environ.get('LLAVE_BACKUP_DIR', os.path.join(ROOT, 'data', 'backups')))
    ap.add_argument('--prune', action='store_true')
    ap.add_argument('--verify-latest', action='store_true')
    ap.add_argument('--offsite-cmd', default=None)
    a = ap.parse_args(argv)
    if a.verify_latest:
        p = backup.latest(a.dest)
        ok = bool(p) and backup.verify(p)
        print('verify %s: %s' % (os.path.basename(p) if p else '-', 'OK' if ok else 'FAILED'))
        return 0 if ok else 1
    made = [backup.backup_db(a.db, a.dest)]
    if os.path.isdir(a.media):
        made.append(backup.backup_media(a.media, a.dest))
    removed = backup.prune(a.dest) if a.prune else []
    if a.offsite_cmd:
        for f in made + [made[0] + '.sha256']:
            cmd = [t.replace('{file}', f) for t in shlex.split(a.offsite_cmd)]
            subprocess.run(cmd, check=False)
    ok = backup.verify(made[0])
    print('backup %s verify=%s files=%d pruned=%d' % (os.path.basename(made[0]), 'OK' if ok else 'FAILED',
                                                       len(made), len(removed)))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
