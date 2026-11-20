"""Регрессия по прогону ПМИ 20.11 (Д-3, Д-4, Д-9…Д-12, Д-14, Д-18, Д-21, Д-24, Д-25): ворота качества и скрипты."""
import io
import json
from contextlib import redirect_stderr, redirect_stdout

from helpers import TempRepoCase
import claims as claims_cli
import compare
import core
import decision_lint
import estimate
import fetch_source
import project
import promise_lint
import verify_claims


def run(fn, argv, stdin=None):
    import sys
    old = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn(argv)
    finally:
        sys.stdin = old
    return rc, out.getvalue() + err.getvalue()


def downgrade_reasons(rep):
    return {cid: reason for cid, reason, _ in rep["downgrade"]}


class Base(TempRepoCase):
    def add_claim(self, text, material, quote):
        rc, out = run(claims_cli.main, ["add"], stdin=json.dumps(
            {"text": text, "kind": "fact", "sources": [{"material": material, "quote": quote}]}, ensure_ascii=False))
        self.assertEqual(rc, 0, out)
        return self.claims()[-1]["id"]

    def set_stage(self, stage):
        t = core.load_task(self.proj)
        t["stage"] = stage
        core.write_json(self.proj / "state" / "task.json", t)


class SourceReliability(Base):  # Д-4
    def test_forum_99_percent_is_not_a_fact(self):
        cid = self.add_claim("Ева блокирует 99% мошеннических звонков", "M-11",
                             "Говорят, что Ева блокирует 99% мошеннических звонков")
        rep = verify_claims.check(self.proj)
        self.assertEqual(downgrade_reasons(rep).get(cid), "weak_source")

    def test_fixture_hypothesis_on_forum_is_shown(self):
        rc, out = run(verify_claims.main, [])
        self.assertEqual(rc, 0, out)
        self.assertIn("C-021 остаётся гипотезой", out)

    def test_source_type_saved_in_manifest(self):
        f = self.inbox_file("forum-otzyvy.html", "<p>" + "Отзыв пользователя о сервисе. " * 30 + "</p>")
        rc, out = run(fetch_source.main, [str(f)])
        self.assertEqual(rc, 0, out)
        mf = core.read_json(self.proj / "materials" / core.MANIFEST)
        self.assertEqual(mf[sorted(mf)[-1]]["source_type"], "ugc")
        f2 = self.inbox_file("report.md", "Отчёт компании о квартале. " * 30)
        run(fetch_source.main, [str(f2), "--source-type", "official"])
        mf = core.read_json(self.proj / "materials" / core.MANIFEST)
        self.assertEqual(mf[sorted(mf)[-1]]["source_type"], "official")

    def test_traps_folder_is_a_local_source(self):  # Д-3: ловушку можно сохранить снимком, а не читать самому
        (self.proj / "traps").mkdir()
        (self.proj / "traps" / "forum-eva.html").write_text("<p>" + "Ева блокирует почти всё, говорят на форуме. " * 20 + "</p>", encoding="utf-8")
        rc, out = run(fetch_source.main, [str(self.proj / "traps" / "forum-eva.html")])
        self.assertEqual(rc, 0, out)
        self.assertIn("тип источника ugc", out)


class QuoteStrength(Base):  # Д-12
    def test_one_word_quote_is_not_evidence(self):
        cid = self.add_claim("Ева блокирует всех мошенников без исключений и гарантирует полную защиту", "M-03", "Ева")
        self.assertEqual(downgrade_reasons(verify_claims.check(self.proj)).get(cid), "short_quote")

    def test_quantifier_must_be_in_quote(self):
        cid = self.add_claim("Ева блокирует все мошеннические звонки до абонента", "M-03",
                             "блокирует большинство мошеннических звонков, не доводя их до абонента")
        self.assertEqual(downgrade_reasons(verify_claims.check(self.proj)).get(cid), "not_in_quote")

    def test_full_chain_to_guaranteed_promise_fails(self):
        cid = self.add_claim("Ева блокирует всех мошенников без исключений и гарантирует полную защиту", "M-03", "Ева")
        verify_claims.apply_fix(self.proj, verify_claims.check(self.proj))
        props = core.read_json(self.proj / "state" / "product-properties.json")
        props["properties"].append({"id": "P-08", "statement": "Ева гарантированно блокирует всех мошенников, полная защита",
                                    "status": "fact", "claims": [cid]})
        core.write_json(self.proj / "state" / "product-properties.json", props)
        self.replace_in("out/comms-strategy.md", "| MSG-06 | Родителям не нужен смартфон | P-07 | тест сообщения |",
                        "| MSG-06 | Родителям не нужен смартфон | P-07 | тест сообщения |\n"
                        "| MSG-07 | Ева гарантированно блокирует всех мошенников — полная защита | P-08 | обещание |")
        rep = promise_lint.lint(self.proj)
        bad = [p for p in rep["promises"] if p["id"] == "MSG-07"][0]
        self.assertFalse(bad["ok"])
        self.assertIn("E3", [c for c, _ in bad["issues"]])

    def test_fixture_facts_still_pass(self):
        rep = verify_claims.check(self.proj)
        self.assertEqual(rep["downgrade"], [])
        self.assertEqual(len(rep["ok"]), 15)


