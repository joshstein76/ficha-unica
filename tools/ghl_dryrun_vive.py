#!/usr/bin/env python3
"""READ-ONLY check of VIVE's GHL sub-account vs what LLAVE would create. Only GETs. Never prints the token."""
import json, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import db, ghl  # noqa: E402

ENV = '/Users/joshstein/Desktop/Claude Ledger/josh-command-center/clients/vive-polanco/config/vive-ghl.env'
BASE = 'https://services.leadconnectorhq.com'
KEYS = ['llave_listing_ref', 'llave_listing_url', 'llave_lead_source']


def readenv(p):
    out = {}
    for ln in open(p, encoding='utf-8'):
        ln = ln.strip()
        if ln and not ln.startswith('#') and '=' in ln:
            k, v = ln.split('=', 1)
            out[k.strip()] = v.strip().strip('"\'')
    return out


def get(tok, path):
    r = subprocess.run(['curl', '-s', '-m', '30', '-A', 'curl/8.4.0', '-X', 'GET', '-H', 'Authorization: Bearer ' + tok,
                        '-H', 'Version: 2021-07-28', '-H', 'Accept: application/json', BASE + path],
                       capture_output=True, text=True, timeout=45)
    try:
        return json.loads(r.stdout or '{}')
    except Exception:
        return {'_error': 'non-json response'}


def main():
    env = readenv(ENV)
    tok, loc = env.get('VIVE_GHL_TOKEN', ''), env.get('VIVE_GHL_LOCATION_ID', '')
    print('token:', 'present' if tok else 'absent', '| location id:', 'present' if loc else 'absent')
    if not (tok and loc):
        sys.exit(1)
    L = ['# LLAVE GHL dry-run vs VIVE (read-only) 2026-10-17', '', 'Only GET requests. No secrets, no contact data.', '']
    cf = get(tok, '/locations/%s/customFields' % loc)
    fields = cf.get('customFields') or []
    names = sorted(f.get('name', '') for f in fields)
    found = {k: any(k in (f.get('fieldKey', '') + f.get('name', '')).lower().replace(' ', '_') for f in fields) for k in KEYS}
    L += ['## Custom fields', 'Total fields in location: %d%s' % (len(fields), ' (API error: %s)' % cf.get('message', cf.get('_error')) if not fields and ('message' in cf or '_error' in cf) else '')]
    L += ['- %s: %s' % (k, 'EXISTS' if v else 'missing') for k, v in found.items()] + ['', 'Field names: ' + ', '.join(names), '']
    time.sleep(1)
    pp = get(tok, '/opportunities/pipelines?locationId=%s' % loc)
    pipes = [p.get('name', '') for p in pp.get('pipelines') or []]
    L += ['## Pipelines (%d)' % len(pipes)] + ['- ' + n for n in pipes]
    L += ['', "'LLAVE Leads' exists: %s (expected no)" % ('yes' if 'LLAVE Leads' in pipes else 'no'), '']
    canon = None
    dbp = db.DB_PATH
    if os.path.exists(dbp):
        try:
            con = db.connect(dbp)
            r = con.execute("SELECT id FROM listings WHERE title LIKE '%Her_clito%' LIMIT 1").fetchone()
            canon = db.canonical(con, r['id']) if r else None
        except Exception:
            canon = None
    src = 'data/llave.db'
    if not canon:
        src = 'hard-coded'
        canon = {'ref': 'VIVE-HERACLITO', 'title': 'Departamento en Heráclito, Polanco', 'operation': 'venta',
                 'url': 'http://vive.fichaunica.localhost:8640/propiedad/heraclito', 'price': None, 'currency': 'MXN',
                 'price_date': None, 'address': {'colonia': 'Polanco'}}
    lead = {'name': 'Cliente Prueba', 'phone': '+520000000000', 'email': '', 'message': 'Prueba', 'source': 'sitio'}
    agency = {'id': 0, 'slug': 'vive', 'name': 'VIVE Polanco', 'whatsapp': None, 'ghl_location_id': loc}
    L += ['## Plan for a fake lead (listing from %s), NOT sent' % src]
    for op in ghl.plan_for_lead(lead, canon, agency):
        b = op.get('body') or {}
        line = '- %s | body keys: %s' % (op['kind'], ', '.join(sorted(b)) or '(none)')
        if b.get('tags'):
            line += ' | tags: ' + ', '.join(b['tags'])
        if op.get('status'):
            line += ' | status: ' + op['status']
        L.append(line)
    L += ['', 'NO WRITES MADE']
    txt = '\n'.join(L)
    print(txt)
    with open(os.path.join(ROOT, 'docs', 'ghl-dryrun-vive-2026-10-17.md'), 'w', encoding='utf-8') as f:
        f.write(txt + '\n')


if __name__ == '__main__':
    main()
