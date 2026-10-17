#!/usr/bin/env python3
"""Give a Ficha Única user the admin role (sees /admin: every agency, leads at risk). Usage: python3 tools/make_admin.py <email> [--off]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
con = db.connect()
role = 'owner' if '--off' in sys.argv else 'admin'
n = con.execute('UPDATE users SET role=? WHERE email=?', (role, sys.argv[1].strip().lower())).rowcount
db.audit(con, 'cli', 'role_change', '%s -> %s' % (sys.argv[1], role))
con.commit()
print('ok' if n else 'no existe ese correo')
