import unittest
from tools import ghl_snapshot_setup as s


class SnapshotPlan(unittest.TestCase):
    def test_empty_account_creates_everything(self):
        plan = s.build_plan({})
        self.assertTrue(all(x['action'] == 'create' for x in plan))
        self.assertEqual(sum(x['kind'] == 'pipeline' for x in plan), 3)
        self.assertEqual(sum(x['kind'] == 'custom_field' for x in plan), 8)
        self.assertEqual(sum(x['kind'] == 'tag' for x in plan), len(s.TAGS))

    def test_existing_items_are_skipped(self):
        ex = {'pipelines': ['compradores'], 'custom_fields': ['contact.fu_agent', 'FU Budget'], 'tags': ['FU-Lead']}
        plan = {(x['kind'], x['name']): x['action'] for x in s.build_plan(ex)}
        self.assertEqual(plan[('pipeline', 'Compradores')], 'skip')
        self.assertEqual(plan[('pipeline', 'Rentas')], 'create')
        self.assertEqual(plan[('custom_field', 'fu_agent')], 'skip')
        self.assertEqual(plan[('custom_field', 'fu_budget')], 'skip')
        self.assertEqual(plan[('tag', 'fu-lead')], 'skip')

    def test_idempotent_second_run_is_all_skip(self):
        first = s.build_plan({})
        ex = {'pipelines': [x['name'] for x in first if x['kind'] == 'pipeline'],
              'custom_fields': [x['payload']['fieldKey'] for x in first if x['kind'] == 'custom_field'],
              'tags': [x['name'] for x in first if x['kind'] == 'tag']}
        self.assertTrue(all(x['action'] == 'skip' for x in s.build_plan(ex)))

    def test_apply_refused_without_approval(self):
        import os
        for k in ('FU_GHL_TOKEN', 'FU_GHL_LOCATION_ID', 'FU_GHL_APPLY_APPROVED'):
            os.environ.pop(k, None)
        self.assertEqual(s.main(['--apply']), 2)
        self.assertEqual(s.main([]), 0)

    def test_stage_names(self):
        self.assertEqual(s.PIPELINES['Compradores'][-2:], ['Cerrado ganado', 'Cerrado perdido'])
        self.assertEqual(len(s.PIPELINES['Rentas']), 7)


if __name__ == '__main__':
    unittest.main()
