#!/usr/bin/env python3
"""Queue 5-minute lead reminders + the daily 'seguimiento hoy' digest on data/llave.db (cron, every minute). Dry-run outbox only."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import db, lead_watch  # noqa: E402

if __name__ == '__main__':
    con = db.connect(db.DB_PATH)  # LLAVE_DB on the server
    db.init(con)
    print(lead_watch.remind(con), lead_watch.follow_up_digest(con))
