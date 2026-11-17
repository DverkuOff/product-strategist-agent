"""Регрессия по аудиту (В1) и жюри (противоречие 4): ложные пропуски и срабатывания promise_lint.

Свойства и обещания — из скрипта аудитора review-agent-tech/tools/pl.py."""
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS  # noqa: F401
import core
import promise_lint

COMMS = """# Коммуникация
## Ключевые обещания
| ID | Обещание | Опора | Тип |
|---|---|---|---|
| K1 | Защищает от дипфейков голосом близких | P-01 | обещание |
| K2 | Гарантированно блокирует все звонки — полная защита | P-02 | обещание |
| K3 | Лучше всех защищает пожилых родителей | P-01 | обещание |
| K4 | Всего 99 рублей — дешевле конкурентов в 3 раза | P-03 | обещание |
| K5 | Ни один мошенник не дозвонится до мамы | P-01 | обещание |
| K6 | Надёжнее любого банка | P-01 | обещание |
| K7 | Уведомит близкого о звонке с незнакомого номера | P-01 | обещание |

## Слоган
Самая надёжная защита — **навсегда**.
"""


class PromiseAudit(unittest.TestCase):
    def setUp(self):
        self.p = Path(tempfile.mkdtemp())
        for d in ("state", "out"):
            (self.p / d).mkdir()
        core.write_jsonl(self.p / "state" / "claims.jsonl",
                         [{"id": "C-001", "text": "x", "kind": "fact", "status": "active", "sources": [{"material": "M-01"}]}])
        core.write_json(self.p / "state" / "product-properties.json", {"properties": [
            {"id": "P-01", "statement": "Уведомляет близкого о звонке с незнакомого номера", "status": "fact", "claims": ["C-001"]},
            {"id": "P-02", "statement": "Сервис не гарантирует блокировку всех звонков; это не полная защита", "status": "fact", "claims": ["C-001"]},
            {"id": "P-03", "statement": "Стоит 99 рублей в месяц", "status": "fact", "claims": ["C-001"]},
        ]})
        (self.p / "out" / "comms-strategy.md").write_text(COMMS, encoding="utf-8")
        (self.p / "out" / "validation-plan.md").write_text("", encoding="utf-8")
        self.rep = promise_lint.lint(self.p)
        self.by = {pr["id"]: [c for c, _ in pr["issues"]] for pr in self.rep["promises"]}

    def tearDown(self):
        shutil.rmtree(self.p, ignore_errors=True)

    def test_foreign_property_without_common_words(self):
        self.assertIn("E7", self.by["K1"])

    def test_negated_property_does_not_confirm(self):
        self.assertIn("E5", self.by["K2"])

    def test_comparatives(self):
        for k in ("K3", "K4", "K5", "K6"):
            self.assertIn("E5", self.by[k], k)
        self.assertIn("E6", self.by["K4"])

    def test_good_promise_passes(self):
        self.assertEqual(self.by["K7"], [])

    def test_slogan_is_error(self):
        self.assertTrue(any("E8" in e and "Слоган" in e for e in self.rep["errors"]), self.rep["errors"])


class RiskyWords(unittest.TestCase):
    def test_absolute_base_not_risky(self):
        self.assertEqual(promise_lint.risky_phrases("абсолютная база неизвестна"), [])
        self.assertTrue(promise_lint.risky_phrases("абсолютная защита от мошенников"))
        self.assertTrue(promise_lint.risky_phrases("абсолютно безопасно"))
