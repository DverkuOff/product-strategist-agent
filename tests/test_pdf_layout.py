"""PDF из inbox/: таблица брифа сохраняет столбцы (pdftotext -layout), а не перемешивается построчно."""
import shutil
import unittest
from pathlib import Path

from helpers import SCRIPTS  # noqa: F401  (кладёт scripts/ в sys.path)
import fetch_source

BRIEF = Path(__file__).resolve().parents[1] / "projects" / "demo-svyaz-dlya-blizkih" / "inbox" / "brief-megafon.pdf"


@unittest.skipUnless(shutil.which("pdftotext") and BRIEF.exists(), "нужны pdftotext (poppler) и бриф демо-задачи")
class PdfLayout(unittest.TestCase):
    def test_table_row_keeps_columns(self):
        _, text, data = fetch_source.convert_local(BRIEF)
        self.assertEqual(data, BRIEF.read_bytes())
        row = next(l for l in text.splitlines() if "7 500" in l)
        self.assertEqual(row.split(), ["7", "500", "6", "500", "8", "000", "12", "000"])


if __name__ == "__main__":
    unittest.main()
