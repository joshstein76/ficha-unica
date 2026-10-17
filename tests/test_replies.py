import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import replies  # noqa: E402

AG = {'name': 'Casas Roma', 'first_reply': None, 'first_reply_noname': None}


class Replies(unittest.TestCase):
    def test_default_is_josh_approved_text(self):
        t = replies.render(AG, 'ana pérez', 'Depto en la Roma', 'María López')
        self.assertEqual(t, 'Hola Ana, gracias por escribir sobre Depto en la Roma. Soy María de Casas Roma. '
                            '¿Le comparto más fotos y detalles por aquí o prefiere agendar una visita?')

    def test_no_name_variant_and_bad_names(self):
        for raw in ('', '@ana_88', 'ana@x.com', '5512345678', '🏠'):
            self.assertTrue(replies.render(AG, raw, 'Depto', 'María').startswith('Hola, gracias por escribir sobre Depto.'), raw)

    def test_team_account(self):
        self.assertIn('Somos Casas Roma.', replies.render(AG, 'Ana', 'X', 'Equipo Casas'))

    def test_custom_and_check(self):
        ag = dict(AG, first_reply='¡Qué tal {nombre}! Te escribe {asesor}.')
        self.assertEqual(replies.render(ag, 'Luis', 'X', 'Pedro Gómez'), '¡Qué tal Luis! Te escribe Pedro.')
        self.assertIn('{precio}', replies.check('Hola {precio}'))
        self.assertTrue(replies.check('Hola {nombre}', need_name=False))
        self.assertEqual(replies.check(replies.DEFAULT_FIRST_REPLY), '')


if __name__ == '__main__':
    unittest.main()
