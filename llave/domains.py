"""Own domain (Pro plan): input cleanup, the DNS check, the state the panel and the router read, certificate warm-up.

Flow: the agent types micasa.mx in Mi sitio -> `claim` stores it (pending) -> the agent points www.micasa.mx (and,
optionally, micasa.mx) to us at their registrar -> "Verificar ahora" or the cron tool (tools/domain_check_run.py) calls
`check`, which resolves the names with the system resolver and, when www resolves ONLY to our IP, sets domain_verified_at
-> Caddy then asks /_tls/ask and issues the certificate on first use; we visit the domain once ourselves (`warm_tls`)
so no real visitor waits for it -> the router serves www.micasa.mx, sends micasa.mx to www, and sends the free address
to the own domain (db.own_domain_live). If a verified domain stops resolving for FAIL_LIMIT cron checks in a row it is
unverified and the site goes back to the free address; nothing is deleted and it comes back by itself when DNS is right.

The resolver is injected everywhere (`resolver(host) -> list of IPv4 strings | [] (no record) | None (could not tell)`),
so tests never touch the network. Nothing in this module sends email: notices to the agent live in the panel only.
"""
import datetime
import ipaddress
import json
import os
import re
import socket
import sqlite3
import ssl
import time
import urllib.parse

from . import db

FAIL_LIMIT = 3     # consecutive failed cron checks before a verified domain is unverified
CLAIM_DAYS = 14    # an unverified claim older than this can be taken by another agency
OWN_BRAND_DOMAINS = ('fichaunica.mx', 'fichaunica.com', 'fichaunica.com.mx')   # never an agent's own domain (BASE_DOMAIN and LLAVE_OWN_DOMAINS are added)
RESERVED_TLDS = {'localhost', 'local', 'test', 'invalid', 'example', 'internal', 'lan', 'home', 'corp', 'intranet', 'arpa', 'onion'}
PUBLIC_SUFFIXES = {'com.mx', 'org.mx', 'net.mx', 'gob.mx', 'edu.mx', 'co.uk', 'org.uk', 'com.br', 'com.ar', 'com.co', 'com.pe',
                   'com.es', 'co.nz', 'com.au'}   # not a domain on their own: the name before them is missing

MSG_INVALID = 'Ese dominio no parece válido. Escríbelo así: micasa.mx'
MSG_OWN = 'Ese dominio es de Ficha Única. Escribe el dominio que compraste tú (por ejemplo micasa.mx).'
MSG_SUFFIX = 'Falta el nombre de tu dominio (por ejemplo micasa.com.mx).'
MSG_TAKEN = 'Ese dominio ya está conectado a otra cuenta de Ficha Única. Si es tuyo, escríbenos por WhatsApp y lo resolvemos.'

_SCHEME = re.compile(r'^[a-z][a-z0-9+.\-]*://')
_LABEL = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')
_TLD = re.compile(r'^(?:[a-z]{2,24}|xn--[a-z0-9-]{2,59})$')
_DEFINITE_FAIL = ('sin_registro', 'otra', 'mixto')   # answers that count as a failed check (a resolver that could not answer never does)


# ---------------------------------------------------------------- config (read at call time: env can change under tests and on the server)
def public_ips():
    """IPv4 addresses agents point their domain to (LLAVE_PUBLIC_IP, comma separated). Empty = not configured."""
    out = []
    for tok in re.split(r'[,\s]+', os.environ.get('LLAVE_PUBLIC_IP', '').strip()):
        try:
            ip = ipaddress.ip_address(tok)
        except ValueError:
            continue
        if ip.version == 4 and str(ip) not in out:
            out.append(str(ip))
    return out


def cname_target():
    """The name agents point www to with a CNAME (LLAVE_CNAME_TARGET; default sites.<brand domain>, which the wildcard DNS record resolves)."""
    t = (os.environ.get('LLAVE_CNAME_TARGET') or '').strip().lower().rstrip('.')
    return t or 'sites.' + db.BASE_DOMAIN


