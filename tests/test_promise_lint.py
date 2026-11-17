import unittest

from helpers import TempRepoCase
import promise_lint
import verify_claims


def issues(rep, pid):
    return [code for p in rep["promises"] if p["id"] == pid for code, _ in p["issues"]]


class PromiseLint(TempRepoCase):
    def test_fixture_is_clean(self):
        rep = promise_lint.lint(self.proj)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["stats"]["promises"], 6)
        self.assertEqual(rep["stats"]["failed"], 0)
        self.assertEqual(rep["warnings"], [])  # «Полная защита» в разделе «Чего не говорим» не считается

    def test_e1_no_support(self):
        self.replace_in("out/comms-strategy.md", "| P-04 | обещание |", "| — | обещание |")
        self.assertEqual(issues(promise_lint.lint(self.proj), "MSG-03"), ["E1"])

    def test_e2_unknown_property(self):
        self.replace_in("out/comms-strategy.md", "| P-04 | обещание |", "| P-42 | обещание |")
        self.assertIn("E2", issues(promise_lint.lint(self.proj), "MSG-03"))

    def test_e3_hypothesis_as_promise(self):
        self.replace_in("out/comms-strategy.md", "| P-06 | тест сообщения |", "| P-06 | обещание |")
        self.assertEqual(issues(promise_lint.lint(self.proj), "MSG-05"), ["E3"])

    def test_e4_test_not_in_validation_plan(self):
        self.replace_in("out/validation-plan.md", "| MSG-06 |", "| X-06 |")
        self.assertEqual(issues(promise_lint.lint(self.proj), "MSG-06"), ["E4"])

    def test_e5_risky_wording(self):
        self.replace_in("out/comms-strategy.md", "Ева распознаёт поддельные голоса", "Ева гарантированно распознаёт поддельные голоса")
        self.assertEqual(issues(promise_lint.lint(self.proj), "MSG-04"), ["E5"])

    def test_e5_full_protection(self):
        self.replace_in("out/comms-strategy.md", "и сама прервёт опасный разговор", "и обеспечит полную защиту")
        self.assertIn("E5", issues(promise_lint.lint(self.proj), "MSG-01"))

    def test_e6_number_without_support(self):
        self.replace_in("out/comms-strategy.md", "до 50 номеров близких", "до 100 номеров близких")
        self.assertEqual(issues(promise_lint.lint(self.proj), "MSG-03"), ["E6"])

    def test_cascade_from_verify_claims(self):
        # факт C-002 искажён → понижен → свойство P-01 становится гипотезой → MSG-01 не проходит
        c = next(x for x in self.claims() if x["id"] == "C-002")
        self.edit_claim("C-002", text=c["text"].replace("10%", "30%"))
        verify_claims.apply_fix(self.proj, verify_claims.check(self.proj))
        rep = promise_lint.lint(self.proj)
        self.assertIn("E3", issues(rep, "MSG-01"))
        self.assertTrue(any("P-01" in w for w in rep["warnings"]))

    def test_property_fact_without_claims_is_hypothesis(self):
        import json
        p = self.proj / "state" / "product-properties.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["properties"][3]["claims"] = []
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertIn("E3", issues(promise_lint.lint(self.proj), "MSG-03"))

    def test_risky_outside_table_is_warning(self):
        self.replace_in("out/comms-strategy.md", "## 2. Барьер", "## 2. Барьер\nСамый надёжный оператор.")
        rep = promise_lint.lint(self.proj)
        self.assertTrue(any("«самый»" in w for w in rep["warnings"]))

    def test_missing_comms(self):
        (self.proj / "out" / "comms-strategy.md").unlink()
        self.assertEqual(promise_lint.main(["--project", str(self.proj)]), 2)

    def test_matrix(self):
        m = promise_lint.matrix(self.proj, promise_lint.lint(self.proj))
        self.assertIn("| MSG-01", m)
        self.assertIn("C-002", m)


class Parsing(unittest.TestCase):
    def test_parse_promises_any_column_order(self):
        md = "| Опора | Тип | Обещание | ID |\n|---|---|---|---|\n| P-01, P-02 | обещание | Текст | MSG-01 |\n"
        p = promise_lint.parse_promises(md)[0]
        self.assertEqual(p["id"], "MSG-01")
        self.assertEqual(p["props"], ["P-01", "P-02"])

    def test_strikethrough_ignored(self):
        md = "| Обещание | Опора |\n|---|---|\n| ~~лучший~~ Текст | P-01 |\n"
        self.assertEqual(promise_lint.parse_promises(md)[0]["text"], "Текст")

    def test_risky_forms(self):
        self.assertTrue(promise_lint.risky_phrases("самый быстрый"))
        self.assertTrue(promise_lint.risky_phrases("оператор №1"))
        self.assertFalse(promise_lint.risky_phrases("работает лучше, чем страх"))
        self.assertFalse(promise_lint.risky_phrases("предложение самому абоненту"))


if __name__ == "__main__":
    unittest.main()
