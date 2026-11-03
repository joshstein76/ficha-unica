"""The block list lives in a private file, never in this public code, and production refuses to look healthy without it."""
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from llave import db, ghl  # noqa: E402
from llave.web import server  # noqa: E402


class BlockList(unittest.TestCase):
    def terms_file(self, text):
        f = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8')
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def health(self):
        with mock.patch('llave.alerts.heartbeat', return_value={'ok': True, 'db_ok': True}):
            return server.health(None)

    def test_the_private_file_decides_who_is_blocked(self):
        path = self.terms_file('# a comment\nGrupo Ficticio\n\nana ficticia\n')
        with mock.patch.dict(os.environ, {'LLAVE_BLOCKLIST_FILE': path}):
            self.assertTrue(ghl.is_blocked('Ana Ficticia López'))
            self.assertTrue(ghl.is_blocked('Luis', '', 'Grupo Ficticio SA'))
            self.assertTrue(ghl.is_blocked('Luis', 'ana ficticia@x.test'))
            self.assertFalse(ghl.is_blocked('Laura Gómez', 'laura@x.test'))
            self.assertFalse(ghl.is_blocked('a comment'))

    def test_outside_production_only_a_made_up_name_is_blocked(self):
        env = {k: v for k, v in os.environ.items() if k != 'LLAVE_BLOCKLIST_FILE'}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(db, 'ENV', 'development'):
            self.assertTrue(ghl.is_blocked('Persona Bloqueada'))
            self.assertFalse(ghl.is_blocked('Laura Gómez'))

    def test_production_health_fails_without_the_list(self):
        env = {k: v for k, v in os.environ.items() if k != 'LLAVE_BLOCKLIST_FILE'}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(db, 'ENV', 'production'):
            self.assertEqual(ghl.block_terms(), ())
            self.assertFalse(self.health()['ok'])
        missing = {'LLAVE_BLOCKLIST_FILE': os.path.join(tempfile.gettempdir(), 'no-such-blocklist-file.txt')}
        with mock.patch.dict(os.environ, missing), mock.patch.object(db, 'ENV', 'production'):
            self.assertFalse(self.health()['ok'])

    def test_production_health_is_fine_with_the_list(self):
        with mock.patch.dict(os.environ, {'LLAVE_BLOCKLIST_FILE': self.terms_file('grupo ficticio\n')}), mock.patch.object(db, 'ENV', 'production'):
            self.assertTrue(self.health()['ok'])
            self.assertNotIn('blocklist_ok', self.health())


if __name__ == '__main__':
    unittest.main()