def own_domains():
    out = set(OWN_BRAND_DOMAINS) | {db.BASE_DOMAIN.lower()}
    for tok in re.split(r'[,;\s]+', os.environ.get('LLAVE_OWN_DOMAINS', '')):
        if tok.strip():
            out.add(tok.strip().lower().rstrip('.'))
    host = (urllib.parse.urlsplit(db.MARKETING_URL).hostname or '') if db.MARKETING_URL else ''
    if host:
        out.add(host[4:] if host.startswith('www.') else host)
    return out


# ---------------------------------------------------------------- input
def normalize(raw):
    """What the agent typed -> bare domain: no scheme, path, port, credentials or www. '' for a blank input (= remove the domain).
    Raises ValueError (Spanish message) when it is not a usable domain name or it is one of ours."""
    s = (raw or '').strip().lower()
    if not s:
        return ''
    if re.search(r'\s', s):
        raise ValueError(MSG_INVALID)
    s = _SCHEME.sub('', s)
    s = re.split(r'[/?#\\]', s, maxsplit=1)[0]
    s = s.rsplit('@', 1)[-1]
    s = re.sub(r':\d*$', '', s).strip('.')
    while s.startswith('www.'):
        s = s[4:]
    if not s:
        raise ValueError(MSG_INVALID)
    if not s.isascii():  # méxico.mx -> xn--mxico-... (what DNS and certificates use)
        try:
            s = s.encode('idna').decode('ascii')
        except UnicodeError:
            raise ValueError(MSG_INVALID)
    labels = s.split('.')
    if len(s) > 253 or len(labels) < 2 or not all(_LABEL.match(x) for x in labels) or not _TLD.match(labels[-1]):
        raise ValueError(MSG_INVALID)
    if any(s == o or s.endswith('.' + o) for o in own_domains()):
        raise ValueError(MSG_OWN)
    if labels[-1] in RESERVED_TLDS:
        raise ValueError(MSG_INVALID)
    if s in PUBLIC_SUFFIXES:
        raise ValueError(MSG_SUFFIX)
    return s


# ---------------------------------------------------------------- time helpers (UTC, same text format as SQLite datetime('now'))
def _now(now=None):
    return now or datetime.datetime.utcnow()


def _stamp(now=None):
    return _now(now).strftime('%Y-%m-%d %H:%M:%S')


