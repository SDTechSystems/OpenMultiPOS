import unittest

from open_multi_pos.warranty_contract import change, creation, from_html, to_html

REQUEST = "0f8fad5b-d9cb-469f-a165-70867728950e"


class WarrantyContractTests(unittest.TestCase):
    def created(self):
        return {
            "brand": "Negocio ficticio",
            "invoice": "FAKE-SINV-1",
            "row": "fake-row-1",
            "request_id": REQUEST,
            "complaint": "  La vela ficticia no enciende\r\n  ",
            "complaint_date": "2026-10-21",
        }

    def changed(self):
        return {
            "brand": "Negocio ficticio",
            "claim": "SER-WRN-2026-00001",
            "modified": "2026-10-21 10:00:00.000000",
            "status": "Work In Progress",
            "resolution_details": "",
            "note": "Se revisa en mostrador",
        }

    def test_normalizes_creation(self):
        result = creation(self.created())
        self.assertEqual(result["complaint"], "La vela ficticia no enciende")
        self.assertEqual(result["complaint_date"], "2026-10-21")

    def test_rejects_invalid_creation(self):
        for field, values in {
            "request_id": ["1", "0f8fad5b-d9cb-169f-a165-70867728950e", None],
            "complaint": ["", "   ", None, "x" * 2001, "a\x00b"],
            "complaint_date": ["21/10/2026", "2026-02-30", "", 20261021],
            "row": ["", None, "x" * 141],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    data = self.created()
                    data[field] = value
                    creation(data)

    def test_rejects_unknown_or_missing_fields(self):
        extra = {**self.created(), "customer": "Otro cliente"}
        missing = self.created()
        del missing["row"]
        for value in (extra, missing):
            with self.assertRaises(ValueError):
                creation(value)

    def test_change_requires_native_status_and_solution_to_close(self):
        self.assertEqual(change(self.changed())["status"], "Work In Progress")
        for status in ("Abierta", "", None, "Resolved"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                change({**self.changed(), "status": status})
        with self.assertRaises(ValueError):
            change({**self.changed(), "status": "Closed"})
        closed = change({**self.changed(), "status": "Closed", "resolution_details": "Cambio"})
        self.assertEqual(closed["resolution_details"], "Cambio")

    def test_change_limits_note(self):
        with self.assertRaises(ValueError):
            change({**self.changed(), "note": "x" * 1001})

    def test_text_editor_round_trip_escapes_markup(self):
        value = 'Línea <script>alert("x")</script>\nSegunda & "fin"'
        stored = to_html(value)
        self.assertNotIn("<script>", stored)
        self.assertEqual(from_html(stored), value)
        self.assertEqual(to_html(""), "")
        self.assertEqual(from_html("<div><p>Uno</p><p>Dos</p></div>"), "Uno\nDos")


if __name__ == "__main__":
    unittest.main()
