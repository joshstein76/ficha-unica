"""Error alerts for Ficha Única: redacted, rate-limited, never raises.

report() always appends a JSON line to the rotating alert log. It only sends outbound (webhook / email)
when a channel is configured AND LLAVE_ENV == 'production'; otherwise mode is 'dry'.
"""
import datetime
import hashlib
import json
import logging
import logging.handlers
import os
import re
import shutil
import smtplib
import traceback
import urllib.request
from email.message import EmailMessage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RATE_SECONDS = 15 * 60
_CONFIG = None

SECRET_KEY = r'(?:[\w.-]*(?:password|passwd|token|secret|key|csrf|cookie|authorization)[\w.-]*)'
_KV = re.compile(r'(?i)(["\']?' + SECRET_KEY + r'["\']?\s*[=:]\s*)(?:Bearer\s+)?("[^"]*"|\'[^\']*\'|[^\s&,;}\]]+)')
_BEARER = re.compile(r'(?i)\bBearer\s+[\w.~+/=-]+')
_EMAIL = re.compile(r'([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)')
_PHONE = re.compile(r'(?<![\w.])\+?\d[\d\s().-]{5,}\d(?![\w])')


def _mask_phone(m):
    s = m.group(0)
    digits = [c for c in s if c.isdigit()]
    if len(digits) < 7:
        return s
    keep = len(digits) - 4
    seen = 0
    out = []
    for c in s:
        if c.isdigit():
            out.append('*' if seen < keep else c)
            seen += 1
        else:
            out.append(c)
    return ''.join(out)


def redact(text):
    text = str(text)
    text = _KV.sub(lambda m: m.group(1) + '[REDACTED]', text)
    text = _BEARER.sub('Bearer [REDACTED]', text)
    text = _EMAIL.sub(lambda m: '***@' + m.group(2), text)
    return _PHONE.sub(_mask_phone, text)


def configure(env=None):
    global _CONFIG
    env = os.environ if env is None else env
    log = env.get('LLAVE_ALERT_LOG') or os.path.join(ROOT, 'data', 'logs', 'errors.log')
    _CONFIG = {
        'env': env.get('LLAVE_ENV', ''),
        'webhook': env.get('LLAVE_ALERT_WEBHOOK') or None,
        'email_to': env.get('LLAVE_ALERT_EMAIL_TO') or None,
        'smtp_host': env.get('LLAVE_SMTP_HOST') or None,
        'smtp_port': int(env.get('LLAVE_SMTP_PORT') or 587),
        'smtp_user': env.get('LLAVE_SMTP_USER') or None,
        'smtp_password': env.get('LLAVE_SMTP_PASSWORD') or None,
        'smtp_from': env.get('LLAVE_SMTP_FROM') or env.get('LLAVE_SMTP_USER') or 'llave@localhost',
        'log': log,
        'state': env.get('LLAVE_ALERT_STATE') or os.path.join(os.path.dirname(log), 'alert-state.json'),
    }
    return _CONFIG


def _cfg():
    return _CONFIG or configure()


def _signature(exc_or_msg):
    if isinstance(exc_or_msg, BaseException):
        frames = traceback.extract_tb(exc_or_msg.__traceback__)
        app = [f for f in frames if os.path.abspath(f.filename).startswith(ROOT + os.sep)]
        f = (app or frames or [None])[-1]
        where = '%s:%s' % (os.path.relpath(f.filename, ROOT) if app else os.path.basename(f.filename), f.lineno) if f else '?'
        key = '%s|%s' % (type(exc_or_msg).__name__, where)
    else:
        key = 'msg|' + redact(exc_or_msg)
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]


def _iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _summary(exc_or_msg):
    if isinstance(exc_or_msg, BaseException):
        tb = ''.join(traceback.format_exception(type(exc_or_msg), exc_or_msg, exc_or_msg.__traceback__))
        text = tb
        head = '%s: %s' % (type(exc_or_msg).__name__, exc_or_msg)
    else:
        text = head = str(exc_or_msg)
    return redact(head), redact(text)[:300]


def _log_line(path, entry):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    h = logging.handlers.RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=4, encoding='utf-8')
    try:
        h.setFormatter(logging.Formatter('%(message)s'))
        h.emit(logging.LogRecord('llave.alerts', logging.ERROR, path, 0, json.dumps(entry, ensure_ascii=False), None, None))
    finally:
        h.close()


def _load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(path, state):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f)
    os.replace(tmp, path)


