#!/usr/bin/env python3
"""Push pending Ficha Única contacts/leads to the platform GHL sub-account (cron every minute). Does nothing unless
LLAVE_GHL_LIVE=1 + FU_GHL_TOKEN + FU_GHL_LOCATION_ID are set. Never sends a message to anyone."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import db, ghl_live  # noqa: E402

if __name__ == '__main__':
    if not ghl_live.enabled():
        print('ghl sync off')
        sys.exit(0)
    con = db.connect(os.path.join(ROOT, 'data', 'llave.db'))
    db.init(con)
    queued = ghl_live.sweep_first_publish(con)
    print('first_publish queued: %d' % queued, ghl_live.drain(con))
