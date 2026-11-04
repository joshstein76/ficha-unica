#!/usr/bin/env python3
"""El embudo de Ficha Única en un vistazo: cuántas agencias llegan a cada paso. Solo lectura y sin datos personales.
Usage: python3 tools/funnel.py [--db RUTA] [--json]      (sin --db usa LLAVE_DB, como la app; --json = una sola línea)

READ ONLY: the database is opened with `file:...?mode=ro` (SQLite refuses every write, and a missing file is an error, never a new empty
database). NO PERSONAL DATA: the output is counts and minutes. Names, emails, phones, taglines and messages are never selected for output.
Demo agencies (agencies.is_demo = 1, the seed) are left out of every number, and so are their listings and leads; their count is printed apart.

What each line counts (one agency counts once per line):
  agencies                 every non-demo agency.
  site_personalized        tagline AND about filled in: the panel's own "Personaliza tu sitio" step. Every agency already has a public site on its
                           free address from the moment it signs up, so "has a site" cannot be a funnel step; this is the first thing an agent does to it.
  with_public_listing      at least one listing with status activa or apartada (db.PUBLIC_STATUSES). Drafts, paused, sold and rented do not count.
  with_lead                at least one lead that is real: anything except a blocked or discarded-untouched lead (status descartado with no first_response_at).
  with_lead_answered       at least one lead the agent answered: first_response_at is set (WhatsApp tapped, or moved past "nuevo") and the status is not descartado.
                           A database too old to have first_response_at falls back to status contactado / cita / cerrado.
  on_paid_plan             plan pro or ia (the retired agencia / pro_crm count as ia). Includes pilot agents given a plan free with tools/set_plan.py.
  on_stripe_subscription   agencies.stripe_subscription_id is set: the ones really paying (a cancelled subscription clears it).
  signup_to_first_listing_min / signup_to_first_lead_min
                           median minutes from agencies.created_at to the agency's earliest listing (any status) / earliest real lead; agencies without
                           one are left out and `n` says how many were counted; never below 0. null when nobody has one yet.
"""
import argparse
import datetime
import json
import os
import sqlite3
import statistics
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db  # noqa: E402

FMT = '%Y-%m-%d %H:%M:%S'
PAID_PLANS = tuple(p for p in db.PLAN_LIMITS if p != 'gratis') + tuple(db.LEGACY_PLANS)

LABELS = [('agencies', 'Agencias (sin demo)'),
          ('site_personalized', 'Con sitio personalizado'),
          ('with_public_listing', 'Con 1+ propiedad pública'),
          ('with_lead', 'Con 1+ cliente'),
          ('with_lead_answered', 'Con un cliente respondido'),
          ('on_paid_plan', 'En plan de pago'),
          ('on_stripe_subscription', 'Con suscripción en Stripe')]


def open_ro(path):
    """Read-only connection: SQLite itself refuses any write. A missing file raises (it is never created)."""
    uri = 'file:%s?mode=ro' % urllib.parse.quote(os.path.abspath(path))
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _columns(con, table):
    return {r[1] for r in con.execute('PRAGMA table_info(%s)' % table)}


def _minutes(start, end):
    try:
        a, b = (datetime.datetime.strptime(str(x)[:19], FMT) for x in (start, end))
    except (TypeError, ValueError):
        return None
    return max((b - a).total_seconds() / 60.0, 0.0)


def _median(values):
    return {'median': round(statistics.median(values), 1) if values else None, 'n': len(values)}


