#!/usr/bin/env python3
"""Set an agency's plan by hand, with an audit row (pilot agents get Pro free, Josh 10-21).
Usage: python3 tools/set_plan.py <slug> <gratis|pro|ia> --reason <why> [--until YYYY-MM-DD]
       python3 tools/set_plan.py --list      (agencies on a dated free plan, soonest end first)"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db, ghl_live  # noqa: E402


def opt(args, name):
    if name in args and args.index(name) + 1 < len(args):
        return args[args.index(name) + 1].strip()
    return None


def main(args, con=None):
    con = con or db.connect()
    db.init(con)
    if '--list' in args:
        rows = con.execute("SELECT slug, plan, plan_until FROM agencies WHERE plan_until IS NOT NULL ORDER BY plan_until").fetchall()
        for r in rows:
            print('%s  %s  hasta %s  (%s días)' % (r['slug'], r['plan'], r['plan_until'], db.plan_days_left(r)))
        if not rows:
            print('ninguna')
        return 0
    if len(args) < 2 or args[1] not in db.PLAN_LIMITS:
        print(__doc__)
        return 2
    slug, plan, reason, until = args[0], args[1], opt(args, '--reason'), opt(args, '--until')
    if not reason:
        print('falta --reason (queda en la auditoría)')
        return 2
    if until:
        try:
            datetime.date.fromisoformat(until)
        except ValueError:
            print('--until debe ser YYYY-MM-DD')
            return 2
    a = con.execute('SELECT id, plan, plan_until, stripe_subscription_id FROM agencies WHERE slug=?', (slug,)).fetchone()
    if not a:
        print('no existe esa agencia')
        return 1
    if a['stripe_subscription_id']:
        print('ojo: tiene suscripción en Stripe; Stripe puede volver a cambiar el plan')
    con.execute('UPDATE agencies SET plan=?, plan_until=? WHERE id=?', (plan, until, a['id']))
    db.audit(con, 'cli', 'plan_change', '%s: %s -> %s (hasta %s) motivo: %s' % (slug, a['plan'], plan, until or '-', reason))
    con.commit()
    ghl_live.plan_changed(con, a['id'])
    print('ok: %s ahora %s%s' % (slug, plan, ' hasta ' + until if until else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
