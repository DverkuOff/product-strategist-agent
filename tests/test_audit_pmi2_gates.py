"""Регрессия по второму кругу ПМИ: Н-4 (отмывание «99%»), Н-8 (сокращения argparse), Н-9 (ворота при откате и
переходе этапа), Л-3 (многоточие внутри kill-критерия и дефис в вердикте)."""
import json

import helpers  # noqa: F401 — пути к scripts/
import core
import decision_lint
import fetch_source
import gates
import project
import verify_claims
from test_audit_pmi_gates import Base, downgrade_reasons, run

FORUM = ("<html><head><title>Страница</title></head><body><h1>Тема: защита от мошенников</h1>"
         "<div class=\"post\"><b>гость_123</b>: Говорят, что Ева блокирует 99% мошеннических звонков, у меня вообще "
         "ни одного не было с прошлой весны. Мне тоже кажется, что звонков стало меньше, но маме всё равно звонили.</div>"
         "</body></html>")


class LaunderingNinetyNine(Base):  # Н-4
    def test_second_strong_source_does_not_launder_weak_number(self):
        rc, out = run(__import__("claims").main, ["add"], stdin=json.dumps({
            "text": "Ева блокирует 99% мошеннических звонков", "kind": "fact", "sources": [
                {"material": "M-11", "quote": "Говорят, что Ева блокирует 99% мошеннических звонков"},
                {"material": "M-03", "quote": "блокирует большинство мошеннических звонков, не доводя их до абонента"}]},
            ensure_ascii=False))
        self.assertEqual(rc, 0, out)
        cid = self.claims()[-1]["id"]
        rep = verify_claims.check(self.proj)
        self.assertIn(downgrade_reasons(rep).get(cid), ("not_in_snapshot", "not_in_quote"))
        detail = next(d for c, _, d in rep["downgrade"] if c == cid)
        self.assertIn("99", detail)
        self.assertIn("слабом источнике", detail)

    def test_inbox_page_is_not_rp_and_forum_content_is_ugc(self):
        f = self.inbox_file("page.html", FORUM)
        rc, out = run(fetch_source.main, [str(f), "--title", "Страница от РП"])
        self.assertEqual(rc, 0, out)
        self.assertIn("тип источника ugc", out)
        g = self.inbox_file("note.md", "Заметка РП о планах на квартал без цифр и мнений пользователей. " * 5)
        rc, out = run(fetch_source.main, [str(g)])
        self.assertIn("тип источника unknown", out)
        h = self.inbox_file("report.csv", "месяц,подключения\nянварь,120\nфевраль,135\n")
        rc, out = run(fetch_source.main, [str(h), "--kind", "table"])
        self.assertIn("тип источника rp", out)

    def test_agent_cannot_raise_source_type(self):
        f = self.inbox_file("saved2.html", "<p>" + "Обсуждение сервиса защиты от звонков. " * 20 + "</p>")
        rc, out = run(fetch_source.main, [str(f), "--url", "https://forum.example.ru/t/1", "--source-type", "media"])
        self.assertEqual(rc, 0, out)
        self.assertIn("тип источника ugc", out)
        self.assertIn("не принят", out)
        f2 = self.inbox_file("plain.md", "Отчёт компании о квартале. " * 30)
        rc, out = run(fetch_source.main, [str(f2), "--source-type", "official"])  # без признаков — тип задаёт агент
        self.assertIn("тип источника official", out)
        self.assertTrue(core.source_type_allowed("media", "ugc"))  # понизить можно
        self.assertFalse(core.source_type_allowed("advertising", "official"))


class AbbreviatedOptions(Base):  # Н-8
    def test_rebuild_abbreviation_rejected(self):
        import os
        os.environ["STRATEGIST_MAINTAINER"] = "1"
        try:
            with self.assertRaises(SystemExit):
                run(fetch_source.main, ["--rebuild"])
        finally:
            os.environ.pop("STRATEGIST_MAINTAINER", None)
        with self.assertRaises(SystemExit):
            run(project.main, ["stage", "options", "--no", "x"])


class GatesOnAnyStage(Base):  # Н-9
    def break_promise(self):
        self.replace_in("out/comms-strategy.md", "| MSG-06 | Родителям не нужен смартфон | P-07 | тест сообщения |",
                        "| MSG-06 | Родителям не нужен смартфон | P-07 | тест сообщения |\n"
                        "| MSG-07 | Ева гарантированно защитит ваших близких от всех мошенников | P-01 | обещание |")

    def test_rollback_does_not_switch_off_promise_check(self):
        self.break_promise()
        for stage in ("research", "intake", "strategy"):
            self.set_stage(stage)
            probs, _ = gates.problems(self.proj)
            self.assertTrue(any("MSG-07" in p for p in probs), stage)

    def test_forward_stage_refused_when_red(self):
        self.set_stage("strategy")
        self.break_promise()
        rc, out = run(project.main, ["stage", "validation"])
        self.assertEqual(rc, 2)
        self.assertIn("ворота качества красные", out)
        self.assertEqual(core.load_task(self.proj)["stage"], "strategy")
        self.set_stage("validation")
        rc, out = run(project.main, ["stage", "done"])
        self.assertEqual(rc, 2)
        self.assertEqual(run(project.main, ["stage", "research"])[0], 0)  # назад можно, но ворота остаются красными
        self.assertTrue(gates.problems(self.proj)[0])

    def test_clean_fixture_moves_forward(self):
        self.set_stage("validation")
        self.assertEqual(gates.problems(self.proj)[0], [])
        rc, out = run(project.main, ["stage", "done", "--note", "kill-критерии утверждены"])
        self.assertEqual(rc, 0, out)


class DecisionPlaceholders(Base):  # Л-3
    def test_ellipsis_inside_kill_criterion_is_not_placeholder(self):
        self.replace_in("state/decisions.md", "за 4 недели;", "за 4 недели (сравнение «до… после»);")
        self.assertEqual(decision_lint.check_decisions(self.proj)[0], [])

    def test_real_placeholders_still_caught(self):
        for ph in ("…", "TODO", "kill-критерии — при каком результате проверки или каком новом факте решение отменяется",
                   "будут в плане проверки"):
            text = (self.proj / "state" / "decisions.md").read_text(encoding="utf-8")
            import re
            new = re.sub(r"(- Что заставит пересмотреть:).*", lambda m: f"{m.group(1)} {ph}", text, count=1)
            (self.proj / "state" / "decisions.md").write_text(new, encoding="utf-8")
            codes = [e.split()[0] for e in decision_lint.check_decisions(self.proj)[0]]
            self.assertIn("D2", codes, ph)

    def test_hyphen_in_verdict_accepted(self):
        self.replace_in("state/decisions.md", "- Вердикт: делать — вариант", "- Вердикт: делать - вариант")
        self.assertEqual(decision_lint.check_decisions(self.proj)[0], [])
        self.replace_in("state/decisions.md", "- Вердикт: делать - вариант", "- Вердикт: делать вариант")
        errs = decision_lint.check_decisions(self.proj)[0]
        self.assertTrue(errs and "тире" in errs[0], errs)
