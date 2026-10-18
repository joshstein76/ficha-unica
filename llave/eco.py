"""Ecosistema engine (Ficha Única / LLAVE): credits for work that stays inside Josh's family of companies.

An agent earns credits when a sister brand CONFIRMS an event (signed webhook / API / admin), never on the
agent's own claim. Credits are redeemed for visibility (featured listing, extra listings, lead priority).
Pure stdlib, SQLite. No network: GHL effects are only queued to the dry-run outbox.
"""
import datetime
import hashlib
import hmac
import time
import json

from . import whatsapp

# ---------------------------------------------------------------- rules (data; Claude's proposal, Josh can change)
# key "brand.kind" -> credits, label (Spanish), pair (from→to, for the owner report)
RULES = {
    'rentapoliza.poliza_emitida': {'credits': 30, 'label': 'Póliza jurídica emitida en RentaPóliza', 'pair': 'fichaunica→rentapoliza'},
    'vive.referido_cerrado':      {'credits': 50, 'label': 'Referido cerrado con VIVE Polanco (la comisión 50/50 la maneja VIVE, no Ficha Única)', 'pair': 'fichaunica→vive'},
    'vive.referido_enviado':      {'credits': 5,  'label': 'Referido enviado a VIVE Polanco', 'pair': 'fichaunica→vive'},
    'cerquito.pedido':            {'credits': 5,  'label': 'Pedido en Cerquito (por pedido)', 'pair': 'fichaunica→cerquito'},
    'idxbloom.referido_alta':     {'credits': 20, 'label': 'Alta de un referido en IDX Bloom', 'pair': 'fichaunica→idxbloom'},
    'ciaobella.cliente_alta':     {'credits': 20, 'label': 'Cliente nuevo de Ciao Bella Marketing', 'pair': 'fichaunica→ciaobella'},
    'fichaunica.colega_publica':  {'credits': 10, 'label': 'Colega invitado que publica su primera propiedad', 'pair': 'fichaunica→fichaunica'},
}

# item -> cost, days, boost kind, label. Claude's proposal, Josh can change.
CATALOG = {
    'destacar_7d':           {'cost': 20, 'days': 7,  'kind': 'destacada',        'label': 'Propiedad destacada 7 días (orden prioritario en la Bolsa y en el directorio público)'},
    'extra_10_listings_30d': {'cost': 30, 'days': 30, 'kind': 'extra_listings',   'label': '10 propiedades extra por 30 días', 'extra': 10},
    'prioridad_leads_30d':   {'cost': 40, 'days': 30, 'kind': 'prioridad_leads',  'label': 'Prioridad en leads generales de Ficha Única por 30 días'},
}

FREE_LEADS_DEFINITION = (
    'Los leads gratis vienen únicamente del tráfico propio de Ficha Única (el directorio, los feeds y las consultas '
    'generales del portal que no son de una propiedad en particular). Se reparten entre las inmobiliarias con '
    'prioridad activa en su zona. No garantizamos un número de leads: depende del tráfico y de la demanda de cada zona.'
)

BRANDS = ('rentapoliza', 'vive', 'cerquito', 'idxbloom', 'ciaobella', 'fichaunica')
STATUSES = ('pendiente', 'confirmado', 'rechazado')
REPLAY_WINDOW_S = 300


def _now(now=None):
    return now or datetime.datetime.utcnow()


