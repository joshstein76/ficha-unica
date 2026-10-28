"""Speed-to-lead watchdog: first reply within 5 minutes. Alerts go to the AGENCY only (dry-run outbox);
this module never messages the lead."""
import datetime
import json

from . import db, replies, whatsapp

STATUSES = ('nuevo', 'contactado', 'cita', 'cerrado', 'descartado')
FMT = '%Y-%m-%d %H:%M:%S'
MAX_AGE_DAYS = 7


def ensure_columns(con):
    cols = {r[1] for r in con.execute('PRAGMA table_info(leads)')}
    for col in ('first_response_at', 'reminded_at'):
        if col not in cols:
            con.execute('ALTER TABLE leads ADD COLUMN %s TEXT' % col)
    con.execute("""CREATE TABLE IF NOT EXISTS listing_views (
        listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
        day TEXT NOT NULL,
        views INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(listing_id, day))""")
    con.commit()


def _now(now):
    if now is None:
        return datetime.datetime.utcnow().replace(microsecond=0)
    if isinstance(now, str):
        return datetime.datetime.strptime(now, FMT)
    return now


def _own_lead(con, lead_id, agency_id):
    return con.execute('SELECT id, status, first_response_at FROM leads WHERE id=? AND agency_id=?',
                       (lead_id, agency_id)).fetchone()


def mark_responded(con, lead_id, agency_id, now=None):
    ensure_columns(con)
    l = _own_lead(con, lead_id, agency_id)
    if not l:
        return False
    ts = _now(now).strftime(FMT)
    con.execute('UPDATE leads SET first_response_at=COALESCE(first_response_at, ?), '
                "status=CASE WHEN status='nuevo' THEN 'contactado' ELSE status END WHERE id=?", (ts, lead_id))
    db.audit(con, 'agency:%d' % agency_id, 'lead_responded', 'lead:%d' % lead_id)
    con.commit()
    return True


def set_status(con, lead_id, agency_id, status, now=None):
    if status not in STATUSES:
        return False
    ensure_columns(con)
    l = _own_lead(con, lead_id, agency_id)
    if not l:
        return False
    ts = _now(now).strftime(FMT)
    if status != 'nuevo':
        con.execute('UPDATE leads SET status=?, first_response_at=COALESCE(first_response_at, ?) WHERE id=?',
                    (status, ts, lead_id))
    else:
        con.execute('UPDATE leads SET status=? WHERE id=?', (status, lead_id))
    db.audit(con, 'agency:%d' % agency_id, 'lead_status', 'lead:%d %s->%s' % (lead_id, l['status'], status))
    con.commit()
    return True


FOLLOW_UP_DAYS = (1, 3, 7)  # Mañana · En 3 días · En una semana; 0 clears it


def today_cdmx(now=None):
    """Mexico City calendar day (no DST since 2022: UTC-6)."""
    if now is not None:
        return _now(now).date()
    return (datetime.datetime.utcnow() - datetime.timedelta(hours=6)).date()


def set_follow_up(con, lead_id, agency_id, days, today=None):
    """Remind the agent to follow up in N days (1/3/7), or clear it (0). Only the agency's own leads."""
    if days not in FOLLOW_UP_DAYS + (0,):
        return False
    if not _own_lead(con, lead_id, agency_id):
        return False
    day = None if days == 0 else (today or today_cdmx()) + datetime.timedelta(days=days)
    con.execute('UPDATE leads SET follow_up_on=? WHERE id=?', (day.isoformat() if day else None, lead_id))
    db.audit(con, 'agency:%d' % agency_id, 'lead_follow_up', 'lead:%d %s' % (lead_id, day.isoformat() if day else 'none'))
    con.commit()
    return True


def follow_up_due_sql():
    return "follow_up_on IS NOT NULL AND follow_up_on <= ? AND status IN ('nuevo','contactado','cita')"


def follow_up_count(con, agency_id, today=None):
    """Open leads whose follow-up day is today or already passed."""
    return con.execute('SELECT COUNT(*) FROM leads WHERE agency_id=? AND ' + follow_up_due_sql(),
                       (agency_id, (today or today_cdmx()).isoformat())).fetchone()[0]


DIGEST_HOURS = (9, 20)  # CDMX: from 9:00 a.m., never after 8 p.m. (Josh's night rule)


