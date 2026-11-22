"""Цитата из ячейки таблицы PDF (pdftotext -layout): строки ячейки перемежаются соседними столбцами."""
import unittest

from helpers import SCRIPTS  # noqa: F401  (кладёт scripts/ в sys.path)
import verify_claims as v

LAYOUT = (
    "Кто нужен           Что известно в начале работы     Что предстоит решить\n"
    "                                                     Сколько требует ваш вариант и что\n"
    "                    На второй квартал предварительно упростить, перенести или\n"
    "Разработчики\n"
    "                    выделено три человеко-месяца     дополнительно профинансировать при\n"
    "                                                     дефиците\n"
)


class TableQuotes(unittest.TestCase):
    def test_cell_split_over_lines_is_found(self):
        r = v.quote_sentences(LAYOUT, "На второй квартал предварительно выделено три человеко-месяца")
        self.assertIsNotNone(r)
        self.assertIn("три", r)

    def test_changed_number_is_not_found(self):
        self.assertIsNone(v.quote_sentences(LAYOUT, "На второй квартал предварительно выделено пять человеко-месяцев"))

    def test_words_from_other_column_are_not_glued(self):
        self.assertIsNone(v.quote_sentences(LAYOUT, "предварительно выделено три человеко-месяца дополнительно профинансировать"))
        self.assertIsNone(v.quote_sentences(LAYOUT, "выделено три человеко-месяца упростить, перенести или"))

    def test_short_quote_not_matched_by_cells(self):
        self.assertIsNone(v.quote_in_table_cell(LAYOUT, "выделено три"))


if __name__ == "__main__":
    unittest.main()