def collect(con):
    """-> the funnel as a plain dict of numbers (see the module docstring for each one). Reads only."""
    acols, lcols = _columns(con, 'agencies'), _columns(con, 'leads')
    if not acols:  # no tables at all: an empty file, not a Ficha Única database
        return empty()
    demo = 'a.is_demo=0' if 'is_demo' in acols else '1=1'
    paid = ','.join('?' * len(PAID_PLANS))
    public = ','.join('?' * len(db.PUBLIC_STATUSES))
    if 'first_response_at' in lcols:
        real_lead, answered = "(l.status<>'descartado' OR l.first_response_at IS NOT NULL)", "(l.status<>'descartado' AND l.first_response_at IS NOT NULL)"
    else:
        real_lead, answered = "l.status<>'descartado'", "l.status IN ('contactado','cita','cerrado')"

    def count(where='1=1', args=()):
        return con.execute('SELECT COUNT(*) FROM agencies a WHERE %s AND %s' % (demo, where), args).fetchone()[0]

    out = {
        'agencies': count(),
        'site_personalized': count("COALESCE(TRIM(a.tagline),'')<>'' AND COALESCE(TRIM(a.about),'')<>''"),
        'with_public_listing': count('EXISTS (SELECT 1 FROM listings l WHERE l.agency_id=a.id AND l.status IN (%s))' % public, db.PUBLIC_STATUSES),
        'with_lead': count('EXISTS (SELECT 1 FROM leads l WHERE l.agency_id=a.id AND %s)' % real_lead),
        'with_lead_answered': count('EXISTS (SELECT 1 FROM leads l WHERE l.agency_id=a.id AND %s)' % answered),
        'on_paid_plan': count('a.plan IN (%s)' % paid, PAID_PLANS),
        'on_stripe_subscription': count("COALESCE(a.stripe_subscription_id,'')<>''") if 'stripe_subscription_id' in acols else 0,
    }
    first_listing = [_minutes(r[0], r[1]) for r in con.execute(
        'SELECT a.created_at, (SELECT MIN(l.created_at) FROM listings l WHERE l.agency_id=a.id) FROM agencies a WHERE %s' % demo)]
    first_lead = [_minutes(r[0], r[1]) for r in con.execute(
        'SELECT a.created_at, (SELECT MIN(l.created_at) FROM leads l WHERE l.agency_id=a.id AND %s) FROM agencies a WHERE %s' % (real_lead, demo))]
    out['signup_to_first_listing_min'] = _median([m for m in first_listing if m is not None])
    out['signup_to_first_lead_min'] = _median([m for m in first_lead if m is not None])
    out['demo_agencies_left_out'] = con.execute('SELECT COUNT(*) FROM agencies a WHERE NOT (%s)' % demo).fetchone()[0]
    return out


def empty():
    z = {k: 0 for k, _ in LABELS}
    z.update(signup_to_first_listing_min=_median([]), signup_to_first_lead_min=_median([]), demo_agencies_left_out=0)
    return z


def _mins(m):
    if m['median'] is None:
        return 'sin datos todavía'
    v = m['median']
    when = '%.0f min' % v if v < 120 else ('%.1f h' % (v / 60.0) if v < 2880 else '%.1f días' % (v / 1440.0))
    return '%s (%d agencia%s)' % (when, m['n'], '' if m['n'] == 1 else 's')


def render_text(f, now=None):
    total = f['agencies']
    lines = ['Embudo de Ficha Única, %s UTC' % (now or datetime.datetime.utcnow()).strftime('%Y-%m-%d %H:%M'), '']
    for key, label in LABELS:
        pct = '' if key == 'agencies' else ('  %3d%%' % round(100.0 * f[key] / total) if total else '    -')
        lines.append('%-30s %5d%s' % (label, f[key], pct))
    lines += ['', 'Del registro a la primera propiedad: ' + _mins(f['signup_to_first_listing_min']),
              'Del registro al primer cliente:      ' + _mins(f['signup_to_first_lead_min'])]
    if f['demo_agencies_left_out']:
        lines.append('(%d agencia%s de demostración no se cuenta%s)' % (f['demo_agencies_left_out'], '' if f['demo_agencies_left_out'] == 1 else 's',
                                                                      '' if f['demo_agencies_left_out'] == 1 else 'n'))
    return '\n'.join(lines)


def main(argv=None, out=print, now=None):
    ap = argparse.ArgumentParser(description='El embudo de Ficha Única: solo lectura, sin datos personales.')
    ap.add_argument('--db', default=None, help='ruta de la base (por defecto LLAVE_DB, como la app)')
    ap.add_argument('--json', action='store_true', help='salida en JSON')
    args = ap.parse_args(argv)
    path = args.db or db.DB_PATH
    try:
        con = open_ro(path)
        try:
            f = collect(con)
        finally:
            con.close()
    except sqlite3.Error as ex:
        sys.stderr.write('No pude leer la base (solo lectura): %s\n' % ex)
        return 2
    if args.json:
        out(json.dumps(dict(f, generated_at=(now or datetime.datetime.utcnow()).strftime('%Y-%m-%dT%H:%M:%SZ')), ensure_ascii=False, sort_keys=True))  # one line: fits a daily .jsonl log
    else:
        out(render_text(f, now))
    return 0


if __name__ == '__main__':
    sys.exit(main())
