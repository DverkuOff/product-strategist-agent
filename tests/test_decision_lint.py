import unittest

from helpers import TempRepoCase
import decision_lint


def codes(errs):
    return sorted({e.split()[0] for e in errs})


class Options(TempRepoCase):
    def test_fixture_clean(self):
        self.assertEqual(decision_lint.check_options(self.proj), [])
        self.assertEqual(decision_lint.check_decisions(self.proj), ([], []))

    def test_cost_of_inaction_required(self):
        self.replace_in("out/options.md", "**Цена бездействия:**", "**Прогноз:**")
        self.assertIn("O3", codes(decision_lint.check_options(self.proj)))

    def test_cost_of_inaction_needs_support(self):
        self.replace_in("out/options.md",
                        "базовая линия — подключения уже выросли примерно в 20 раз за год [факт C-001] без отдельной коммуникации; без изменений рост продолжится за счёт узнаваемости, но медленнее [прогноз C-020]; цена — подключения взрослых детей, которые о функции не знают [гипотеза C-018].",
                        "всё и так растёт.")
        errs = decision_lint.check_options(self.proj)
        self.assertTrue(any("без опоры" in e for e in errs))

    def test_status_quo_required(self):
        self.replace_in("out/options.md", "## Вариант A. Оставить как есть", "## Вариант A. Скидка 30%")
        self.assertIn("O2", codes(decision_lint.check_options(self.proj)))

    def test_rejected_variant_not_counted(self):
        self.replace_in("out/options.md", "## Вариант C. Платный семейный пакет", "## Вариант C. Платный семейный пакет (отброшен)")
        self.assertIn("O1", codes(decision_lint.check_options(self.proj)))

    def test_variant_needs_objections(self):
        self.replace_in("out/options.md", "- Возражение: провалится, потому что ядро", "- Замечание: ядро")
        self.assertIn("O5", codes(decision_lint.check_options(self.proj)))


class Decisions(TempRepoCase):
    def test_verdict_required_with_reason(self):
        self.replace_in("state/decisions.md", "- Вердикт: делать — вариант опирается", "- Вердикт: делать вариант опирается")
        errs, _ = decision_lint.check_decisions(self.proj)
        self.assertIn("D1", codes(errs))

    def test_reopen_required(self):
        self.replace_in("state/decisions.md", "- Что заставит пересмотреть:", "- Комментарий:")
        self.assertIn("D2", codes(decision_lint.check_decisions(self.proj)[0]))

    def test_old_kill_field_accepted(self):
        self.replace_in("state/decisions.md", "- Что заставит пересмотреть:", "- Kill-критерии:")
        self.assertEqual(decision_lint.check_decisions(self.proj)[0], [])

    def test_placeholder_not_allowed_at_validation(self):
        self.replace_in("state/decisions.md", "- Что заставит пересмотреть: T-01", "- Что заставит пересмотреть: будут в плане проверки; T-01")
        self.assertIn("D2", codes(decision_lint.check_decisions(self.proj)[0]))

    def test_do_without_worked_out_variant_is_downgraded(self):
        self.replace_in("state/decisions.md", "- Вариант: B", "- Вариант: Z")
        errs, downs = decision_lint.check_decisions(self.proj)
        self.assertEqual([d for d, _ in downs], ["D-001"])
        decision_lint.apply_downgrades(self.proj, downs)
        text = (self.proj / "state" / "decisions.md").read_text(encoding="utf-8")
        self.assertIn("Вердикт: нужна ясность — понижено проверкой", text)
        self.assertIn("(было: делать —", text)
        self.assertEqual(decision_lint.check_decisions(self.proj), ([], []))  # повторно не понижает
        self.assertIn("decision_lint", (self.proj / "state" / "journal.md").read_text(encoding="utf-8"))

    def test_do_with_unsupported_variant_is_downgraded(self):
        # вариант B без меток утверждений — не проработан
        self.replace_in("out/options.md", "[гипотеза C-018]; покупатель — взрослый ребёнок [факт C-004].", "незнание; покупатель — взрослый ребёнок.")
        _, downs = decision_lint.check_decisions(self.proj)
        self.assertTrue(downs and "нет опоры" in downs[0][1])

    def test_stop_verdict_needs_no_variant(self):
        self.replace_in("state/decisions.md", "- Вердикт: делать —", "- Вердикт: стоп —")
        self.replace_in("state/decisions.md", "- Вариант: B", "- Вариант: —")
        self.assertEqual(decision_lint.check_decisions(self.proj), ([], []))

    def test_cli(self):
        self.assertEqual(decision_lint.main(["--project", str(self.proj)]), 0)


if __name__ == "__main__":
    unittest.main()
