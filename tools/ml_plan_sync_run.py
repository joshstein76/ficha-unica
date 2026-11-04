#!/usr/bin/env python3
"""Safety net for the Mercado Libre pause / reactivate sync (cron, hourly; see deploy/crontab.example).
Every place that changes a plan already calls llave.feeds.mercadolibre.sync_plan_limit_safe right after the change. This sweep repeats it for every
agency with a published Mercado Libre item, so a sync that failed once, or a limit that moved without a plan change (a referral bonus, a
RentaPóliza credit), is caught within the hour. It is idempotent: nothing is queued twice.
DRY RUN ONLY: it writes outbox rows (portal.mercadolibre.pause / .reactivate, status dry_run) and never touches the network or Mercado Libre.
Usage: python3 tools/ml_plan_sync_run.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db  # noqa: E402
from llave.feeds import mercadolibre  # noqa: E402


def main(con=None, out=print):
    con = con or db.connect(db.DB_PATH)  # LLAVE_DB on the server
    db.init(con)
    queued = mercadolibre.sync_all(con)
    out('ml_plan_sync ' + json.dumps({'agencias': len(queued), 'pausar': sum(len(r['pause']) for r in queued.values()),
                                       'reactivar': sum(len(r['reactivate']) for r in queued.values())}, sort_keys=True))
    return queued


if __name__ == '__main__':
    main()
