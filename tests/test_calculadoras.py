import unittest

from llave import calculadoras as c


class Calculadoras(unittest.TestCase):
    def test_neta(self):
        r = c.neta('4,500,000', '5', '16', hipoteca='1,000,000', adeudos='12,000.50')
        # 5% of 4.5M = 225,000; IVA 16% = 36,000
        self.assertEqual(dict(r['rows'])['Comisión'], -22500000)
        self.assertEqual(dict(r['rows'])['IVA sobre la comisión'], -3600000)
        self.assertEqual(r['neto'], 450000000 - 22500000 - 3600000 - 100000000 - 1200050)

    def test_compra_has_no_default_isai(self):
        with self.assertRaises(ValueError):
            c.compra('2,000,000', '')
        r = c.compra('2,000,000', '3', honorarios='45,000')
        self.assertEqual(r['total'], 6000000 + 4500000)
        self.assertEqual(r['con_precio'], 200000000 + 10500000)

    def test_bad_input(self):
        for args in (('', '5', '16'), ('-1', '5', '16'), ('abc', '5', '16'), ('100', '150', '16'), ('100', '5', '')):
            with self.assertRaises(ValueError):
                c.neta(*args)

    def test_fmt(self):
        self.assertEqual(c.fmt(123456789), '$1,234,567.89 MXN')
        self.assertEqual(c.fmt(-5), '-$0.05 MXN')


if __name__ == '__main__':
    unittest.main()