def _ts(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _parse(s):
    return datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')


def ensure_tables(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS eco_events (
      id INTEGER PRIMARY KEY,
      agency_id INTEGER REFERENCES agencies(id) ON DELETE CASCADE,
      brand TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pendiente' CHECK (status IN ('pendiente','confirmado','rechazado')),
      credits INTEGER NOT NULL DEFAULT 0,
      meta TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      confirmed_at TEXT,
      UNIQUE (brand, ref)
    );
    CREATE TABLE IF NOT EXISTS eco_ledger (          -- append-only: never UPDATE or DELETE
      id INTEGER PRIMARY KEY,
      agency_id INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
      delta INTEGER NOT NULL, reason TEXT NOT NULL,
      event_id INTEGER REFERENCES eco_events(id),
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS eco_boosts (          -- listing_id NULL for agency-level boosts
      id INTEGER PRIMARY KEY,
      agency_id INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
      listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,
      kind TEXT NOT NULL,                            -- destacada | extra_listings | prioridad_leads
      starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
      source_ledger_id INTEGER REFERENCES eco_ledger(id)
    );
    CREATE INDEX IF NOT EXISTS ix_eco_events_agency ON eco_events(agency_id, status);
    CREATE INDEX IF NOT EXISTS ix_eco_ledger_agency ON eco_ledger(agency_id);
    CREATE INDEX IF NOT EXISTS ix_eco_boosts_listing ON eco_boosts(listing_id, kind, ends_at);
    CREATE INDEX IF NOT EXISTS ix_eco_boosts_agency ON eco_boosts(agency_id, kind, ends_at);
    ''')
    con.commit()


# ---------------------------------------------------------------- events
def _audit(con, actor, action, detail):
    try:
        con.execute('INSERT INTO audit(actor, action, detail) VALUES (?,?,?)', (actor, action, detail))
    except Exception:
        pass


def record_event(con, brand, kind, ref, agency_id, meta=None, confirmed=False, actor='system', now=None):
    """Idempotent per (brand, ref). Returns the event row as dict plus 'created' (False = already known).
    confirmed=True only for signed webhooks / admin actions, never for an agent's own claim."""
    key = '%s.%s' % (brand, kind)
    rule = RULES.get(key)
    if not rule:
        raise ValueError('regla desconocida: %s' % key)
    ref = str(ref).strip()
    if not ref:
        raise ValueError('ref requerido')
    row = con.execute('SELECT * FROM eco_events WHERE brand=? AND ref=?', (brand, ref)).fetchone()
    if row:
        d = dict(row)
        d['created'] = False
        return d
    cur = con.execute('INSERT INTO eco_events(agency_id, brand, kind, ref, credits, meta, created_at) VALUES (?,?,?,?,?,?,?)',
                      (agency_id, brand, kind, ref, rule['credits'], json.dumps(meta or {}, ensure_ascii=False),
                       _ts(_now(now))))
    con.commit()
    if confirmed:
        confirm_event(con, cur.lastrowid, actor, now=now)
    d = dict(con.execute('SELECT * FROM eco_events WHERE id=?', (cur.lastrowid,)).fetchone())
    d['created'] = True
    return d


def confirm_event(con, event_id, actor, now=None):
    """pendiente -> confirmado and +credits in the ledger. Idempotent: a second call grants nothing."""
    ev = con.execute('SELECT * FROM eco_events WHERE id=?', (event_id,)).fetchone()
    if not ev:
        raise KeyError('evento no existe')
    if ev['status'] != 'pendiente':
        return False
    if not ev['agency_id']:
        raise ValueError('evento sin inmobiliaria')
    t = _ts(_now(now))
    con.execute("UPDATE eco_events SET status='confirmado', confirmed_at=? WHERE id=? AND status='pendiente'", (t, event_id))
    con.execute('INSERT INTO eco_ledger(agency_id, delta, reason, event_id, created_at) VALUES (?,?,?,?,?)',
                (ev['agency_id'], ev['credits'], '%s.%s (%s)' % (ev['brand'], ev['kind'], actor), event_id, t))
    _audit(con, actor, 'eco.confirm', 'event:%d' % event_id)
    con.commit()
    return True


def reject_event(con, event_id, actor, reason=''):
    ev = con.execute('SELECT status FROM eco_events WHERE id=?', (event_id,)).fetchone()
    if not ev:
        raise KeyError('evento no existe')
    if ev['status'] != 'pendiente':
        return False  # a confirmed event is never undone silently; reverse with an explicit negative ledger row
    con.execute("UPDATE eco_events SET status='rechazado' WHERE id=?", (event_id,))
    _audit(con, actor, 'eco.reject', 'event:%d %s' % (event_id, reason))
    con.commit()
    return True


def balance(con, agency_id):
    return con.execute('SELECT COALESCE(SUM(delta),0) FROM eco_ledger WHERE agency_id=?', (agency_id,)).fetchone()[0]


# ---------------------------------------------------------------- redeem + boosts
class InsufficientCredits(Exception):
    pass


def redeem(con, agency_id, item, listing_id=None, now=None):
    cat = CATALOG.get(item)
    if not cat:
        raise ValueError('artículo desconocido: %s' % item)
    if cat['kind'] == 'destacada':
        l = con.execute('SELECT agency_id FROM listings WHERE id=?', (listing_id,)).fetchone() if listing_id else None
        if not l or l['agency_id'] != agency_id:
            raise ValueError('la propiedad no es de esta inmobiliaria')
    else:
        listing_id = None
    bal = balance(con, agency_id)
    if bal < cat['cost']:
        raise InsufficientCredits('faltan %d créditos' % (cat['cost'] - bal))
    t = _now(now)
    cur = con.execute('INSERT INTO eco_ledger(agency_id, delta, reason, created_at) VALUES (?,?,?,?)',
                      (agency_id, -cat['cost'], 'canje:%s' % item, _ts(t)))
    lid = cur.lastrowid
    # stack after a still-running boost of the same kind instead of overlapping it
    q = 'SELECT MAX(ends_at) FROM eco_boosts WHERE agency_id=? AND kind=? AND ends_at>?'
    args = [agency_id, cat['kind'], _ts(t)]
    if listing_id:
        q += ' AND listing_id=?'
        args.append(listing_id)
    cur_end = con.execute(q, args).fetchone()[0]
    start = max(t, _parse(cur_end)) if cur_end else t
    end = start + datetime.timedelta(days=cat['days'])
    con.execute('INSERT INTO eco_boosts(agency_id, listing_id, kind, starts_at, ends_at, source_ledger_id) VALUES (?,?,?,?,?,?)',
                (agency_id, listing_id, cat['kind'], _ts(start), _ts(end), lid))
    con.commit()
    return {'item': item, 'cost': cat['cost'], 'balance': bal - cat['cost'], 'starts_at': _ts(start), 'ends_at': _ts(end)}


def active_boost(con, listing_id, now=None):
    t = _ts(_now(now))
    return bool(con.execute("SELECT 1 FROM eco_boosts WHERE listing_id=? AND kind='destacada' AND starts_at<=? AND ends_at>?",
                            (listing_id, t, t)).fetchone())


def extra_listing_slots(con, agency_id, now=None):
    """Extra listings above the plan limit (add to db.PLAN_LIMITS in the caller)."""
    t = _ts(_now(now))
    n = con.execute("SELECT COUNT(*) FROM eco_boosts WHERE agency_id=? AND kind='extra_listings' AND starts_at<=? AND ends_at>?",
                    (agency_id, t, t)).fetchone()[0]
    return n * CATALOG['extra_10_listings_30d']['extra']


def priority_agencies(con, colonia=None, municipio=None, now=None):
    """Agencies with an ACTIVE prioridad_leads boost, best first (balance desc, then id).
    With colonia/municipio only agencies that have a listing in that zone qualify."""
    from .db import slugify
    t = _ts(_now(now))
    rows = con.execute("SELECT a.id, a.slug, a.name, MAX(b.ends_at) AS until FROM eco_boosts b "
                       "JOIN agencies a ON a.id=b.agency_id WHERE b.kind='prioridad_leads' AND b.starts_at<=? AND b.ends_at>? "
                       "GROUP BY a.id", (t, t)).fetchall()
    out = []
    for r in rows:
        if colonia or municipio:
            ls = con.execute('SELECT colonia, municipio FROM listings WHERE agency_id=?', (r['id'],)).fetchall()
            ok = any((colonia and slugify(l['colonia'] or '') == slugify(colonia)) or
                     (municipio and slugify(l['municipio'] or '') == slugify(municipio)) for l in ls)
            if not ok:
                continue
        out.append({'agency_id': r['id'], 'slug': r['slug'], 'name': r['name'], 'priority_until': r['until'],
                    'credits': balance(con, r['id'])})
    out.sort(key=lambda d: (-d['credits'], d['agency_id']))
    return out


# ---------------------------------------------------------------- webhooks
def sign(secret, body_bytes, timestamp=None):
    """Signature the sister brand must send. With a timestamp the signed text is b'<ts>.' + body."""
    msg = (str(timestamp).encode() + b'.' + body_bytes) if timestamp is not None else body_bytes
    return 'sha256=' + hmac.new(secret.encode() if isinstance(secret, str) else secret, msg, hashlib.sha256).hexdigest()


def verify_webhook(secret, body_bytes, signature_header, timestamp=None, now=None, window=REPLAY_WINDOW_S):
    """HMAC-SHA256 hex, constant time. If `timestamp` (X-Eco-Timestamp, unix seconds) is given it is part of the
    signed text and must be within `window` seconds of now (replay protection)."""
    if not secret or not signature_header:
        return False
    if timestamp is not None:
        try:
            ts = int(str(timestamp).strip())
        except ValueError:
            return False
        nowts = (now if now is not None else time.time())  # utcnow().timestamp() would apply the local UTC offset
        if abs(nowts - ts) > window:
            return False
    got = str(signature_header).strip()
    if got.lower().startswith('sha256='):
        got = got[7:]
    want = sign(secret, body_bytes, timestamp)[7:]
    return hmac.compare_digest(got.lower().encode(), want.encode())


def find_agency_by_agent(con, email=None, phone=None):
    """Agency id for a user matched by email (case-insensitive) or WhatsApp (normalised), else None."""
    em = (email or '').strip().lower()
    if em:
        r = con.execute('SELECT agency_id FROM users WHERE lower(email)=?', (em,)).fetchone()
        if r:
            return r['agency_id']
    ph = whatsapp.norm_phone(phone)
    if ph:
        for r in con.execute('SELECT agency_id, whatsapp FROM users WHERE whatsapp IS NOT NULL AND whatsapp<>""'):
            if whatsapp.norm_phone(r['whatsapp']) == ph:
                return r['agency_id']
    return None


def queue_tags(con, agency_id, event_id, tags, email='', phone=''):
    """DRY-RUN outbox row only. Nothing is sent to GHL or to any person."""
    a = con.execute('SELECT slug, ghl_location_id FROM agencies WHERE id=?', (agency_id,)).fetchone()
    op = {'kind': 'ghl.tag', 'mode': 'dry_run', 'method': 'POST', 'path': '/contacts/{contactId}/tags',
          'agency_slug': a['slug'] if a else None, 'locationId': (a and a['ghl_location_id']) or 'DRY_RUN_NO_LOCATION',
          'contact': {'email': email or '', 'phone': whatsapp.norm_phone(phone)}, 'body': {'tags': list(tags)}}
    con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('ghl.tag', ?, ?, 'dry_run')",
                ('eco:%d' % event_id, json.dumps(op, ensure_ascii=False)))
    con.commit()
    return op


def handle_rentapoliza_webhook(con, body, now=None):
    """body: {event:'poliza.emitida', folio, agent_email, agent_phone, listing_ref?, emitted_at}.
    Returns {ok, code, event_id?}. A valid signature (checked by the caller) IS the confirmation.
    Only folio + agent identity + listing ref are read: tenant/owner data is ignored by design."""
    if (body or {}).get('event') != 'poliza.emitida':
        return {'ok': False, 'code': 'evento_no_soportado'}
    folio = str(body.get('folio') or '').strip()
    if not folio:
        return {'ok': False, 'code': 'folio_requerido'}
    agency_id = find_agency_by_agent(con, body.get('agent_email'), body.get('agent_phone'))
    if not agency_id:
        return {'ok': False, 'code': 'asesor_no_encontrado'}
    meta = {k: body.get(k) for k in ('listing_ref', 'emitted_at') if body.get(k)}
    ev = record_event(con, 'rentapoliza', 'poliza_emitida', folio, agency_id, meta=meta,
                      confirmed=True, actor='webhook:rentapoliza', now=now)
    if not ev['created']:
        return {'ok': True, 'code': 'duplicado', 'event_id': ev['id']}
    queue_tags(con, agency_id, ev['id'], ['eco-source-rentapoliza', 'eco-referral-fichaunica-rentapoliza'],
               body.get('agent_email'), body.get('agent_phone'))
    return {'ok': True, 'code': 'confirmado', 'event_id': ev['id']}


# ---------------------------------------------------------------- owner dashboard
def owner_report(con, days=30, now=None):
    since = _ts(_now(now) - datetime.timedelta(days=days))
    by_brand, by_pair = {}, {}
    for r in con.execute('SELECT brand, kind, status, credits FROM eco_events WHERE created_at>=?', (since,)):
        b = by_brand.setdefault(r['brand'], {'events': 0, 'confirmed': 0, 'credits': 0})
        b['events'] += 1
        if r['status'] == 'confirmado':
            b['confirmed'] += 1
            b['credits'] += r['credits']
            pair = RULES.get('%s.%s' % (r['brand'], r['kind']), {}).get('pair', 'fichaunica→' + r['brand'])
            by_pair[pair] = by_pair.get(pair, 0) + 1
    top = [{'agency_id': r['agency_id'], 'name': r['name'], 'earned': r['earned'], 'balance': balance(con, r['agency_id'])}
           for r in con.execute("SELECT e.agency_id, a.name, SUM(e.credits) AS earned FROM eco_events e "
                                "JOIN agencies a ON a.id=e.agency_id WHERE e.status='confirmado' AND e.created_at>=? "
                                "GROUP BY e.agency_id ORDER BY earned DESC, e.agency_id LIMIT 10", (since,))]
    return {'days': days, 'by_brand': by_brand, 'by_pair': by_pair, 'top_agencies': top}
