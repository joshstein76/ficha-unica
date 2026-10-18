"""Buyer property alerts ("Avísame de propiedades similares"): a buyer subscribes on an agent's site with consent;
when a matching listing goes public, the AGENCY gets the match and a ready WhatsApp message to forward (dry-run outbox).
We never message the buyer automatically until a template is approved (Josh's preview rule)."""
from . import db, whatsapp
from .web.common import money


def ensure_table(con):
    con.execute("CREATE TABLE IF NOT EXISTS saved_searches (id INTEGER PRIMARY KEY, agency_id INTEGER NOT NULL REFERENCES agencies(id) ON DELETE CASCADE, "
                "name TEXT, phone TEXT NOT NULL, operation TEXT, property_type TEXT, colonia TEXT, max_price_cents INTEGER, currency TEXT DEFAULT 'MXN', "
                "min_beds INTEGER, active INTEGER NOT NULL DEFAULT 1, last_match_listing INTEGER DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    con.execute("CREATE TABLE IF NOT EXISTS saved_search_matches (search_id INTEGER, listing_id INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), "
                "PRIMARY KEY (search_id, listing_id))")


def subscribe(con, agency_id, name, phone, operation=None, property_type=None, colonia=None, max_price=None, currency='MXN', min_beds=None, consent=False):
    if not consent:
        raise ValueError('Acepta el aviso de privacidad para recibir avisos.')
    p = whatsapp.norm_phone(phone)
    if not p:
        raise ValueError('Revisa tu WhatsApp: 10 dígitos.')
    ensure_table(con)
    sid = con.execute('INSERT INTO saved_searches(agency_id, name, phone, operation, property_type, colonia, max_price_cents, currency, min_beds) '
                      'VALUES (?,?,?,?,?,?,?,?,?)', (agency_id, (name or '')[:80], p, operation or None, property_type or None,
                                                     (colonia or '').strip()[:60] or None,
                                                     int(max_price) * 100 if str(max_price or '').isdigit() else None,
                                                     currency if currency in ('MXN', 'USD') else 'MXN',
                                                     int(min_beds) if str(min_beds or '').isdigit() else None)).lastrowid
    db.audit(con, 'site', 'saved_search', 'agency:%d search:%d' % (agency_id, sid))
    con.commit()
    return sid


def matches(con, search):
    s = dict(search)
    sql = "SELECT id FROM listings WHERE agency_id=? AND status IN ('activa','apartada')"
    args = [s['agency_id']]
    for col in ('operation', 'property_type'):
        if s.get(col):
            sql += ' AND %s=?' % col
            args.append(s[col])
    if s.get('colonia'):
        sql += ' AND (colonia LIKE ? OR municipio LIKE ?)'
        args += ['%' + s['colonia'] + '%'] * 2
    if s.get('max_price_cents'):
        sql += ' AND currency=? AND price_cents <= ?'
        args += [s['currency'], s['max_price_cents']]
    if s.get('min_beds'):
        sql += ' AND bedrooms >= ?'
        args.append(s['min_beds'])
    sql += ' AND id NOT IN (SELECT listing_id FROM saved_search_matches WHERE search_id=?)'
    args.append(s['id'])
    return [r['id'] for r in con.execute(sql, args)]


def run(con):
    """Queue one agency alert per new match (dry-run). Returns number of matches queued."""
    import json
    ensure_table(con)
    n = 0
    for s in con.execute('SELECT * FROM saved_searches WHERE active=1').fetchall():
        a = con.execute('SELECT * FROM agencies WHERE id=?', (s['agency_id'],)).fetchone()
        for lid in matches(con, s):
            c = db.canonical(con, lid)
            forward = 'Hola %s, salió una propiedad que coincide con lo que busca: %s, %s. %s' % (
                (s['name'] or '').split(' ')[0] or '', c['title'], money(c['price'], c['currency']), c['url'])
            payload = {'kind': 'ghl.agent_alert', 'audience': 'agency', 'channel': 'whatsapp', 'to_whatsapp': a['whatsapp'],
                       'body': {'text': 'Nueva coincidencia para %s (alerta de búsqueda): %s. Reenvíale: %s' % (
                           s['name'] or 'un cliente', c['ref'], whatsapp.wa_link(s['phone'], forward))}}
            con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('ghl.agent_alert', ?, ?, 'dry_run')",
                        ('saved_search:%d:%d' % (s['id'], lid), json.dumps(payload, ensure_ascii=False)))
            con.execute('INSERT OR IGNORE INTO saved_search_matches(search_id, listing_id) VALUES (?,?)', (s['id'], lid))
            n += 1
    con.commit()
    return n
