"""Mercado Libre Mexico OAuth 2.0 (authorization code + PKCE) and item publishing.

LOCAL MVP: nothing here touches the network unless LLAVE_ML_LIVE=1 AND the app is configured.
Never log or print tokens/secrets.
"""
import base64
import datetime
import hashlib
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request

from . import db
from .feeds import mercadolibre as ml_feed

# confirm in developers.mercadolibre.com.mx before going live
AUTH_URL = 'https://auth.mercadolibre.com.mx/authorization'
TOKEN_URL = 'https://api.mercadolibre.com/oauth/token'
ITEMS_URL = 'https://api.mercadolibre.com/items'

STATE_TTL_MIN = 10
REFRESH_MARGIN_MIN = 5
NOT_LIVE_MSG = 'Conexión real con Mercado Libre desactivada en el MVP'


def config():
    return {
        'client_id': os.environ.get('ML_CLIENT_ID', ''),
        'client_secret': os.environ.get('ML_CLIENT_SECRET', ''),
        'redirect_uri': os.environ.get('ML_REDIRECT_URI') or
                        'http://app.%s:%d/oauth/mercadolibre/callback' % (db.BASE_DOMAIN, db.PORT),
    }


def is_configured():
    c = config()
    return bool(c['client_id'] and c['client_secret'])


def is_live():
    return is_configured() and os.environ.get('LLAVE_ML_LIVE') == '1'


def _now():
    return datetime.datetime.utcnow().replace(microsecond=0)


def _iso(d):
    return d.isoformat()


def ensure_tables(con):
    # In production tokens go to a vault (Supabase Vault), never plain columns.
    con.executescript("""
    CREATE TABLE IF NOT EXISTS ml_oauth_states (
      state TEXT PRIMARY KEY, agency_id INTEGER, code_verifier TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS ml_accounts (
      agency_id INTEGER PRIMARY KEY REFERENCES agencies(id) ON DELETE CASCADE,
      ml_user_id TEXT, nickname TEXT, access_token TEXT, refresh_token TEXT,
      expires_at TEXT, scope TEXT, connected_at TEXT,
      status TEXT);  -- 'conectada' | 'desconectada' | 'demo'
    """)
    con.commit()


def start(con, agency_id):
    """Return the authorization URL (and remember state+verifier), or None if not configured."""
    if not is_configured():
        return None
    ensure_tables(con)
    cfg = config()
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode()
    cutoff = _iso(_now() - datetime.timedelta(minutes=STATE_TTL_MIN))
    con.execute('DELETE FROM ml_oauth_states WHERE created_at < ?', (cutoff,))
    con.execute('INSERT INTO ml_oauth_states(state, agency_id, code_verifier, created_at) VALUES (?,?,?,?)',
                (state, agency_id, verifier, _iso(_now())))
    con.commit()
    q = {'response_type': 'code', 'client_id': cfg['client_id'], 'redirect_uri': cfg['redirect_uri'],
         'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'}
    return AUTH_URL + '?' + urllib.parse.urlencode(q)


def _default_http_post(url, data, headers=None):
    """Default transport (only reachable when live). Form-encodes unless Content-Type is JSON.
    Errors never include request bodies (they hold secrets)."""
    headers = dict(headers or {})
    if 'json' in headers.get('Content-Type', ''):
        body = json.dumps(data).encode('utf-8')
    else:
        headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
        body = urllib.parse.urlencode(data).encode('utf-8')
    headers.setdefault('Accept', 'application/json')
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode('utf-8') or '{}')
    except urllib.error.HTTPError as e:
        raise RuntimeError('Mercado Libre respondió HTTP %d' % e.code)
    except urllib.error.URLError:
        raise RuntimeError('No se pudo contactar a Mercado Libre')


def _store_tokens(con, agency_id, tok, keep_refresh=None):
    exp = _iso(_now() + datetime.timedelta(seconds=int(tok.get('expires_in', 0) or 0)))
    refresh = tok.get('refresh_token') or keep_refresh
    uid = tok.get('user_id')
    con.execute("""INSERT INTO ml_accounts(agency_id, ml_user_id, access_token, refresh_token, expires_at, scope,
                       connected_at, status) VALUES (?,?,?,?,?,?,?, 'conectada')
                   ON CONFLICT(agency_id) DO UPDATE SET
                     ml_user_id=COALESCE(excluded.ml_user_id, ml_user_id), access_token=excluded.access_token,
                     refresh_token=excluded.refresh_token, expires_at=excluded.expires_at,
                     scope=COALESCE(excluded.scope, scope),
                     connected_at=COALESCE(connected_at, excluded.connected_at), status='conectada'""",
                (agency_id, str(uid) if uid is not None else None, tok.get('access_token'), refresh, exp,
                 tok.get('scope'), _iso(_now())))
    con.commit()


