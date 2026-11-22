import unittest

from helpers import TempRepoCase
import claims as claims_cli
import compare
import revisit


class Compare(TempRepoCase):
    def test_table_on_fixture(self):
        md = compare.build(self.proj)
        self.assertIn("| Ключевых обещаний | 6 | 13 |", md)
        self.assertIn("| …противоречит факту (суждение) | 0 | 2 |", md)
        self.assertIn("| ≥3 вариантов решения | да | нет |", md)
        self.assertIn("| Фактов, подтверждённых снимками источников | 15 из 15 |", md)

    def test_negation_not_counted(self):
        self.assertEqual(compare.risky("Избегать обещаний «100% защиты»."), [])
        self.assertTrue(compare.risky("Ева даёт 100% защиту."))
        # значение параметра в расчёте — не обещание; обещание «100%» по-прежнему считается
        self.assertEqual(compare.risky("| k=25 % | k=100 % |\nпри 100 % приписывании прибавка 3 млн"), [])
        self.assertTrue(compare.risky("Скидка до 100% всем семьям."))
        # признаки в другой формулировке: варианты строками таблицы, «без изменений», «остановить»
        text = ("| **A. Семьи** | x |\n| **B. Владельцы** | y |\n| **D. Роутер** | z |\n"
                "Путь без изменений. Неизвестные исходы. Стоп-сигнал. **Остановить** пилот.")
        checks = compare.analyze(text, set())["checks"]
        for name in ("≥3 вариантов решения", "вариант «оставить как есть»", "раздел «чего не знаем»",
                     "план: нежелательные последствия", "план: kill-критерий"):
            self.assertTrue(checks[name], name)
        self.assertFalse(compare.analyze("**A или B.** выбираем A", set())["checks"]["≥3 вариантов решения"])

    def test_risky_in_refusal_section_not_counted(self):
        self.assertEqual(compare.risky("## Чего не говорим\n- Самый надёжный\n"), [])

    def test_writes_out_file(self):
        compare.main(["--project", str(self.proj)])
        self.assertTrue((self.proj / "out" / "compare.md").exists())


class Revisit(TempRepoCase):
    def test_clean(self):
        self.assertEqual(revisit.check(self.proj), [])

    def test_forum_hypothesis_does_not_reopen(self):
        # C-021 (форум, гипотеза) противоречит C-002 — шум не должен переоткрывать решение
        self.assertEqual([c for c in self.claims() if c["id"] == "C-021"][0]["contradicts"], ["C-002"])
        self.assertEqual(revisit.check(self.proj), [])

    def test_new_contradicting_fact_reopens(self):
        rows = self.claims()
        rows.append({"id": "C-030", "text": "МегаФон сообщает новое", "kind": "fact", "status": "active",
                     "sources": [{"material": "M-03"}], "contradicts": ["C-004"]})
        self.write_claims(rows)
        flags = revisit.check(self.proj)
        self.assertTrue(any("C-030" in f and "C-004" in f for f in flags))

    def test_superseded_basis(self):
        rows = self.claims()
        rows.append({"id": "C-031", "text": "уточнение", "kind": "hypothesis", "status": "active", "sources": []})
        self.write_claims(rows)
        self.assertEqual(claims_cli.main(["supersede", "C-001", "--by", "C-031", "--reason", "новые данные"]), 0)
        self.assertTrue(any("C-001 заменено на C-031" in f for f in revisit.check(self.proj)))

    def test_due_date(self):
        import datetime as dt
        flags = revisit.check(self.proj, today=dt.date(2027, 2, 1))
        self.assertTrue(any("дата пересмотра" in f for f in flags))

    def test_inactive_decision_ignored(self):
        self.replace_in("state/decisions.md", "Статус: принято", "Статус: отменено")
        self.assertEqual(revisit.check(self.proj, today=__import__("datetime").date(2030, 1, 1)), [])


if __name__ == "__main__":
    unittest.main()
