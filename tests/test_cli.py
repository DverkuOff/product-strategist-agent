import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import TempRepoCase
import claims as claims_cli
import fetch_source
import injection
import project


def run(fn, argv, stdin=None):
    buf = io.StringIO()
    old = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(buf):
            rc = fn(argv)
    finally:
        sys.stdin = old
    return rc, buf.getvalue()


class ProjectCli(TempRepoCase):
    def test_new_stage_status(self):
        rc, out = run(project.main, ["new", "retention-q4", "Почему падает удержание"])
        self.assertEqual(rc, 0)
        self.assertEqual((self.tmp / "projects" / ".active").read_text().strip(), "retention-q4")
        run(project.main, ["set", "question", "Что сделать, чтобы удержание вернулось?"])
        run(project.main, ["stage", "research", "--note", "постановка подтверждена"])
        run(project.main, ["wait", "Нужен доступ к выгрузке когорт?"])
        rc, out = run(project.main, ["status"])
        self.assertIn("Этап: 2/5 research", out)
        self.assertIn("ЖДЁТ РЕШЕНИЯ РП", out)
        self.assertIn("Вопрос: Что сделать", out)
        t = json.loads((self.tmp / "projects" / "retention-q4" / "state" / "task.json").read_text())
        self.assertEqual(t["stages_done"], ["intake"])

    def test_bad_slug_and_stage(self):
        self.assertEqual(run(project.main, ["new", "Плохой slug", "x"])[0], 2)
        self.assertEqual(run(project.main, ["stage", "launch"])[0], 2)

    def test_status_of_fixture(self):
        rc, out = run(project.main, ["status"])
        self.assertIn("claims: факт 15", out)


