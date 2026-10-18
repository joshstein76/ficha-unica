import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import db  # noqa: E402
from llave.ai import budget, client  # noqa: E402


def fake_ok(model='claude-opus-5-5', inp=1000, out=1000):
    def t(url, headers, body):
        return 200, json.dumps({'model': model, 'stop_reason': 'end_turn', 'usage': {'input_tokens': inp, 'output_tokens': out},
                                'content': [{'type': 'text', 'text': '{"ok": true}'}]}).encode()
    return t


class Budget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = db.connect(os.path.join(self.tmp, 'b.db'))
        db.init(self.con)
        self.watch = os.path.join(self.tmp, 'WATCHDOG.md')
        os.environ['LLAVE_WATCHDOG_FILE'] = self.watch
        os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-test-' + 'x' * 30
        os.environ['LLAVE_AI_MONTHLY_CAP_USD'] = '1'

    def tearDown(self):
        for k in ('LLAVE_WATCHDOG_FILE', 'ANTHROPIC_API_KEY', 'LLAVE_AI_MONTHLY_CAP_USD', 'LLAVE_AI_LIVE'):
            os.environ.pop(k, None)

    def test_cost_and_record(self):
        self.assertAlmostEqual(budget.cost('claude-opus-5-5', 1_000_000, 1_000_000), 24.0)
        total = budget.record(self.con, 'claude-opus-5-5', {'input_tokens': 10000, 'output_tokens': 10000})
        self.assertAlmostEqual(total, 0.24)

    def test_calls_recorded_and_alert_at_80(self):
        os.environ['LLAVE_AI_MONTHLY_CAP_USD'] = '1.2'   # 80% = $0.96
        for _ in range(3):   # 3 x $0.24 = $0.72
            client.complete_json('s', 'u', {'type': 'object', 'properties': {}, 'additionalProperties': False, 'required': []},
                                 transport=fake_ok(inp=10000, out=10000), budget_con=self.con)
        self.assertFalse(os.path.exists(self.watch))
        client.complete_json('s', 'u', {'type': 'object', 'properties': {}, 'additionalProperties': False, 'required': []},
                             transport=fake_ok(inp=10000, out=10000), budget_con=self.con)   # $0.96 -> crosses 80%
        self.assertIn('AI spend at 80% of the monthly cap', open(self.watch).read())
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM outbox WHERE kind='alert.ai_budget'").fetchone()[0], 1)

    def test_hard_cap_blocks_before_sending(self):
        budget.record(self.con, 'claude-opus-5-5', {'input_tokens': 0, 'output_tokens': 40000})   # $0.80
        sent = []
        def t(url, headers, body):
            sent.append(1)
            return fake_ok()(url, headers, body)
        with self.assertRaises(client.AIUnavailable):
            client.complete_json('s', 'u', {'type': 'object', 'properties': {}, 'additionalProperties': False, 'required': []},
                                 transport=t, budget_con=self.con)   # worst case 16000 out = $0.32 -> would exceed $1
        self.assertEqual(sent, [])
        os.environ['LLAVE_AI_LIVE'] = '1'
        self.assertFalse(client.enabled(self.con))


if __name__ == '__main__':
    unittest.main()