VARIANTS = [  # Д-11: 14 близких формулировок из отчёта ПМИ
    "Наилучшая защита близких", "блокирует самую опасную их часть", "защищает всегда", "работает лучше, чем конкуренты",
    "надёжнее, чем у конкурентов", "защищает от любого мошенничества", "Гaрантированно защищает",  # латинская a
    "Ева блокирует все мошеннические звонки", "работает безупречно", "ни при каких обстоятельствах не пропустит звонок",
    "первой в России", "максимальная защита", "на все сто", "лучше чем у других",
]


class PromiseVariants(Base):
    def test_fourteen_variants_fail(self):
        rows = "\n".join(f"| MSG-{i + 10} | Ева блокирует мошеннические звонки на номера близких: {v} | P-01 | обещание |"
                         for i, v in enumerate(VARIANTS))
        self.replace_in("out/comms-strategy.md", "| MSG-06 | Родителям не нужен смартфон | P-07 | тест сообщения |",
                        "| MSG-06 | Родителям не нужен смартфон | P-07 | тест сообщения |\n" + rows)
        rep = promise_lint.lint(self.proj)
        new = [p for p in rep["promises"] if int(p["id"].split("-")[1]) >= 10]
        self.assertEqual(len(new), 14)
        for p in new:
            self.assertIn("E5", [c for c, _ in p["issues"]], p["text"])
        self.assertEqual(sum(1 for p in rep["promises"] if p["ok"]), 6)  # эталонные обещания по-прежнему проходят

    def test_neutral_wording_still_passes(self):
        for t in ("работает лучше, чем страх", "предложение самому абоненту", "абсолютная база неизвестна",
                  "Ева блокирует большинство мошеннических звонков"):
            self.assertEqual(promise_lint.risky_phrases(t), [], t)

    def test_matrix_marks_message_tests(self):
        rc, out = run(promise_lint.main, ["--matrix"])
        self.assertIn("✓ тест сообщения", out)


class StageGates(Base):  # Д-9, Д-10
    def test_no_stage_skipping(self):
        self.set_stage("intake")
        self.assertEqual(run(project.main, ["stage", "options"])[0], 2)
        self.assertEqual(run(project.main, ["stage", "done"])[0], 2)
        self.set_stage("strategy")
        self.assertEqual(run(project.main, ["stage", "done"])[0], 2)
        self.assertEqual(run(project.main, ["stage", "research"])[0], 0)  # назад можно

    def test_forward_needs_stage_result(self):
        self.set_stage("research")
        (self.proj / "out" / "research.md").unlink()
        rc, out = run(project.main, ["stage", "options"])
        self.assertEqual(rc, 2)
        self.assertIn("research.md", out)

    def test_web_fetch_needs_plan_on_any_stage(self):
        for stage in ("intake", "options", "validation"):
            self.set_stage(stage)
            self.assertEqual(run(fetch_source.main, ["https://invalid.invalid/x"])[0], 3, stage)

    def test_rebuild_manifest_only_for_maintainer(self):  # Д-18
        self.assertEqual(run(fetch_source.main, ["--rebuild-manifest"])[0], 2)

    def test_missing_options_is_an_error(self):
        (self.proj / "out" / "options.md").unlink()
        (self.proj / "state" / "decisions.md").write_text("# Решения\n", encoding="utf-8")
        rc, out = run(decision_lint.main, [])
        self.assertEqual(rc, 1)
        self.assertIn("options.md", out)
        self.assertIn("decisions.md", out)
        self.assertNotIn("✓", out)

    def test_stop_gate_requires_artifacts(self):
        import stage_gate
        (self.proj / "out" / "comms-strategy.md").unlink()
        problems, _ = stage_gate.run(self.proj)
        self.assertTrue(any("comms-strategy.md" in p for p in problems), problems)
        self.set_stage("strategy")  # на самом этапе strategy документа ещё может не быть
        problems, _ = stage_gate.run(self.proj)
        self.assertFalse(any("comms-strategy.md" in p for p in problems), problems)


class SmallFixes(Base):
    def test_negative_estimate_refused(self):  # Д-24
        self.assertEqual(run(estimate.main, ["--sources", "-5"])[0], 2)

    def test_compare_without_baseline_fails(self):
        (self.proj / "baseline" / "chat-answer.md").unlink()
        self.assertEqual(run(compare.main, ["--no-write"])[0], 2)

    def test_compare_no_fake_zero_cost(self):  # Д-14
        (self.proj / "state" / "cost-ledger.csv").write_text(",".join(core.LEDGER_FIELDS) + "\n", encoding="utf-8")
        rc, out = run(compare.main, ["--no-write"])
        self.assertNotIn("| $0.00 |", out)
        self.assertIn("нет данных", out)

    def test_cgnat_refused(self):  # Д-25
        with self.assertRaises(ValueError):
            fetch_source.check_url("http://100.100.100.200/latest/meta-data")

    def test_hint_uses_full_inbox_path(self):  # Д-21
        from helpers import REPO
        for f in ("scripts/fetch_source.py", ".claude/skills/research/SKILL.md"):
            self.assertNotIn("fetch_source.py inbox/", (REPO / f).read_text(encoding="utf-8"), f)
