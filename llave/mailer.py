"""Outgoing email for Ficha Única. AGENTS ONLY: this module has no idea who a lead is and nothing here is ever addressed to a client.

Settings come from env vars (the same ones llave/alerts.py uses for error emails; production: $DATA_DIR/app.env):
  LLAVE_SMTP_HOST  LLAVE_SMTP_PORT (587 STARTTLS · 465 SSL · 25 plain)  LLAVE_SMTP_USER  LLAVE_SMTP_PASSWORD
  LLAVE_SMTP_FROM  ("hola@fichaunica.mx" or "Ficha Única <hola@fichaunica.mx>"; falls back to the user when that is an address)

send(con, to, subject, text, html=None, kind='') never raises:
  - no SMTP configured -> the message is written to the outbox as `dry_run` and nothing leaves the machine;
  - SMTP configured    -> sent, and the outbox row says `sent` or `error` (the password is never stored, printed or logged);
  - an empty subject or body (or a bad address) is REFUSED and recorded as `error`: we once sent empty emails, that is a hard rule now.
Every message is plain text + optional HTML. Tests inject the transport (`sender=` or patch `_smtp_send`) and never open a connection."""
import json
import os
import re
import smtplib
import ssl
import sys
import threading
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from . import db

TIMEOUT = 15            # seconds for connect + each SMTP step
ASYNC = True            # real SMTP from a file database runs on a worker thread (tests set False)
PRIVATE_KINDS = ('reset',)   # their body holds a private link: the outbox keeps the subject and recipient, never the text
MAX_STORED_TEXT = 4000
_ADDR = re.compile(r'^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$')
_threads = []
_threads_lock = threading.Lock()


# ---------- settings ----------
def config(env=None):
    """-> {host, port, user, password, sender}. Holds the password: never print or log this dict."""
    env = os.environ if env is None else env
    try:
        port = int((env.get('LLAVE_SMTP_PORT') or '587').strip())
    except ValueError:
        port = 587
    user = (env.get('LLAVE_SMTP_USER') or '').strip()
    sender = (env.get('LLAVE_SMTP_FROM') or '').strip() or (user if '@' in user else '')
    return {'host': (env.get('LLAVE_SMTP_HOST') or '').strip(), 'port': port, 'user': user,
            'password': env.get('LLAVE_SMTP_PASSWORD') or '', 'sender': sender}


def enabled(env=None):
    """True when there is a mail server and a valid From address. Otherwise every message is a dry run."""
    c = config(env)
    return bool(c['host'] and _ADDR.match(parseaddr(c['sender'])[1]))


def config_problems(env=None):
    """Startup hint: some SMTP variables are set but not enough to send. Empty when SMTP is simply not configured."""
    c = config(env)
    if not any((c['host'], c['user'], c['password'], c['sender'])) or enabled(env):
        return []
    out = []
    if not c['host']:
        out.append('LLAVE_SMTP_HOST is missing: emails stay dry-run')
    if not _ADDR.match(parseaddr(c['sender'])[1]):
        out.append('LLAVE_SMTP_FROM is missing or not an address: emails stay dry-run')
    return out


# ---------- sending ----------
def _smtp_send(msg, cfg):
    """The only function that opens a connection. Tests patch it (or pass `sender=`); it never logs the password."""
    ctx = ssl.create_default_context()
    smtp = (smtplib.SMTP_SSL(cfg['host'], cfg['port'], timeout=TIMEOUT, context=ctx) if cfg['port'] == 465
            else smtplib.SMTP(cfg['host'], cfg['port'], timeout=TIMEOUT))
    with smtp as s:
        if cfg['port'] not in (25, 465):
            s.starttls(context=ctx)
        if cfg['user']:
            s.login(cfg['user'], cfg['password'])
        s.send_message(msg, from_addr=parseaddr(cfg['sender'])[1])


def _scrub(text, cfg):
    t = str(text)
    for secret in (cfg.get('password'),):
        if secret:
            t = t.replace(secret, '[REDACTED]')
    return t


def _refusal(to, subject, text):
    """Spanish-free internal reason (it only goes to the outbox) or ''."""
    if not _ADDR.match(to):
        return 'destinatario no válido'
    if not subject:
        return 'asunto vacío'
    if '\n' in subject or '\r' in subject:
        return 'asunto con saltos de línea'
    if not text:
        return 'cuerpo vacío'
    return ''