def _parse(ts):
    try:
        return datetime.datetime.strptime((ts or '')[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def ago_es(ts, now=None):
    t = _parse(ts)
    if not t:
        return ''
    secs = max(0, (_now(now) - t).total_seconds())
    if secs < 90:
        return 'hace un momento'
    if secs < 3600:
        return 'hace %d min' % (secs // 60)
    if secs < 86400:
        return 'hace %d h' % (secs // 3600)
    return 'hace %d día%s' % (secs // 86400, '' if secs // 86400 == 1 else 's')


# ---------------------------------------------------------------- state
def state_of(agency):
    """none | pendiente | verificado | problema (a verified domain stopped resolving and was taken off)."""
    a = dict(agency)
    if not a.get('custom_domain'):
        return 'none'
    if a.get('domain_verified_at'):
        return 'verificado'
    return 'problema' if a.get('domain_lost_at') else 'pendiente'


def lost_notice(agency):
    """True while the panel must tell the agent their domain stopped working (until it verifies again or is removed)."""
    a = dict(agency)
    return state_of(a) == 'problema' and db.plan_has(a, 'domain')


def _load(text):
    try:
        out = json.loads(text) if text else {}
    except ValueError:
        out = {}
    return out if isinstance(out, dict) else {}


def status(agency, now=None):
    """Everything the Mi sitio card shows, from the agency row (no network)."""
    a = dict(agency)
    d = a.get('custom_domain') or ''
    return {'domain': d, 'www': db.own_domain_host(d) if d else '', 'state': state_of(a), 'plan_ok': db.plan_has(a, 'domain'),
            'detail': _load(a.get('domain_check')), 'checked_at': a.get('domain_checked_at'), 'lost_at': a.get('domain_lost_at'),
            'tls': a.get('domain_tls'), 'cname': cname_target(), 'ips': public_ips(),
            'free_url': db.origin(a['slug']) if a.get('slug') else '', 'own_url': ('https://' + db.own_domain_host(d)) if d else ''}


def agency_for_host(con, host):
    """The agency whose VERIFIED own domain `host` is, in its www or bare form -> (row, 'www' | 'apex'), else (None, None).
    The router and /_tls/ask both go through here, so the certificate rule and the serving rule can never disagree."""
    h = (host or '').strip().lower().rstrip('.')
    if not h:
        return None, None
    kind, d = ('www', h[4:]) if h.startswith('www.') else ('apex', h)
    row = con.execute('SELECT * FROM agencies WHERE custom_domain=? AND domain_verified_at IS NOT NULL', (d,)).fetchone()
    return (row, kind) if row else (None, None)


# ---------------------------------------------------------------- claim / release
_CLEAR = ("custom_domain=NULL, domain_verified_at=NULL, domain_claimed_at=NULL, domain_checked_at=NULL, domain_check=NULL, "
          "domain_fail_count=0, domain_lost_at=NULL, domain_tls=NULL")


def _claim_expired(claimed_at, ts):
    t, now = _parse(claimed_at), _parse(ts)
    return t is None or (now - t).days >= CLAIM_DAYS


def claim(con, agency, raw, now=None, actor=None):
    """Save (or remove, when blank) the agency's own domain. Returns the stored domain or None. Raises ValueError (Spanish).
    One agency per domain: a verified domain, or an unverified claim younger than CLAIM_DAYS, belongs to its holder.
    Saving the domain the agency already has changes nothing (it stays verified)."""
    aid = agency['id']
    actor = actor or 'agency:%d' % aid
    d = normalize(raw)
    cur = agency['custom_domain']
    if not d:
        if cur:
            con.execute('UPDATE agencies SET %s WHERE id=?' % _CLEAR, (aid,))
            db.audit(con, actor, 'domain_removed', cur)
            con.commit()
        return None
    if d == cur:
        return d
    ts = _stamp(now)
    other = con.execute('SELECT id, domain_verified_at, domain_claimed_at FROM agencies WHERE custom_domain=? AND id!=?', (d, aid)).fetchone()
    if other:
        if other['domain_verified_at'] or not _claim_expired(other['domain_claimed_at'], ts):
            raise ValueError(MSG_TAKEN)
        con.execute('UPDATE agencies SET %s WHERE id=?' % _CLEAR, (other['id'],))
        db.audit(con, actor, 'domain_claim_lapsed', '%s taken from agency:%d (never verified, claim older than %d days)' % (d, other['id'], CLAIM_DAYS))
    try:
        con.execute("UPDATE agencies SET custom_domain=?, domain_verified_at=NULL, domain_claimed_at=?, domain_checked_at=NULL, "
                    "domain_check=NULL, domain_fail_count=0, domain_lost_at=NULL, domain_tls=NULL WHERE id=?", (d, ts, aid))
    except sqlite3.IntegrityError:  # two agencies saved the same name at the same moment
        con.rollback()
        raise ValueError(MSG_TAKEN)
    db.audit(con, actor, 'domain_claimed', '%s (was %s)' % (d, cur or '-'))
    con.commit()
    return d


# ---------------------------------------------------------------- DNS
_NO_ANSWER = {x for x in (getattr(socket, 'EAI_NONAME', None), getattr(socket, 'EAI_NODATA', None)) if x is not None}


def system_resolver(host):
    """The standard library resolver, IPv4 only. [] = the name has no address (does not exist); None = the lookup itself failed
    (resolver down, timeout): that must never count against an agent's domain."""
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror as ex:
        return [] if ex.errno in _NO_ANSWER else None
    except (UnicodeError, OSError):
        return None
    return sorted({i[4][0] for i in infos})


def _lookup(resolver, host):
    try:
        out = resolver(host)
    except Exception:  # a resolver may raise instead of answering; either way we could not tell
        return None
    if out is None:
        return None
    if isinstance(out, str):
        out = [out]
    return sorted({str(x) for x in out})


def classify(ips, ours):
    """ok (only our addresses) · mixto (ours + others) · otra (none of ours) · sin_registro (no address) · desconocido (could not tell)."""
    if ips is None:
        return 'desconocido'
    if not ips:
        return 'sin_registro'
    if not ours:
        return 'desconocido'
    ips = set(ips)
    if ips <= ours:
        return 'ok'
    return 'mixto' if ips & ours else 'otra'


# ---------------------------------------------------------------- certificate warm-up
def warm_tls(names, ip=None, timeout=30):
    """Open a TLS connection to our own server with each name as SNI. Caddy sees an unknown host, asks /_tls/ask (the domain is verified
    by now), obtains the certificate and answers the handshake, so the next real visitor finds it ready. The default context also
    checks chain and name, so True means a valid certificate is installed. Returns {name: bool}."""
    ip = ip or (public_ips() or [''])[0]
    out = {}
    for n in names:
        try:
            with socket.create_connection((ip, 443), timeout=timeout) as raw:
                with ssl.create_default_context().wrap_socket(raw, server_hostname=n):
                    out[n] = True
        except (OSError, ssl.SSLError, ValueError):
            out[n] = False
    return out


def default_warm():
    """The real warm-up, only in production with LLAVE_PUBLIC_IP set (a local or test run never opens a connection). LLAVE_DOMAIN_WARM=0 turns it off."""
    if db.ENV == 'production' and public_ips() and os.environ.get('LLAVE_DOMAIN_WARM', '1') != '0':
        return warm_tls
    return None


def _wanted(domain, detail):
    return [db.own_domain_host(domain)] + ([domain] if detail.get('apex') == 'ok' else [])


def _warm(con, aid, domain, detail, warm):
    """Get certificates for the names that have none yet. domain_tls follows the www name only (it is the one that matters: the free
    address redirects once it is 'ok'); the bare name is best effort and is retried by cron while it points to us."""
    wanted = _wanted(domain, detail)
    done = [n for n in detail.get('warmed', []) if n in wanted]
    todo = [n for n in wanted if n not in done]
    if todo:
        try:
            res = warm(todo) or {}
        except Exception:
            res = {}
        done += [n for n in todo if res.get(n)]
    con.execute('UPDATE agencies SET domain_tls=?, domain_check=? WHERE id=?',
                ('ok' if db.own_domain_host(domain) in done else 'espera', json.dumps(dict(detail, warmed=done)), aid))
    con.commit()


def warm_agency(con, agency_id, warm=None):
    """Warm-up for one agency on its own connection (the 'Verificar ahora' button starts this in a thread)."""
    row = con.execute('SELECT * FROM agencies WHERE id=?', (agency_id,)).fetchone()
    warm = warm or default_warm()
    if not row or not warm or not row['custom_domain'] or not row['domain_verified_at'] or not db.plan_has(row, 'domain'):
        return
    _warm(con, row['id'], row['custom_domain'], _load(row['domain_check']), warm)


# ---------------------------------------------------------------- the check
def check(con, agency, resolver=None, source='cron', now=None, warm=None, actor=None):
    """One DNS check of one agency's domain. Returns {state, event, www, apex, fail_count}; event is 'verified', 'lost' or None.
    source='cron' (tools/domain_check_run.py) is the only one whose failures count towards unverifying a verified domain;
    'boton' (Verificar ahora) can verify but never takes a domain off. warm: None = real warm-up when configured, False = skip,
    or a callable(names) -> {name: bool}."""
    row = con.execute('SELECT * FROM agencies WHERE id=?', (agency['id'],)).fetchone()
    d = row['custom_domain'] if row else None
    if not d:
        return {'state': 'none', 'event': None, 'www': None, 'apex': None, 'fail_count': 0}
    actor = actor or ('cron' if source == 'cron' else 'agency:%d' % row['id'])
    ts = _stamp(now)
    resolver = resolver or system_resolver
    www_ips, apex_ips = _lookup(resolver, db.own_domain_host(d)), _lookup(resolver, d)
    ours = set(public_ips())
    if not ours:  # LLAVE_PUBLIC_IP not set: the CNAME target (wildcard DNS) tells us where we are
        ours = set(_lookup(resolver, cname_target()) or [])
    www_c, apex_c = classify(www_ips, ours), classify(apex_ips, ours)
    detail = {'www': www_c, 'www_ips': www_ips or [], 'apex': apex_c, 'apex_ips': apex_ips or [], 'configured': bool(ours),
              'warmed': _load(row['domain_check']).get('warmed', [])}
    sets = {'domain_checked_at': ts}
    verified = bool(row['domain_verified_at'])
    fail = int(row['domain_fail_count'] or 0)
    event = None
    if www_c == 'ok':
        fail = 0
        if not verified:
            sets.update(domain_verified_at=ts, domain_lost_at=None)
            if callable(warm) or default_warm():  # a certificate is about to be requested: the free address keeps serving until it exists
                sets['domain_tls'] = 'espera'
            verified, event = True, 'verified'
            db.audit(con, actor, 'domain_verified', '%s via %s' % (d, source))
    elif www_c in _DEFINITE_FAIL and verified and source == 'cron':
        fail += 1
        if fail >= FAIL_LIMIT:
            sets.update(domain_verified_at=None, domain_lost_at=ts, domain_claimed_at=ts, domain_tls=None)
            detail['warmed'] = []
            fail, verified, event = 0, False, 'lost'
            db.audit(con, actor, 'domain_lost', '%s stopped resolving to us (%d checks in a row); back to the free address' % (d, FAIL_LIMIT))
    sets['domain_fail_count'] = fail
    sets['domain_check'] = json.dumps(detail)
    con.execute('UPDATE agencies SET %s WHERE id=?' % ', '.join('%s=?' % k for k in sets), tuple(sets.values()) + (row['id'],))
    con.commit()
    if verified and www_c == 'ok' and db.plan_has(row, 'domain') and warm is not False:
        warm = warm or default_warm()  # after the commit: Caddy's /_tls/ask must already see the domain as verified
        if warm:
            _warm(con, row['id'], d, detail, warm)
    lost_at = sets['domain_lost_at'] if 'domain_lost_at' in sets else row['domain_lost_at']
    state = 'verificado' if verified else ('problema' if lost_at else 'pendiente')
    return {'state': state, 'event': event, 'www': www_c, 'apex': apex_c, 'fail_count': fail}


def run_all(con, resolver=None, now=None, warm=None, budget_s=240, clock=time.monotonic):
    """Check every agency whose plan includes an own domain, least recently checked first, and stop after budget_s so runs never pile up.
    Returns a summary {checked, verificados, perdidos, ok, pendientes, sin_plan, sin_tiempo}."""
    out = {'checked': 0, 'verificados': 0, 'perdidos': 0, 'ok': 0, 'pendientes': 0, 'sin_plan': 0, 'sin_tiempo': 0}
    start = clock()
    rows = con.execute("SELECT * FROM agencies WHERE custom_domain IS NOT NULL ORDER BY COALESCE(domain_checked_at, ''), id").fetchall()
    for r in rows:
        if not db.plan_has(r, 'domain'):
            out['sin_plan'] += 1
            continue
        if clock() - start > budget_s:
            out['sin_tiempo'] += 1
            continue
        res = check(con, r, resolver=resolver, source='cron', now=now, warm=warm)
        out['checked'] += 1
        if res['event'] == 'verified':
            out['verificados'] += 1
        elif res['event'] == 'lost':
            out['perdidos'] += 1
        elif res['state'] == 'verificado':
            out['ok'] += 1
        else:
            out['pendientes'] += 1
    return out