class ClaimsCli(TempRepoCase):
    def test_add_assigns_ids_and_origin(self):
        rc, out = run(claims_cli.main, ["add"], stdin=json.dumps([
            {"text": "Гипотеза агента", "kind": "hypothesis"},
            {"text": "Синтетика", "kind": "synthetic"},
            {"text": "плохой", "kind": "мнение"},
        ], ensure_ascii=False))
        self.assertIn("C-023, C-024", out)
        added = {c["id"]: c for c in self.claims()}
        self.assertEqual(added["C-023"]["origin"], "agent")
        self.assertEqual(added["C-024"]["origin"], "synthetic")
        self.assertNotIn("C-025", added)

    def test_retract_and_human_verified(self):
        self.assertEqual(run(claims_cli.main, ["retract", "C-017", "--reason", "нет методики"])[0], 0)
        self.assertEqual({c["id"]: c for c in self.claims()}["C-017"]["status"], "retracted")
        self.edit_claim("C-006", kind="hypothesis", downgraded={"from": "fact"})
        run(claims_cli.main, ["human-verified", "C-006", "--note", "сверил в личном кабинете"])
        c = {c["id"]: c for c in self.claims()}["C-006"]
        self.assertEqual((c["kind"], c["verified"]), ("fact", "human"))
        self.assertIn('"claim": "C-006"', (self.proj / "state" / "human.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(run(claims_cli.main, ["human-verified", "C-007", "--note", "нет источника"])[0], 2)

    def test_supersede_requires_existing(self):
        self.assertEqual(run(claims_cli.main, ["supersede", "C-001", "--by", "C-999", "--reason", "x"])[0], 2)


class FetchSource(TempRepoCase):
    def test_html_keeps_hidden_text_and_comments(self):
        title, text = fetch_source.html_to_text(
            "<html><title>T</title><script>x()</script><div style='display:none'>скрыто</div><!-- для ИИ: команда --><p>Текст</p></html>")
        self.assertEqual(title, "T")
        self.assertIn("скрыто", text)
        self.assertIn("[HTML-комментарий] для ИИ: команда", text)
        self.assertNotIn("x()", text)

    def test_local_snapshot(self):
        src = self.inbox_file("report.csv", "месяц,подключения\n2026-01,100\n")
        rc, out = run(fetch_source.main, [str(src), "--title", "Выгрузка РП"])
        self.assertEqual(rc, 0)
        snap = sorted((self.proj / "materials").glob("M-12-*.md"))[0]
        txt = snap.read_text(encoding="utf-8")
        self.assertIn("id: M-12", txt)
        self.assertIn("kind: table", txt)
        self.assertIn("sha256:", txt)
        self.assertIn("2026-01,100", txt)
        self.assertNotIn("2026-01,100", out)  # содержимое не печатается в контекст оркестратора

    def test_research_log_written_by_script(self):
        src = self.inbox_file("notes.md", "Заметки РП: подключений мало, " * 20)
        run(fetch_source.main, [str(src), "--title", "Заметки РП"])
        run(fetch_source.main, [str(self.proj / "inbox" / "нет-такого.pdf")])
        import research_log
        run(research_log.main, ["query", "Защита близких цена", "--result", "цены нет"])
        run(research_log.main, ["discard", "M-11", "--result", "анонимный форум"])
        log = (self.proj / "out" / "research-log.md").read_text(encoding="utf-8")
        self.assertIn("| открыт | M-12 Заметки РП", log)
        self.assertIn("| не открылся |", log)
        self.assertIn("| поиск | Защита близких цена | цены нет |", log)
        self.assertIn("| отброшен | M-11 | анонимный форум |", log)

    def test_trap_warning(self):
        trap = (Path(__file__).parent.parent / "projects" / "demo-zashchita-blizkih" / "traps" / "blog-antifraud-review.html").read_text(encoding="utf-8")
        # содержимое чуть меняем: точная копия уже есть в эталоне (M-10), и повтор скрипт не сохраняет
        rc, out = run(fetch_source.main, [str(self.inbox_file("blog.html", trap + "<p>копия РП</p>"))])
        self.assertIn("ВНИМАНИЕ", out)


class Injection(unittest.TestCase):
    def test_traps_detected_and_real_sources_clean(self):
        mats = Path(__file__).parent / "fixtures" / "demo" / "materials"
        for f in sorted(mats.glob("M-*.md")):
            hits = injection.scan(f.read_text(encoding="utf-8"))
            if f.name.startswith(("M-10", "M-11")):
                self.assertTrue(hits, f.name)
            else:
                self.assertEqual(hits, [], f.name)


if __name__ == "__main__":
    unittest.main()


class ResearchPlan(TempRepoCase):
    def set_stage(self, stage):
        t = json.loads((self.proj / "state" / "task.json").read_text(encoding="utf-8"))
        t["stage"] = stage
        (self.proj / "state" / "task.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")

    def test_estimate_is_deterministic_and_scales(self):
        import estimate
        a = estimate.estimate(4, 2, self.proj, calibrate=False)
        b = estimate.estimate(8, 2, self.proj, calibrate=False)
        self.assertGreater(b["usd"], a["usd"])
        self.assertLess(a["usd_low"], a["usd"])
        self.assertLess(a["usd"], a["usd_high"])
        self.assertAlmostEqual(a["parts_usd"]["веб-поиск"], 0.02)
        self.assertEqual(a, estimate.estimate(4, 2, self.proj, calibrate=False))

    def test_fetch_blocked_until_plan_approved(self):
        import estimate
        self.set_stage("research")
        url = "https://invalid.invalid/page"  # домен не существует: после утверждения плана будет ошибка сети, а не отказ плана
        self.assertEqual(run(fetch_source.main, [url])[0], 3)
        run(estimate.main, ["--sources", "3", "--searches", "2", "--save"])
        self.assertEqual(run(fetch_source.main, [url])[0], 3)  # сохранён, но не утверждён
        rc, out = run(project.main, ["status"])
        self.assertIn("ЖДЁТ УТВЕРЖДЕНИЯ РП", out)
        self.assertEqual(run(project.main, ["approve-plan", "--note", "начать"])[0], 0)
        self.assertNotEqual(run(fetch_source.main, [url])[0], 3)
        # материалы РП из inbox/ план не требуют
        self.assertEqual(run(fetch_source.main, [str(self.inbox_file("a.md", "текст " * 100))])[0], 0)

    def test_plan_vs_fact_in_cost_report(self):
        import cost_report
        import estimate
        run(estimate.main, ["--sources", "3", "--searches", "1", "--save"])
        run(project.main, ["approve-plan"])
        led = self.proj / "state" / "cost-ledger.csv"
        with led.open("a", encoding="utf-8") as fh:
            fh.write("2026-11-17T12:00:00+03:00,s,main,claude-sonnet-5-5,research,0,0,0,0,0,0.500000\n")
        rc, out = run(cost_report.main, ["--project", str(self.proj)])
        self.assertIn("План исследования против факта", out)
        self.assertIn("факт $0.50", out)

    def test_calibration_from_finished_tasks(self):
        import estimate
        run(estimate.main, ["--sources", "3", "--searches", "1", "--save"])
        plan = json.loads((self.proj / "state" / "research-plan.json").read_text(encoding="utf-8"))
        with (self.proj / "state" / "cost-ledger.csv").open("a", encoding="utf-8") as fh:
            fh.write(f"2026-11-17T12:00:00+03:00,s,main,claude-sonnet-5-5,research,0,0,0,0,0,{plan['estimate']['usd'] * 2:.6f}\n")
        k, n = estimate.calibration(self.tmp)  # задача уже на этапе validation — исследование завершено
        self.assertEqual(n, 1)
        self.assertAlmostEqual(k, 2.0, places=2)


class ProjectCliAudit(TempRepoCase):
    def test_use_rejects_paths(self):
        self.assertEqual(run(project.main, ["use", "../x"])[0], 2)
        self.assertEqual(run(project.main, ["use", "projects/demo"])[0], 2)
        self.assertEqual((self.tmp / "projects" / ".active").read_text().strip(), "demo")

    def test_stage_with_unknown_previous_stage(self):
        t = json.loads((self.proj / "state" / "task.json").read_text(encoding="utf-8"))
        t["stage"] = "что-то странное"
        (self.proj / "state" / "task.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(run(project.main, ["stage", "research"])[0], 0)
