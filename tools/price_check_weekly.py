#!/usr/bin/env python3
"""Weekly price check on data/llave.db (a future cron calls this). Dry-run outbox only."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import db, price_check  # noqa: E402

if __name__ == '__main__':
    con = db.connect(db.DB_PATH)  # LLAVE_DB on the server
    db.init(con)
    print(price_check.weekly_run(con))