def finish(con, state, code, http_post=None):
    """Validate state (single use, 10 min), then exchange the code. Returns agency_id."""
    ensure_tables(con)
    row = con.execute('SELECT * FROM ml_oauth_states WHERE state=?', (state or '',)).fetchone()
    if not row:
        raise ValueError('Estado de autorización inválido')
    con.execute('DELETE FROM ml_oauth_states WHERE state=?', (state,))
    con.commit()
    if _now() - datetime.datetime.fromisoformat(row['created_at']) > datetime.timedelta(minutes=STATE_TTL_MIN):
        raise ValueError('La autorización expiró, intenta de nuevo')
    if not is_live():
        raise RuntimeError(NOT_LIVE_MSG)
    cfg = config()
    tok = (http_post or _default_http_post)(TOKEN_URL, {
        'grant_type': 'authorization_code', 'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'],
        'code': code, 'redirect_uri': cfg['redirect_uri'], 'code_verifier': row['code_verifier']}, {})
    if not tok.get('access_token'):
        raise RuntimeError('Mercado Libre no entregó un token')
    _store_tokens(con, row['agency_id'], tok)
    return row['agency_id']


def connect_demo(con, agency_id):
    ensure_tables(con)
    con.execute("""INSERT INTO ml_accounts(agency_id, nickname, connected_at, status)
                   VALUES (?, 'cuenta de prueba', ?, 'demo')
                   ON CONFLICT(agency_id) DO UPDATE SET nickname='cuenta de prueba', access_token=NULL,
                     refresh_token=NULL, expires_at=NULL, connected_at=excluded.connected_at, status='demo'""",
                (agency_id, _iso(_now())))
    con.commit()


def refresh_if_needed(con, agency_id, http_post=None):
    """Refresh the access token when under 5 min remain. Live only. Returns True if refreshed."""
    ensure_tables(con)
    if not is_live():
        return False
    a = con.execute('SELECT * FROM ml_accounts WHERE agency_id=?', (agency_id,)).fetchone()
    if not a or a['status'] != 'conectada' or not a['refresh_token']:
        return False
    if a['expires_at'] and datetime.datetime.fromisoformat(a['expires_at']) - _now() > \
            datetime.timedelta(minutes=REFRESH_MARGIN_MIN):
        return False
    cfg = config()
    tok = (http_post or _default_http_post)(TOKEN_URL, {
        'grant_type': 'refresh_token', 'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'],
        'refresh_token': a['refresh_token']}, {})
    if not tok.get('access_token'):
        raise RuntimeError('Mercado Libre no entregó un token')
    _store_tokens(con, agency_id, tok, keep_refresh=a['refresh_token'])
    return True


def disconnect(con, agency_id):
    ensure_tables(con)
    con.execute("""UPDATE ml_accounts SET access_token=NULL, refresh_token=NULL, expires_at=NULL,
                   status='desconectada' WHERE agency_id=?""", (agency_id,))
    con.commit()


def status(con, agency_id):
    ensure_tables(con)
    a = con.execute('SELECT status, nickname, connected_at FROM ml_accounts WHERE agency_id=?',
                    (agency_id,)).fetchone()
    return {'status': a['status'] if a else 'desconectada', 'nickname': a['nickname'] if a else None,
            'connected_at': a['connected_at'] if a else None,
            'live': is_live(), 'configured': is_configured()}


def publish(con, listing_id, http_post=None):
    """Live POST /items when live and the agency has a 'conectada' account; otherwise dry-run to the outbox."""
    ensure_tables(con)
    l = con.execute('SELECT agency_id FROM listings WHERE id=?', (listing_id,)).fetchone()
    if not l:
        raise ValueError('Propiedad no encontrada')
    acc = con.execute('SELECT * FROM ml_accounts WHERE agency_id=?', (l['agency_id'],)).fetchone()
    if is_live() and acc and acc['status'] == 'conectada':
        refresh_if_needed(con, l['agency_id'], http_post)
        acc = con.execute('SELECT access_token FROM ml_accounts WHERE agency_id=?', (l['agency_id'],)).fetchone()
        item = ml_feed.build_item(db.canonical(con, listing_id))
        item = {k: v for k, v in item.items() if not k.startswith('_')}
        resp = (http_post or _default_http_post)(ITEMS_URL, item, {
            'Authorization': 'Bearer ' + acc['access_token'], 'Content-Type': 'application/json'})
        con.execute("INSERT INTO outbox(kind, ref, payload, status, response) VALUES "
                    "('portal.mercadolibre.create', ?, ?, 'sent', ?)",
                    ('listing:%d' % listing_id, json.dumps(item, ensure_ascii=False),
                     json.dumps({'id': resp.get('id'), 'permalink': resp.get('permalink')})))
        con.commit()
        return {'mode': 'live', 'item_id': resp.get('id'), 'permalink': resp.get('permalink')}
    payload = ml_feed.dry_run_publish(con, listing_id)
    return {'mode': 'dry_run', 'payload': payload}
