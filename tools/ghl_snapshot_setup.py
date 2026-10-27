#!/usr/bin/env python3
"""Ficha Unica platform sub-account: idempotent setup of the API-scriptable parts (custom fields + tags; pipelines are listed to create by hand).

DRY-RUN by default: prints the plan, writes nothing. Existing items are read (GET) first so nothing is duplicated.
Writes happen only with BOTH the --apply flag AND env FU_GHL_APPLY_APPROVED=1.
Env: FU_GHL_TOKEN (location-level Private Integration token), FU_GHL_LOCATION_ID. Secrets are never printed.
Workflows, Conversation AI, calendars, email templates, snapshot creation are UI-only (see docs/GHL-AGENT-SNAPSHOT.md).
"""
import argparse, json, os, subprocess, sys

BASE = 'https://services.leadconnectorhq.com'

# Platform sub-account "Ficha Única": agents are our customers, site leads are copied here (llave/ghl_live.py).
PIPELINES = {
    'Agentes': ['Registrado', 'Primera propiedad publicada', 'Pro', 'Pro + IA', 'Canceló'],
    'Leads de sitios': ['Nuevo', 'Contactado por el asesor', 'Visita', 'Cerrado', 'Perdido'],
}

# (fieldKey suffix, display name, dataType)
CUSTOM_FIELDS = [
    ('fu_agency_slug', 'FU Agency Slug', 'TEXT'),
    ('fu_plan', 'FU Plan', 'TEXT'),
    ('fu_site_url', 'FU Site URL', 'TEXT'),
    ('fu_listings_published', 'FU Listings Published', 'NUMERICAL'),
    ('fu_listing_ref', 'FU Listing Ref', 'TEXT'),
    ('fu_listing_url', 'FU Listing URL', 'TEXT'),
    ('fu_agent', 'FU Agent', 'TEXT'),
    ('fu_source', 'FU Source', 'TEXT'),
]

TAGS = ['fu-agente', 'fu-plan-gratis', 'fu-plan-pro', 'fu-plan-ia', 'fu-lead', 'fu-venta', 'fu-renta', 'fu-no-contactar']
# fu-agencia-<slug> is created on demand per agency, not here.


def norm(s):
    return (s or '').strip().lower()


def build_plan(existing):
    """existing = {'pipelines': [names], 'custom_fields': [names or keys], 'tags': [names]} -> list of action dicts."""
    have_p = {norm(x) for x in existing.get('pipelines', [])}
    have_f = {norm(x).replace('contact.', '') for x in existing.get('custom_fields', [])}
    have_t = {norm(x) for x in existing.get('tags', [])}
    plan = []
    for name, stages in PIPELINES.items():
        # GHL's public API may not create pipelines: they are only listed ("CREATE IN UI"), never POSTed
        plan.append({'kind': 'pipeline', 'name': name, 'action': 'skip' if norm(name) in have_p else 'ui',
                     'stages': stages})
    for key, label, dtype in CUSTOM_FIELDS:
        exists = norm(key) in have_f or norm(label) in have_f
        plan.append({'kind': 'custom_field', 'name': key, 'action': 'skip' if exists else 'create',
                     'payload': {'name': label, 'dataType': dtype, 'model': 'contact', 'fieldKey': 'contact.' + key}})
    for t in TAGS:
        plan.append({'kind': 'tag', 'name': t, 'action': 'skip' if norm(t) in have_t else 'create',
                     'payload': {'name': t}})
    return plan


def call(method, tok, path, body=None):
    cmd = ['curl', '-s', '-m', '30', '-A', 'curl/8.4.0', '-X', method, '-H', 'Authorization: Bearer ' + tok,
           '-H', 'Version: 2021-07-28', '-H', 'Accept: application/json']
    if body is not None:
        cmd += ['-H', 'Content-Type: application/json', '-d', json.dumps(body)]
    r = subprocess.run(cmd + [BASE + path], capture_output=True, text=True, timeout=45)
    try:
        return json.loads(r.stdout or '{}')
    except Exception:
        return {'_error': 'non-json response'}


def fetch_existing(tok, loc):
    p = call('GET', tok, '/opportunities/pipelines?locationId=' + loc)
    f = call('GET', tok, '/locations/%s/customFields' % loc)
    t = call('GET', tok, '/locations/%s/tags' % loc)
    return {
        'pipelines': [x.get('name', '') for x in p.get('pipelines', [])],
        'custom_fields': [x.get('fieldKey', '') or x.get('name', '') for x in f.get('customFields', [])]
                         + [x.get('name', '') for x in f.get('customFields', [])],
        'tags': [x.get('name', '') for x in t.get('tags', [])],
    }


def apply_plan(plan, tok, loc):
    paths = {'custom_field': '/locations/%s/customFields' % loc,
             'tag': '/locations/%s/tags' % loc}
    for a in plan:
        if a['action'] != 'create':
            continue
        res = call('POST', tok, paths[a['kind']], dict(a['payload']))
        print('  %s %s -> %s' % (a['kind'], a['name'], 'ERROR' if res.get('_error') or res.get('statusCode') else 'ok'))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--apply', action='store_true', help='write to GHL (also needs FU_GHL_APPLY_APPROVED=1)')
    a = ap.parse_args(argv)
    tok, loc = os.environ.get('FU_GHL_TOKEN', ''), os.environ.get('FU_GHL_LOCATION_ID', '')
    approved = os.environ.get('FU_GHL_APPLY_APPROVED') == '1'
    have_creds = bool(tok and loc)
    print('token:', 'present' if tok else 'absent', '| location:', 'present' if loc else 'absent')
    existing = fetch_existing(tok, loc) if have_creds else {}
    if not have_creds:
        print('No credentials: planning against an EMPTY account (offline).')
    plan = build_plan(existing)
    for x in plan:
        if x['action'] == 'ui':
            print('  CREATE IN UI: %s: %s' % (x['name'], ', '.join(x['stages'])))
        else:
            print('  [%s] %s: %s' % (x['action'].upper(), x['kind'], x['name']))
    print('UI-only (not scripted): workflows, Conversation AI bot, calendars, email templates, forms, reputation, dashboard, snapshot creation.')
    todo = sum(1 for x in plan if x['action'] == 'create')
    if not a.apply:
        print('DRY-RUN: %d to create, nothing written.' % todo)
        return 0
    if not (approved and have_creds):
        print('REFUSED: --apply needs FU_GHL_APPLY_APPROVED=1 and FU_GHL_TOKEN + FU_GHL_LOCATION_ID. Nothing written.')
        return 2
    apply_plan(plan, tok, loc)
    return 0


if __name__ == '__main__':
    sys.exit(main())
