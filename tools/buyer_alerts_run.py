#!/usr/bin/env python3
"""Match buyer alerts to new public listings; queue agency alerts (dry-run). Run hourly once production exists."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import alerts_buyers, db  # noqa: E402

con = db.connect()
print('coincidencias nuevas:', alerts_buyers.run(con))
