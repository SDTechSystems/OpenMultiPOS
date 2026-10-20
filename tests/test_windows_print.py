import unittest

from open_multi_pos.windows_print import escpos_raster, parse_pbm


class RasterTests(unittest.TestCase):
    def test_raster_chunks_preserve_all_rows_and_dimensions(self):
        rows = bytes(range(256)) + b"\xff"
        pbm = b"P4\n8 257\n" + rows
        job = escpos_raster(pbm, max_dots=384)
        self.assertTrue(job.startswith(b"\x1b@\x1ba\x00"))
        offset, reconstructed, heights = 5, bytearray(), []
        while job[offset : offset + 4] == b"\x1dv0\x00":
            stride = int.from_bytes(job[offset + 4 : offset + 6], "little")
            height = int.from_bytes(job[offset + 6 : offset + 8], "little")
            self.assertEqual(stride, 1)
            heights.append(height)
            reconstructed.extend(job[offset + 8 : offset + 8 + stride * height])
            offset += 8 + stride * height
        self.assertEqual(heights, [128, 128, 1])
        self.assertEqual(bytes(reconstructed), rows)
        self.assertEqual(job[offset:], b"\n")

    def test_invalid_or_truncated_raster_rejected(self):
        for payload in (
            b"P1\n8 1\n0",
            b"P4\n7 1\n\x00",
            b"P4\n8 2\n\x00",
            b"P4\n8 1\n\x00extra",
            b"P4\nBAD\n",
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_pbm(payload)
        with self.assertRaises(ValueError):
            escpos_raster(b"P4\n392 1\n" + b"\x00" * 49, max_dots=384)
