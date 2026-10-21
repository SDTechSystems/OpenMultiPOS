import unittest

from open_multi_pos.sku import business_initials, product_segment, sku_code, validate_prefix


class SKUTests(unittest.TestCase):
    def test_initials_preserve_short_acronyms_and_strip_accents(self):
        self.assertEqual(business_initials("AB Taller Demostración"), "ABTD")
        self.assertEqual(business_initials("La Casa del Árbol"), "CA")
        self.assertEqual(business_initials("123 comercio"), "N1C")
        self.assertEqual(business_initials(""), "N")

    def test_product_data_and_prefix_are_short_safe_ascii(self):
        self.assertEqual(sku_code("TD", "Café ámbar 250 ml", "00007"), "TD-CAFE-AMBAR-250-ML-00007")
        self.assertEqual(product_segment("!!!"), "PRODUCTO")
        self.assertLessEqual(len(product_segment("artículo " * 20)), 24)
        for value in ("", "abc", "A-B", "1A", "A" * 9, "ÁB", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_prefix(value)
