"""Verify actual PDF page boxes and all long-receipt markers, not only DOM layout."""

import sys
from pathlib import Path

from pypdf import PdfReader

root = Path(sys.argv[1] if len(sys.argv) > 1 else "test-results")
for profile, width in (("jaltech-jal58m", 48), ("generic-58", 58), ("generic-80", 80)):
    short = PdfReader(root / f"{profile}-short.pdf")
    assert len(short.pages) == 1
    box = short.pages[0].mediabox
    assert abs(float(box.width) * 25.4 / 72 - width) < 1
    assert float(box.height) * 25.4 / 72 < 130
    long = PdfReader(root / f"{profile}-long.pdf")
    text = "".join(page.extract_text() for page in long.pages)
    for line in range(1, 51):
        assert f"ITEM-{line:03}" in text, (profile, line)
    assert "END-OF-RECEIPT" in text, profile
    for page in long.pages:
        assert abs(float(page.mediabox.width) * 25.4 / 72 - width) < 1
        assert float(page.mediabox.height) * 25.4 / 72 < 281
    print(
        f"PASS {profile}: short page fits; all 50 rows and footer present across {len(long.pages)} pages"
    )
