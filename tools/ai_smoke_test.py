#!/usr/bin/env python3
"""ONE real AI call (counts against the US$50/month cap): writes the Spanish description for VIVE's Heráclito demo listing
and prints the result + this month's spend. Never prints the key."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db  # noqa: E402
from llave.ai import budget, client, writer  # noqa: E402
from llave.web.server import load_local_env  # noqa: E402

load_local_env()
con = db.connect()
print('AI enabled:', client.enabled(con), '· cap US$%.0f · spent this month US$%.4f' % (budget.cap_usd(), budget.spent(con)))
lid = con.execute("SELECT id FROM listings WHERE ref='VIVE-0001'").fetchone()['id']
out = writer.describe(db.canonical(con, lid), 'es')
print('source:', out['source'], '· reason:', out.get('reason'))
print('title:', out['title'])
print('description:', out['description'])
print('highlights:', out['highlights'])
print('spent this month now US$%.4f' % budget.spent(con))
