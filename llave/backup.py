"""Backups for Ficha Única (LLAVE): consistent SQLite snapshots, incremental media, retention, verify.

Stdlib only. The source database is only ever read (sqlite3 online backup API).
"""
import datetime
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile

DB_RE = re.compile(r'^llave-(\d{8})-(\d{6})\.db\.gz$')
MEDIA_RE = re.compile(r'^media-\d{8}.*\.tar\.gz$')
SKIP_MEDIA_DIRS = ('cards',)  # regenerable cache


def _now(now=None):
    return now or datetime.datetime.utcnow()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def backup_db(src_path, dest_dir, now=None):
    """Snapshot src_path into dest_dir/llave-YYYYmmdd-HHMMSS.db.gz (+ .sha256). Returns the .gz path."""
    now = _now(now)
    if not os.path.isfile(src_path):
        raise FileNotFoundError(src_path)
    os.makedirs(dest_dir, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix='llave-bk-', dir=dest_dir)
    try:
        tmp = os.path.join(tmpdir, 'copy.db')
        src = sqlite3.connect('file:%s?mode=ro' % src_path.replace('?', '%3f'), uri=True)
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
            dst.commit()
            res = dst.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            dst.close()
            src.close()
        if res != 'ok':
            raise RuntimeError('integrity_check failed on the copy: %s' % res)
        out = os.path.join(dest_dir, 'llave-%s.db.gz' % now.strftime('%Y%m%d-%H%M%S'))
        part = out + '.part'
        with open(tmp, 'rb') as fi, open(part, 'wb') as raw, \
                gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as fo:
            shutil.copyfileobj(fi, fo)
        os.replace(part, out)
        with open(out + '.sha256', 'w') as f:
            f.write('%s  %s\n' % (_sha256(out), os.path.basename(out)))
        return out
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def backup_media(media_dir, dest_dir, now=None):
    """tar.gz of media files changed since the last media backup (state in dest_dir/media-state.json).
    First run is full. media/cards is skipped. Returns the archive path."""
    now = _now(now)
    os.makedirs(dest_dir, exist_ok=True)
    state_path = os.path.join(dest_dir, 'media-state.json')
    last = 0.0
    try:
        with open(state_path) as f:
            last = float(json.load(f).get('last_ts', 0))
    except (OSError, ValueError):
        pass
    started = now.replace(tzinfo=datetime.timezone.utc).timestamp() if now.tzinfo is None else now.timestamp()
    files = []
    for root, dirs, names in os.walk(media_dir):
        rel_root = os.path.relpath(root, media_dir)
        if rel_root == '.':
            dirs[:] = [d for d in dirs if d not in SKIP_MEDIA_DIRS]
        for n in sorted(names):
            p = os.path.join(root, n)
            try:
                if os.path.getmtime(p) > last:
                    files.append(p)
            except OSError:
                continue
    out = os.path.join(dest_dir, 'media-%s.tar.gz' % now.strftime('%Y%m%d'))
    if os.path.exists(out):
        out = os.path.join(dest_dir, 'media-%s.tar.gz' % now.strftime('%Y%m%d-%H%M%S'))
    part = out + '.part'
    with tarfile.open(part, 'w:gz') as tar:
        for p in files:
            tar.add(p, arcname=os.path.relpath(p, media_dir), recursive=False)
    os.replace(part, out)
    with open(state_path, 'w') as f:
        json.dump({'last_ts': started, 'last_file': os.path.basename(out), 'files': len(files)}, f)
    return out


def _db_stamp(name):
    m = DB_RE.match(name)
    return datetime.datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S') if m else None


def prune(dest_dir, keep_daily=14, keep_weekly=8, now=None):
    """Keep the newest db backup of each of the last keep_daily days and last keep_weekly ISO weeks,
    always the newest overall. Only llave-*.db.gz(+.sha256) are deleted; media archives are never pruned
    (incrementals depend on each other). Returns removed paths."""
    now = _now(now)
    items = []
    for n in os.listdir(dest_dir):
        ts = _db_stamp(n)
        if ts:
            items.append((ts, n))
    items.sort(reverse=True)
    if not items:
        return []
    keep = {items[0][1]}
    today = now.date()
    days, weeks = set(), set()
    this_week = today - datetime.timedelta(days=today.weekday())
    for ts, n in items:  # newest first, so first hit per bucket is the newest
        d = ts.date()
        if 0 <= (today - d).days < keep_daily and d not in days:
            days.add(d)
            keep.add(n)
        wk = d - datetime.timedelta(days=d.weekday())
        if 0 <= (this_week - wk).days < 7 * keep_weekly and wk not in weeks:
            weeks.add(wk)
            keep.add(n)
    removed = []
    for ts, n in items:
        if n in keep:
            continue
        for f in (n, n + '.sha256'):
            p = os.path.join(dest_dir, f)
            if os.path.isfile(p):
                os.remove(p)
                removed.append(p)
    return removed


def verify(path):
    """True if the .db.gz matches its .sha256, gunzips, and passes PRAGMA integrity_check."""
    tmpdir = None
    try:
        side = path + '.sha256'
        with open(side) as f:
            want = f.read().split()[0]
        if _sha256(path) != want:
            return False
        tmpdir = tempfile.mkdtemp(prefix='llave-vf-')
        tmp = os.path.join(tmpdir, 'v.db')
        with gzip.open(path, 'rb') as fi, open(tmp, 'wb') as fo:
            shutil.copyfileobj(fi, fo)
        con = sqlite3.connect(tmp)
        try:
            return con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        finally:
            con.close()
    except Exception:
        return False
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)


def latest(dest_dir):
    """Newest llave-*.db.gz path in dest_dir, or None."""
    try:
        names = sorted(n for n in os.listdir(dest_dir) if DB_RE.match(n))
    except OSError:
        return None
    return os.path.join(dest_dir, names[-1]) if names else None


def restore_instructions():
    return (
        'RESTAURAR / RESTORE\n'
        '1. Detén el servidor / stop the server.\n'
        '2. gunzip -c data/backups/llave-AAAAMMDD-HHMMSS.db.gz > data/llave.db   '
        '(guarda antes el archivo actual / keep the current file first)\n'
        '3. python3 tools/backup.py --verify-latest   (checksum + integrity_check)\n'
        '4. Media: tar -xzf data/backups/media-*.tar.gz -C data/media  (en orden, del más viejo al más nuevo / oldest first)\n'
        '5. Arranca el servidor y revisa /healthz / start the server and check /healthz.\n'
    )
