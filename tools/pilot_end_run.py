#!/usr/bin/env python3
"""A free pilot plan (tools/set_plan.py --until) has ended: the agency goes to Gratis. Nothing is deleted and nothing is sent; what's over
the limit waits, hidden, until they choose a plan. Daily cron.
It waits while paid plans are closed (Stripe off or a test key): nobody loses anything when they have no way to pay to keep it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import billing, db, ghl_live  # noqa: E402
from llave.feeds import mercadolibre  # noqa: E402


def payments_open():
    return billing.enabled() and not billing.test_lock_active()


def main(con=None, today=None):
    con = con or db.connect()
    db.init(con)
    if not payments_open():
        print('pilot_end esperando: los planes de pago están cerrados')
        return 0
    today = today or db.today_cdmx().isoformat()
    rows = con.execute("SELECT id, slug, plan, plan_until FROM agencies WHERE plan_until IS NOT NULL AND plan_until < ? AND plan <> 'gratis' "
                       "AND (stripe_subscription_id IS NULL OR stripe_subscription_id = '')", (today,)).fetchall()
    for r in rows:
        con.execute("UPDATE agencies SET plan='gratis', plan_until=NULL WHERE id=?", (r['id'],))
        db.audit(con, 'cron', 'plan_change', '%s: %s -> gratis (piloto terminó el %s)' % (r['slug'], r['plan'], r['plan_until']))
        con.commit()
        ghl_live.plan_changed(con, r['id'])
        mercadolibre.sync_plan_limit_safe(con, r['id'])
    print('pilot_end %d agencia(s) a Gratis' % len(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
