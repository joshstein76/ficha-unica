"""Ecosistema: DRY-RUN planner for the shared GHL tag scheme. Prints the plan; never reads tokens, never writes.

  python3 tools/eco_ghl_tags.py [--json]
Each sub-account is known only by the NAME of its env var (the token itself is never read).
"""
import json
import sys

# sub-account label -> (brand key, env var NAME for its token)
SUBACCOUNTS = {
    'Ficha Única (agentes)': ('fichaunica', 'FU_GHL_TOKEN'),
    'VIVE Polanco':          ('vive', 'VIVE_GHL_TOKEN'),
    'Ciao Bella Marketing':  ('ciaobella', 'CB_GHL_TOKEN'),
    'IDX Bloom':             ('idxbloom', 'IDXB_GHL_TOKEN'),
    'Cerquito':              ('cerquito', 'CERQ_GHL_TOKEN'),
    'RentaPóliza':           ('rentapoliza', 'RP_GHL_TOKEN'),   # on hold: plan only
}
BRANDS = [b for b, _ in SUBACCOUNTS.values()]


def plan():
    out = []
    for label, (brand, env) in SUBACCOUNTS.items():
        tags = ['eco-source-' + brand, 'eco-cliente-' + brand]
        tags += ['eco-referral-%s-%s' % (other, brand) for other in BRANDS if other != brand]   # arriving from
        tags += ['eco-referral-%s-%s' % (brand, other) for other in BRANDS if other != brand]   # leaving to
        out.append({'subaccount': label, 'token_env': env, 'tags': sorted(set(tags)),
                    'on_hold': brand == 'rentapoliza', 'action': 'DRY-RUN: crear solo las etiquetas que falten'})
    return out


def main(argv):
    p = plan()
    if '--json' in argv:
        print(json.dumps(p, ensure_ascii=False, indent=2))
        return 0
    print('PLAN (dry-run, nada se escribe, ningún token se lee)')
    for s in p:
        print('\n%s  [token: $%s]%s' % (s['subaccount'], s['token_env'], '  (en pausa: solo plan)' if s['on_hold'] else ''))
        for t in s['tags']:
            print('  + ' + t)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