def _record(con, kind, ref, payload, status, response=None, attempts=0):
    cur = con.execute('INSERT INTO outbox(kind, ref, payload, status, response, attempts) VALUES (?,?,?,?,?,?)',
                      ('email.' + (kind or 'mensaje'), ref, json.dumps(payload, ensure_ascii=False), status, response, attempts))
    con.commit()
    return cur.lastrowid


def build_message(cfg, to, subject, text, html=None):
    msg = EmailMessage()
    msg['Subject'] = subject
    name, addr = parseaddr(cfg['sender'])
    msg['From'] = formataddr((name or db.BRAND, addr))
    msg['To'] = to
    msg['Date'] = formatdate(localtime=False)
    msg['Message-ID'] = make_msgid(domain=addr.split('@')[-1])
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype='html')
    return msg


def send(con, to, subject, text, html=None, kind='', ref=None, sender=None):
    """-> {'ok': bool, 'status': 'sent' | 'dry_run' | 'error' | 'refused', 'delivered': bool, 'id': outbox id | None}. Never raises."""
    cfg = {'password': ''}
    try:
        cfg = config()
        to = (to or '').strip()
        subject = re.sub(r'[ \t]{2,}', ' ', (subject or '').strip())   # CR / LF stay so _refusal can reject a header-injection attempt
        text = (text or '').strip()
        html = (html or '').strip() or None
        payload = {'to': to, 'subject': subject, 'kind': kind or 'mensaje'}
        if kind not in PRIVATE_KINDS:
            payload['text'] = text[:MAX_STORED_TEXT]
        if html:
            payload['html_chars'] = len(html)
        bad = _refusal(to, subject, text)
        if bad:  # nothing is sent, and the row says why
            rid = _record(con, kind, ref, payload, 'error', 'rechazado: ' + bad)
            return {'ok': False, 'status': 'refused', 'delivered': False, 'id': rid}
        if not enabled():
            rid = _record(con, kind, ref, payload, 'dry_run', 'sin SMTP configurado: no se envió')
            return {'ok': True, 'status': 'dry_run', 'delivered': False, 'id': rid}
        msg = build_message(cfg, to, subject, text, html)
        try:
            (sender or _smtp_send)(msg, cfg)
        except Exception as ex:  # SMTP down, bad login, refused recipient...: recorded, never raised, never with the password
            reason = '%s: %s' % (type(ex).__name__, _scrub(ex, cfg)[:300])
            rid = _record(con, kind, ref, payload, 'error', reason, attempts=1)
            return {'ok': False, 'status': 'error', 'delivered': False, 'id': rid}
        rid = _record(con, kind, ref, payload, 'sent', msg['Message-ID'], attempts=1)
        return {'ok': True, 'status': 'sent', 'delivered': True, 'id': rid}
    except Exception as ex:  # even the bookkeeping failed (closed database...): the caller's request must go on
        sys.stderr.write('[llave] mailer: %s: %s\n' % (type(ex).__name__, _scrub(ex, cfg)[:200]))
        return {'ok': False, 'status': 'error', 'delivered': False, 'id': None}


# ---------- off the request thread ----------
def _db_file(con):
    try:
        for _seq, name, path in con.execute('PRAGMA database_list').fetchall():
            if name == 'main':
                return path or ''
    except Exception:
        pass
    return ''


def _run_items(path, items):
    c = None
    try:
        c = db.connect(path)
        for it in items:
            send(c, **it)
    except Exception as ex:
        sys.stderr.write('[llave] mailer worker: %s\n' % type(ex).__name__)
    finally:
        if c is not None:
            c.close()


def dispatch(con, items):
    """Send several messages (dicts of send() arguments). With real SMTP and a file database they go out on a worker thread with its
    own connection, so a slow or dead mail server never holds up a web request; otherwise (dry run, tests, memory db) they go inline."""
    items = [i for i in items if i]
    if not items:
        return
    path = _db_file(con)
    if ASYNC and enabled() and path:
        t = threading.Thread(target=_run_items, args=(path, items), daemon=True)
        with _threads_lock:
            _threads[:] = [x for x in _threads if x.is_alive()] + [t]
        t.start()
        return
    for it in items:
        send(con, **it)


def wait(timeout=10):
    """Join the worker threads (tests, shutdown)."""
    with _threads_lock:
        pending = list(_threads)
    for t in pending:
        t.join(timeout)
