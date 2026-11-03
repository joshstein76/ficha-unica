#!/usr/bin/env python3
"""Check the DNS of every Pro agent's own domain (cron, every 10 minutes; see deploy/crontab.example and docs/CUSTOM-DOMAINS.md).
- A pending domain whose www now resolves ONLY to our IP (LLAVE_PUBLIC_IP) becomes verified, and we visit it once so Caddy gets its certificate.
- A verified domain that stops resolving for 3 checks in a row is unverified: the site goes back to the free address, nothing is deleted,
  the panel shows a notice, and the domain comes back by itself when DNS is right again.
- A lookup that FAILS (resolver down) never counts against anyone; only a definite 'no such record' or 'another address' does.
Uses the standard library resolver (socket) and, only in production with LLAVE_PUBLIC_IP set, one TLS connection to our own server per
new domain. Sends nothing to anybody. Usage: python3 tools/domain_check_run.py"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import db, domains  # noqa: E402


def main(con=None, resolver=None, warm=None, now=None, out=print):
    """resolver/warm/now are injected by the tests; on the server they are the real ones."""
    con = con or db.connect(db.DB_PATH)  # LLAVE_DB on the server
    db.init(con)
    summary = domains.run_all(con, resolver=resolver, now=now, warm=warm)
    out('domain_check ' + json.dumps(summary, sort_keys=True))
    return summary


if __name__ == '__main__':
    main()
