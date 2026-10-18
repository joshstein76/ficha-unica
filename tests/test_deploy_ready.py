"""Deploy-readiness guards: no secrets in git, templates present, prices consistent, no competitor names in user-facing code."""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave.web import panel  # noqa: E402

COMPETITORS = re.compile(r'easy\s*broker|idxboost|wiggot', re.I)


def tracked():
    try:
        out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split('\n')
    except Exception:
        raise unittest.SkipTest('not a git checkout')
    return [f for f in out if f]


class DeployReady(unittest.TestCase):
    def test_templates_present(self):
        for f in ('deploy/app.env.example', 'deploy/target.env.example', 'deploy/Caddyfile', 'deploy/deploy.sh',
                  'deploy/fichaunica.service', 'deploy/crontab.example', 'config/anthropic.env.example'):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, f)), f)

    def test_no_secrets_or_env_files_committed(self):
        pat = re.compile(r'sk-ant-[A-Za-z0-9_-]{20,}|sk_live_|AKIA[0-9A-Z]{16}|pit-[0-9a-f]{8}-[0-9a-f]{4}')
        for f in tracked():
            self.assertFalse(re.search(r'(^|/)[^/]*\.env$|\.local\.md$|\.db$', f), 'secret-ish file tracked: ' + f)
            p = os.path.join(ROOT, f)
            if f.endswith(('.png', '.jpg', '.webp', '.gz')) or f == 'tests/test_deploy_ready.py' or not os.path.isfile(p):
                continue
            with open(p, errors='ignore') as fh:
                self.assertIsNone(pat.search(fh.read()), 'secret pattern in ' + f)

    def test_anthropic_placeholder_documented_and_empty(self):
        with open(os.path.join(ROOT, 'config/anthropic.env.example')) as fh:
            txt = fh.read()
        self.assertRegex(txt, r'(?m)^ANTHROPIC_API_KEY=$')
        with open(os.path.join(ROOT, 'deploy/app.env.example')) as fh:
            app = fh.read()
        self.assertIn('LLAVE_AI_LIVE', app)
        self.assertIn('anthropic.env', app)

    def test_plan_prices_and_coming_soon(self):
        prices = {k: p for k, _, p, _ in panel.PLANS}
        self.assertEqual(prices, {'gratis': 0, 'pro': 299, 'agencia': 799, 'pro_crm': 999})
        self.assertEqual(panel.COMING_SOON, {'pro_crm'})

    def test_prices_consistent_in_docs(self):
        with open(os.path.join(ROOT, 'docs/DECISIONS.md')) as fh:
            txt = fh.read()
        self.assertIn('MXN 299', txt)
        self.assertIn('MXN 799', txt)
        self.assertIn('MXN 999', txt)
        # no other MXN plan price in user-facing code
        for sub in ('llave/web', 'llave/emails.py', 'llave/cards.py'):
            base = os.path.join(ROOT, sub)
            files = [base] if os.path.isfile(base) else [os.path.join(d, n) for d, _, ns in os.walk(base) for n in ns if n.endswith('.py')]
            for p in files:
                with open(p) as fh:
                    for m in re.finditer(r'\$\s?(\d{3,4})\s?MXN', fh.read()):
                        self.assertIn(int(m.group(1)), (299, 799, 999), p)

    def test_no_competitor_names_in_user_facing_code(self):
        for d, _, ns in os.walk(os.path.join(ROOT, 'llave')):
            for n in ns:
                if n.endswith(('.py', '.html', '.txt', '.sql')):
                    p = os.path.join(d, n)
                    with open(p, errors='ignore') as fh:
                        self.assertIsNone(COMPETITORS.search(fh.read()), p)


if __name__ == '__main__':
    unittest.main()
