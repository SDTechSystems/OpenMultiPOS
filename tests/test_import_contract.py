import unittest

from open_multi_pos.import_contract import COLUMNS, MAX_ROWS, parse


class ImportCSVTests(unittest.TestCase):
    def csv(self, row, delimiter=";"):
        return delimiter.join(COLUMNS) + "\r\n" + row

    def test_excel_bom_decimal_comma_leading_zero_and_blank_stock(self):
        rows, errors = parse(
            "\ufeff" + self.csv('crear;;Artículo ficticio;001234;Products;"2500,50";;')
        )
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["codigo_barras"], "001234")
        self.assertEqual(rows[0]["precio"], "2500.50")
        self.assertEqual(rows[0]["cantidad"], 0)
        self.assertEqual(rows[0]["line"], 2)

    def test_comma_and_tabs_quotes_and_blank_lines(self):
        for separator in (",", "\t"):
            text = separator.join(
                ["crear", "", '"Artículo, ficticio"', "", "Products", "2500.00", "2", "800.25"]
            )
            rows, errors = parse(self.csv(text, separator) + "\r\n\r\n")
            self.assertFalse(errors)
            self.assertEqual(rows[0]["nombre"], "Artículo, ficticio")
            self.assertEqual(rows[0]["costo"], "800.25")

    def test_bad_fields_report_line_without_applying_anything(self):
        for row in (
            "crear;;A;;Products;-1;0;",
            "crear;;A;;Products;1;1.5;2",
            "crear;;A;;Products;1;1;",
            "crear;;A;;Products;1;0;2",
            "crear;;=FORMULA;;Products;1;0;",
            "ingresar;SKU;Nombre;;;1;1;2",
            "actualizar;;;;;;;",
            "crear;;A;;Products;1e4;0;",
        ):
            with self.subTest(row=row):
                rows, errors = parse(self.csv(row))
                self.assertFalse(rows)
                self.assertEqual(errors[0]["line"], 2)

    def test_bad_header_encoding_and_bounds(self):
        for text in (
            "",
            "accion;sku\ncrear;X",
            "\x00",
            self.csv("crear;;A;;Products;1;0;") + "x" * (256 * 1024),
            self.csv("\n".join(["crear;;A;;Products;1;0;"] * (MAX_ROWS + 1))),
        ):
            with self.subTest(size=len(text)), self.assertRaises(ValueError):
                parse(text)

    def test_multiple_errors_keep_valid_rows_for_review(self):
        rows, errors = parse(
            self.csv(
                "crear;;A;;Products;1000;2;500\ncrear;;B;;Products;no;2;500\ncrear;;C;;Products;1000;-2;500"
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual([e["line"] for e in errors], [3, 4])