def _default_webhook_sender(url, payload):
    req = urllib.request.Request(url, json.dumps(payload).encode('utf-8'),
                                 {'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=10).close()


def _make_default_email_sender(c):
    def send(msg):
        with smtplib.SMTP(c['smtp_host'], c['smtp_port'], timeout=15) as s:
            if c['smtp_port'] != 25:
                s.starttls()
            if c['smtp_user']:
                s.login(c['smtp_user'], c['smtp_password'] or '')
            s.send_message(msg)
    return send


def report(exc_or_msg, context=None, sender=None, now=None):
    """Record an error. sender = {'webhook': fn(url, payload), 'email': fn(msg)} or a single webhook fn.
    Returns the alert dict (mode: dry | sent | suppressed | error). Never raises."""
    try:
        c = _cfg()
        now = now or datetime.datetime.utcnow()
        ctx = {k: redact(v) for k, v in (context or {}).items() if k in ('path', 'host', 'method')}
        title, summary = _summary(exc_or_msg)
        sig = _signature(exc_or_msg)
        alert = {'signature': sig, 'title': title[:200], 'summary': summary, 'context': ctx,
                 'count': 1, 'first_seen': _iso(now), 'last_seen': _iso(now), 'mode': 'dry', 'env': c['env']}
        channels = bool(c['webhook'] or (c['email_to'] and c['smtp_host']))
        live = channels and c['env'] == 'production'
        if live:
            st = _load_state(c['state'])
            e = st.get(sig) or {'first_seen': _iso(now), 'pending': 0, 'last_sent': None}
            e['pending'] += 1
            e['last_seen'] = _iso(now)
            alert['first_seen'] = e['first_seen']
            alert['count'] = e['pending']
            last = e.get('last_sent')
            due = last is None or (now - datetime.datetime.strptime(last, '%Y-%m-%dT%H:%M:%SZ')).total_seconds() >= RATE_SECONDS
            if not due:
                alert['mode'] = 'suppressed'
                st[sig] = e
                _save_state(c['state'], st)
            else:
                alert['mode'] = 'sent'
                e['pending'] = 0
                e['last_sent'] = _iso(now)
                st[sig] = e
                _save_state(c['state'], st)
                errs = _send(c, alert, sender)
                if errs:
                    alert['mode'] = 'error'
                    alert['send_errors'] = errs
        try:
            _log_line(c['log'], alert)
        except Exception:
            pass
        return alert
    except Exception as ex:  # never raise
        return {'mode': 'error', 'title': 'alerts.report failed', 'summary': type(ex).__name__, 'count': 1}


def _send(c, alert, sender):
    errs = []
    if isinstance(sender, dict):
        wh, em = sender.get('webhook'), sender.get('email')
    else:
        wh, em = sender, None
    if c['webhook']:
        try:
            (wh or _default_webhook_sender)(c['webhook'], alert)
        except Exception as ex:
            errs.append('webhook: %s' % type(ex).__name__)
    if c['email_to'] and c['smtp_host']:
        try:
            m = EmailMessage()
            m['Subject'] = '[Ficha Única] %s (x%d)' % (alert['title'][:120], alert['count'])
            m['From'] = c['smtp_from']
            m['To'] = c['email_to']
            m.set_content('%s\n\n%s\n\ncontext: %s\nfirst: %s  last: %s  count: %d\nsignature: %s\n' % (
                alert['title'], alert['summary'], json.dumps(alert['context']), alert['first_seen'],
                alert['last_seen'], alert['count'], alert['signature']))
            (em or _make_default_email_sender(c))(m)
        except Exception as ex:
            errs.append('email: %s' % type(ex).__name__)
    return errs


def heartbeat():
    """{ok, db_ok, disk_free_mb, last_backup_age_h} for /healthz. Never raises."""
    out = {'ok': False, 'db_ok': False, 'disk_free_mb': None, 'last_backup_age_h': None}
    try:
        from llave import db
        con = db.connect()
        try:
            out['db_ok'] = con.execute('SELECT 1').fetchone()[0] == 1
        finally:
            con.close()
        d = os.path.dirname(os.path.abspath(db.DB_PATH))
        out['disk_free_mb'] = int(shutil.disk_usage(d).free / (1024 * 1024))
    except Exception:
        pass
    try:
        from llave import backup
        bdir = os.environ.get('LLAVE_BACKUP_DIR') or os.path.join(ROOT, 'data', 'backups')
        p = backup.latest(bdir)
        if p:
            ts = backup._db_stamp(os.path.basename(p))
            out['last_backup_age_h'] = round((datetime.datetime.utcnow() - ts).total_seconds() / 3600, 1)
    except Exception:
        pass
    out['ok'] = bool(out['db_ok'])
    return out
