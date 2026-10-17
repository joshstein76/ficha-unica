"""Weekly "is your price still right?" check. Alerts go to the AGENCY only (dry-run outbox), never to clients."""
import datetime
import json

from . import db

STALE_DAYS = 30
MAX_LISTED = 5


def _today(today):
    if today is None:
        return datetime.date.today()
    if isinstance(today, datetime.datetime):
        return today.date()
    return today


def stale_listings(con, agency_id=None, today=None):
    today = _today(today)
    ph = ','.join('?' * len(db.PUBLIC_STATUSES))
    q = ('SELECT id, agency_id, ref, title, price_cents, currency, price_date FROM listings '
         'WHERE status IN (%s)' % ph)
    args = list(db.PUBLIC_STATUSES)
    if agency_id is not None:
        q += ' AND agency_id=?'
        args.append(agency_id)
    out = []
    for r in con.execute(q + ' ORDER BY agency_id, ref', args):
        days = None
        if r['price_date']:
            try:
                days = (today - datetime.date.fromisoformat(r['price_date'][:10])).days
            except ValueError:
                days = None
            if days is not None and days <= STALE_DAYS:
                continue
        out.append({'listing_id': r['id'], 'agency_id': r['agency_id'], 'ref': r['ref'], 'title': r['title'],
                    'price': (r['price_cents'] // 100) if r['price_cents'] is not None else None,
                    'currency': r['currency'], 'price_date': r['price_date'], 'days': days})
    return out


def confirm(con, listing_id, agency_id, today=None):
    cur = con.execute("UPDATE listings SET price_date=?, updated_at=datetime('now') WHERE id=? AND agency_id=?",
                      (_today(today).isoformat(), listing_id, agency_id))
    if cur.rowcount != 1:
        con.rollback()
        return False
    db.audit(con, 'agency:%d' % agency_id, 'price_confirmed', 'listing:%d' % listing_id)
    con.commit()
    return True


def panel_url():
    return db.origin('app')


def _line(s):
    money = ('$%s %s' % (format(s['price'], ','), s['currency'])) if s['price'] is not None else 'precio a consultar'
    since = 'desde %s' % s['price_date'] if s['price_date'] else 'sin fecha'
    return '%s %s %s (%s)' % (s['ref'], s['title'], money, since)


def message_text(items):
    shown = items[:MAX_LISTED]
    text = 'Hola, ¿siguen igual estos precios? ' + '; '.join(_line(s) for s in shown)
    if len(items) > len(shown):
        text += ' y %d más' % (len(items) - len(shown))
    return text + '. Confírmalos con un toque: %s/precios' % panel_url()


def weekly_run(con, today=None):
    today = _today(today)
    y, w, _ = today.isocalendar()
    week = '%d-W%02d' % (y, w)
    by = {}
    for s in stale_listings(con, None, today):
        by.setdefault(s['agency_id'], []).append(s)
    n_ag = n_li = 0
    for aid, items in by.items():
        ref = 'price_check:%d:%s' % (aid, week)
        if con.execute('SELECT 1 FROM outbox WHERE ref=?', (ref,)).fetchone():
            continue
        ag = con.execute('SELECT whatsapp FROM agencies WHERE id=?', (aid,)).fetchone()
        payload = {'kind': 'ghl.agent_alert', 'audience': 'agency', 'channel': 'whatsapp',
                   'to_whatsapp': ag['whatsapp'] if ag else None, 'body': {'text': message_text(items)}}
        con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('ghl.agent_alert', ?, ?, 'dry_run')",
                    (ref, json.dumps(payload, ensure_ascii=False)))
        n_ag += 1
        n_li += len(items)
    con.commit()
    return {'agencies': n_ag, 'listings': n_li}