def follow_up_digest(con, now=None):
    """Once a day per agency: one dry-run alert to the AGENCY listing today's due follow-ups. Never messages the lead."""
    n = _now(now)
    local = n - datetime.timedelta(hours=6)
    if not DIGEST_HOURS[0] <= local.hour < DIGEST_HOURS[1]:
        return 0
    day = local.date().isoformat()
    rows = con.execute(
        "SELECT l.agency_id, l.name, a.whatsapp AS agency_whatsapp FROM leads l JOIN agencies a ON a.id=l.agency_id "
        "WHERE l.follow_up_on IS NOT NULL AND l.follow_up_on <= ? AND l.status IN ('nuevo','contactado','cita')"
        " ORDER BY l.agency_id, l.follow_up_on, l.id", (day,)).fetchall()
    by_agency = {}
    for r in rows:
        by_agency.setdefault(r['agency_id'], []).append(r)
    count = 0
    for agency_id, leads in by_agency.items():
        ref = 'follow_up_digest:%d:%s' % (agency_id, day)
        if con.execute('SELECT 1 FROM outbox WHERE ref=?', (ref,)).fetchone():
            continue
        names = [(r['name'] or '').strip() or 'un cliente' for r in leads[:3]]
        more = len(leads) - len(names)
        who = ', '.join(names) + (' y %d más' % more if more else '')
        text = '📅 Hoy toca dar seguimiento a %d cliente%s: %s. Velos aquí: %s/clientes?estado=hoy' % (
            len(leads), '' if len(leads) == 1 else 's', who, db.origin('app'))
        payload = {'kind': 'ghl.agent_alert', 'audience': 'agency', 'channel': 'whatsapp',
                   'to_whatsapp': leads[0]['agency_whatsapp'], 'body': {'text': text}}
        con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('ghl.agent_alert', ?, ?, 'dry_run')",
                    (ref, json.dumps(payload, ensure_ascii=False)))
        count += 1
    con.commit()
    return count


def overdue(con, minutes=5, now=None):
    ensure_columns(con)
    n = _now(now)
    cutoff = (n - datetime.timedelta(minutes=minutes)).strftime(FMT)
    oldest = (n - datetime.timedelta(days=MAX_AGE_DAYS)).strftime(FMT)
    rows = con.execute(
        "SELECT l.*, a.slug AS agency_slug, a.whatsapp AS agency_whatsapp, "
        "li.ref AS listing_ref, li.title AS listing_title FROM leads l "
        "JOIN agencies a ON a.id=l.agency_id LEFT JOIN listings li ON li.id=l.listing_id "
        "WHERE l.status='nuevo' AND l.first_response_at IS NULL AND l.reminded_at IS NULL "
        "AND l.created_at < ? AND l.created_at >= ? ORDER BY l.created_at, l.id", (cutoff, oldest)).fetchall()
    return [dict(r) for r in rows]


def _text(con, lead, n):
    ag = con.execute('SELECT * FROM agencies WHERE id=?', (lead['agency_id'],)).fetchone()
    title = lead['listing_title'] or 'tu sitio'
    reply = replies.render(ag, lead['name'], lead['listing_title'], '')
    who = (lead['name'] or '').strip() or 'Un cliente'
    if lead['phone']:
        link = whatsapp.wa_link(lead['phone'], reply)
    else:
        link = 'correo: %s' % (lead['email'] or 'sin contacto')
    ref = ' (%s)' % lead['listing_ref'] if lead['listing_ref'] else ''
    return '⏰ %s te escribió hace %d min por %s%s y sigue sin respuesta. Respóndele ya: %s' % (
        who, n, title, ref, link)


def remind(con, now=None):
    n = _now(now)
    count = 0
    for lead in overdue(con, 5, n):
        ref = 'lead_reminder:%d' % lead['id']
        if con.execute('SELECT 1 FROM outbox WHERE ref=?', (ref,)).fetchone():
            con.execute('UPDATE leads SET reminded_at=? WHERE id=?', (n.strftime(FMT), lead['id']))
            continue
        created = datetime.datetime.strptime(lead['created_at'], FMT)
        mins = max(int((n - created).total_seconds() // 60), 0)
        payload = {'kind': 'ghl.agent_alert', 'audience': 'agency', 'channel': 'whatsapp',
                   'to_whatsapp': lead['agency_whatsapp'], 'body': {'text': _text(con, lead, mins)}}
        con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('ghl.agent_alert', ?, ?, 'dry_run')",
                    (ref, json.dumps(payload, ensure_ascii=False)))
        con.execute('UPDATE leads SET reminded_at=? WHERE id=?', (n.strftime(FMT), lead['id']))
        count += 1
    con.commit()
    return count
