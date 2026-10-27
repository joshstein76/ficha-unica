import unittest
from tools import ghl_snapshot_setup as s


class SnapshotPlan(unittest.TestCase):
    def test_empty_account_creates_fields_and_tags_pipelines_are_ui(self):
        plan = s.build_plan({})
        self.assertEqual({x['action'] for x in plan if x['kind'] != 'pipeline'}, {'create'})
        self.assertEqual({x['action'] for x in plan if x['kind'] == 'pipeline'}, {'ui'})
        self.assertEqual(sum(x['kind'] == 'pipeline' for x in plan), 2)
        self.assertEqual(sum(x['kind'] == 'custom_field' for x in plan), 8)
        self.assertEqual(sum(x['kind'] == 'tag' for x in plan), len(s.TAGS))

    def test_existing_items_are_skipped(self):
        ex = {'pipelines': ['agentes'], 'custom_fields': ['contact.fu_plan', 'FU Site URL'], 'tags': ['FU-Lead']}
        plan = {(x['kind'], x['name']): x['action'] for x in s.build_plan(ex)}
        self.assertEqual(plan[('pipeline', 'Agentes')], 'skip')
        self.assertEqual(plan[('pipeline', 'Leads de sitios')], 'ui')
        self.assertEqual(plan[('custom_field', 'fu_plan')], 'skip')
        self.assertEqual(plan[('custom_field', 'fu_site_url')], 'skip')
        self.assertEqual(plan[('tag', 'fu-lead')], 'skip')

    def test_idempotent_second_run_is_all_skip(self):
        first = s.build_plan({})
        ex = {'pipelines': [x['name'] for x in first if x['kind'] == 'pipeline'],
              'custom_fields': [x['payload']['fieldKey'] for x in first if x['kind'] == 'custom_field'],
              'tags': [x['name'] for x in first if x['kind'] == 'tag']}
        self.assertTrue(all(x['action'] == 'skip' for x in s.build_plan(ex)))

    def test_pipelines_print_as_create_in_ui_and_are_never_posted(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            s.main([])
        out = buf.getvalue()
        self.assertIn('CREATE IN UI: Agentes: Registrado, Primera propiedad publicada, Pro, Pro + IA, Canceló', out)
        self.assertIn('CREATE IN UI: Leads de sitios: Nuevo, Contactado por el asesor, Visita, Cerrado, Perdido', out)
        posted = []
        s.call = lambda m, t, path, body=None: posted.append(path) or {}
        try:
            s.apply_plan(s.build_plan({}), 'tok', 'LOC')
        finally:
            del s.call
        self.assertFalse(any('pipelines' in p for p in posted))
        self.assertEqual(len(posted), 8 + len(s.TAGS))

    def test_apply_refused_without_approval(self):
        import os
        for k in ('FU_GHL_TOKEN', 'FU_GHL_LOCATION_ID', 'FU_GHL_APPLY_APPROVED'):
            os.environ.pop(k, None)
        self.assertEqual(s.main(['--apply']), 2)
        self.assertEqual(s.main([]), 0)

    def test_stage_names(self):
        self.assertEqual(s.PIPELINES['Agentes'][:2], ['Registrado', 'Primera propiedad publicada'])
        self.assertEqual(len(s.PIPELINES['Leads de sitios']), 5)

if __name__ == '__main__':
    unittest.main()
