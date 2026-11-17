"""Регрессия по аудиту (В2) и жюри (п.3): ложные понижения и ложные пропуски verify_claims.

Снимки и утверждения — из скриптов аудитора review-agent-tech/tools/vc.py и vc2.py."""
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS  # noqa: F401
import core
import verify_claims

SNAP1 = """---
id: M-01
title: Итоги оператора за 2025 год
publisher: ComNews
---

Выручка оператора в 2025 году выросла на 11% и составила 220,5 млрд руб. Абонентская база — 11 000 000 человек.
Сервис «Защита близких» запущен 24.12.2025. По словам Дмитрия Рудских, сервисом пользуются семьи.
Компания Альфа-Банк не участвовала. Опрос проведён среди 1,5 тыс. респондентов.
В 2024 году число мошеннических звонков составило 12 млн.
"""
SNAP2 = """---
id: M-02
title: Обзор
---

Абонентская база сервиса — 11 000 000 человек. Специальный тариф для семей стоит 99 рублей.
Интерес к сервису высок, сообщила Мария Иванова. Звонки по телефону остаются основным каналом мошенников.
"""
Q = "Выручка оператора в 2025 году выросла на 11%"
PASS, DOWN = "pass", "down"
CASES = [  # (ожидание, снимок, текст утверждения, цитата)
    (PASS, "M-01", "Выручка оператора выросла на 11% в 2025 году", Q),
    (DOWN, "M-01", "Абонентская база выросла на 11%", "Абонентская база — 11 000 000 человек"),
    (DOWN, "M-01", "Число мошеннических звонков выросло на 12% в 2025 году", "В 2024 году число мошеннических звонков составило 12 млн"),
    (PASS, "M-01", "Абонентская база — 11 млн человек", "Абонентская база — 11 000 000 человек"),
    (PASS, "M-01", "Выручка составила 220 500 млн руб.", "составила 220,5 млрд руб"),
    (PASS, "M-01", "Опрос проведён среди 1500 респондентов", "Опрос проведён среди 1,5 тыс. респондентов"),
    (PASS, "M-01", "Сервис запущен 24 декабря 2025 года", "Сервис «Защита близких» запущен 24.12.2025"),
    (PASS, "M-01", "Выручка выросла на 11,0%", Q),
    (PASS, "M-01", "Дмитрий Рудских сообщил, что сервисом пользуются семьи", "По словам Дмитрия Рудских"),
    (DOWN, "M-01", "Теле2 запустил аналог раньше", Q),
    (DOWN, "M-01", "Сервис работает на Apple", Q),
    (DOWN, "M-01", "сервисом активно пользуются пенсионеры и подростки", "этой фразы нет в снимке"),
    (DOWN, "M-01", "Сервисом пользуются 24 семьи из 2025 опрошенных", Q),
    (DOWN, "M-01", "Сервис запущен 25 декабря 2025 года", "Сервис «Защита близких» запущен 24.12.2025"),
    (PASS, "M-02", "Абонентская база сервиса — 11 млн человек", "Абонентская база сервиса — 11 000 000 человек"),
    (DOWN, "M-02", "Тариф предлагает Альфа", "Специальный тариф для семей стоит 99 рублей"),
    (DOWN, "M-02", "Тариф предлагает Тесла", "Специальный тариф для семей стоит 99 рублей"),
    (DOWN, "M-02", "Теле2 продаёт тариф за 99 рублей", "Специальный тариф для семей стоит 99 рублей"),
    (DOWN, "M-02", "Интерес к сервису высок, сообщил Иван Иванов", "Интерес к сервису высок, сообщила Мария Иванова"),
    (DOWN, "M-02", "99% семей довольны тарифом", "Специальный тариф для семей стоит 99 рублей"),
    (DOWN, "M-02", "Тариф для семей стоит 99 рублей", None),  # факт без цитаты
]


class VerifyAudit(unittest.TestCase):
    def setUp(self):
        self.p = Path(tempfile.mkdtemp())
        for d in ("state", "materials", "out"):
            (self.p / d).mkdir()
        for mid, body in (("M-01", SNAP1), ("M-02", SNAP2), ("M-03", "---\nid: M-03\n---\n\n")):
            f = self.p / "materials" / f"{mid}-x.md"
            f.write_text(body, encoding="utf-8")
            core.manifest_add(self.p, mid, f)

    def tearDown(self):
        shutil.rmtree(self.p, ignore_errors=True)

    def check(self, rows):
        core.write_jsonl(self.p / "state" / "claims.jsonl", rows)
        return verify_claims.check(self.p)

    def test_cases(self):
        rows = []
        for i, (_, mid, text, quote) in enumerate(CASES, 1):
            src = {"material": mid}
            if quote:
                src["quote"] = quote
            rows.append({"id": f"C-{i:03d}", "text": text, "kind": "fact", "sources": [src], "status": "active"})
        rep = self.check(rows)
        down = {d[0]: d[2] for d in rep["downgrade"]}
        for i, (exp, _, text, quote) in enumerate(CASES, 1):
            cid = f"C-{i:03d}"
            self.assertEqual(DOWN if cid in down else PASS, exp, f"{cid} «{text}» ← «{quote}»: {down.get(cid, '')}")

    def test_empty_snapshot_downgrades(self):
        rep = self.check([{"id": "C-001", "text": "Пусто", "kind": "fact", "status": "active",
                           "sources": [{"material": "M-03", "quote": "Пусто"}]}])
        self.assertEqual([d[1] for d in rep["downgrade"]], ["empty_snapshot"])


class Quantities(unittest.TestCase):
    def test_scale_and_dates(self):
        self.assertTrue(core.same_quantity("11 млн", "11 000 000"))
        self.assertTrue(core.same_quantity("1500", "1,5 тыс."))
        self.assertTrue(core.same_quantity("220 500 млн", "220,5 млрд"))
        self.assertTrue(core.same_quantity("11,0%", "11%"))
        self.assertFalse(core.same_quantity("99%", "99 рублей"))
        self.assertFalse(core.same_quantity("11%", "11 000 000"))
        self.assertEqual(core.extract_dates("запущен 24.12.2025 и 3 марта 2026 года"), ["2025-12-24", "2026-03-03"])
