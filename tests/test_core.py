import unittest

from helpers import SCRIPTS  # noqa: F401
import core


class NumbersAndNames(unittest.TestCase):
    def test_numbers_canonical(self):
        self.assertEqual(core.extract_numbers("10% и 79,37 млн, 1 000 руб., 69 091 номер, в 20 раз"),
                         ["10", "79.37", "1000", "69091", "20"])

    def test_number_not_glued_to_year(self):
        self.assertEqual(core.extract_numbers("в 2025 году 100 человек"), ["2025", "100"])

    def test_proper_nouns_and_sentence_start(self):
        text = "По данным ЦБ, подключения выросли. Билайн сообщает, что Ева работает; «Защита близких»"
        self.assertEqual(core.extract_proper_nouns(text), ["ЦБ", "Билайн", "Ева", "Защита"])
        self.assertIn("Билайн", core.sentence_initial_words(text))
        self.assertNotIn("Ева", core.sentence_initial_words(text))

    def test_stem_handles_cases(self):
        self.assertIn(core.stem("МегаФона"), core.norm_text("сервис МегаФон запустил"))

    def test_norm_text(self):
        self.assertEqual(core.norm_text("«Ёлка»  и  ЕВА"), "елка и ева")


class Frontmatter(unittest.TestCase):
    def test_parse(self):
        meta, body = core.parse_frontmatter('---\nid: M-01\nurl: "https://x.ru/a:b"\n---\n\nТекст')
        self.assertEqual(meta["id"], "M-01")
        self.assertEqual(meta["url"], "https://x.ru/a:b")
        self.assertEqual(body.strip(), "Текст")


class Cost(unittest.TestCase):
    def test_opus_input_output(self):
        self.assertAlmostEqual(core.usage_cost("claude-opus-5-5", {"input_tokens": 1_000_000, "output_tokens": 1_000_000}), 24.0)

    def test_haiku_cheap(self):
        self.assertAlmostEqual(core.usage_cost("claude-haiku-5-5", {"input_tokens": 50_000}), 0.005)

    def test_cache_write_ttl(self):
        u = {"cache_creation_input_tokens": 2_000_000,
             "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000, "ephemeral_1h_input_tokens": 1_000_000},
             "cache_read_input_tokens": 1_000_000}
        # sonnet: 1M×2×1.25 + 1M×2×2 + 1M×0.10
        self.assertAlmostEqual(core.usage_cost("claude-sonnet-5-5", u), 2.5 + 4.0 + 0.10)

    def test_web_search(self):
        self.assertAlmostEqual(core.usage_cost("claude-sonnet-5-5", {"server_tool_use": {"web_search_requests": 3}}), 0.03)

    def test_unknown_model_zero(self):
        self.assertIsNone(core.usage_cost("<synthetic>", {"input_tokens": 10}))  # неизвестная цена — не $0


if __name__ == "__main__":
    unittest.main()
