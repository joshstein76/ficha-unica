import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llave import emails  # noqa: E402


class Subjects(unittest.TestCase):
    def test_outreach_slash(self):
        self.assertEqual(emails.agent_invite('Casas Roma', 'Hola')['subject'], 'Ficha Única / Casas Roma')
        self.assertEqual(emails.outreach_subject('Ficha Única', ''), 'Ficha Única')

    def test_lead_first_name_plus_words(self):
        self.assertEqual(emails.to_lead({'name': 'VIVE Polanco'}, 'ana ruiz', 'a@b.mx', '3 fotos de Roma 12', 'x')['subject'],
                         'Ana, 3 fotos de Roma 12')
        self.assertEqual(emails.lead_subject('@ana_88', '¿martes o jueves?'), '¿martes o jueves?')  # never a handle
        self.assertEqual(emails.to_lead({'name': 'VIVE Polanco'}, 'Ana', 'a@b.mx', '3 fotos', 'x')['from_name'], 'VIVE Polanco')
        with self.assertRaises(ValueError):
            emails.lead_subject('Ana', 'hola')                     # 1 word
        with self.assertRaises(ValueError):
            emails.lead_subject('Ana', 'uno dos tres cuatro cinco seis')

    def test_transactional_and_rules(self):
        self.assertEqual(emails.transactional_subject('Su visita: martes 10:30'), 'Su visita: martes 10:30')
        self.assertLessEqual(len(emails.transactional_subject('x' * 80)), 40)
        self.assertEqual(emails.check('Ana, 3 fotos de Roma 12'), '')
        self.assertTrue(emails.check('Oferta GRATIS hoy'))
        self.assertTrue(emails.check('Ana, mira esto 🏠'))
        self.assertTrue(emails.check('URGENTE: Ana'))


if __name__ == '__main__':
    unittest.main()
