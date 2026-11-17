"""Регрессия по аудиту (К1): агент не может сам «подтвердить» факт или план.

Воспроизведения из docs/review/3-agent-tech.md: verified: human через claims.py add, правка claims.jsonl
и research-plan.json руками, снимок собственного файла агента как основание факта.
"""
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout

from helpers import REPO, SCRIPTS, TempRepoCase
import claims as claims_cli
import core
import fetch_source
import project
import verify_claims


def run(fn, argv, stdin=None):
    old = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            rc = fn(argv)
    finally:
        sys.stdin = old
    return rc, out.getvalue() + err.getvalue()


class SelfVerification(TempRepoCase):
    def test_add_cannot_set_verified(self):
        rc, _ = run(claims_cli.main, ["add"], stdin=json.dumps(
            {"text": "Сервис подключили 30 млн абонентов", "kind": "fact", "verified": "human",
             "sources": [{"url": "https://example.com"}]}, ensure_ascii=False))
        c = self.claims()[-1]
        self.assertNotEqual(c.get("text"), "Сервис подключили 30 млн абонентов", "claim с verified не должен добавляться")
        rep = verify_claims.check(self.proj)
        self.assertEqual(rep["human"], [])

    def test_hand_edited_verified_flag_is_ignored(self):
        self.edit_claim("C-005", text="Через Еву можно защитить до 77 номеров", verified="human")
        rep = verify_claims.check(self.proj)
        self.assertNotIn("C-005", rep["human"])
        self.assertIn("C-005", [d[0] for d in rep["downgrade"]])

    def test_human_record_counts_and_breaks_on_text_change(self):
        self.edit_claim("C-005", text="Через Еву можно защитить до 77 номеров")
        self.assertEqual(run(claims_cli.main, ["human-verified", "C-005", "--note", "сверил в приложении"])[0], 0)
        self.assertIn("C-005", verify_claims.check(self.proj)["human"])
        self.edit_claim("C-005", text="Через Еву можно защитить до 500 номеров")  # текст изменили после подтверждения
        self.assertNotIn("C-005", verify_claims.check(self.proj)["human"])

    def test_hand_edited_plan_approval_is_ignored(self):
        import estimate
        t = core.load_task(self.proj)
        t["stage"] = "research"
        core.write_json(self.proj / "state" / "task.json", t)
        run(estimate.main, ["--sources", "2", "--searches", "1", "--save"])
        plan = core.read_json(self.proj / "state" / "research-plan.json")
        plan["approved"] = True
        core.write_json(self.proj / "state" / "research-plan.json", plan)
        self.assertEqual(run(fetch_source.main, ["https://example.com/page"])[0], 3)
        self.assertEqual(run(project.main, ["approve-plan", "--note", "РП: начать"])[0], 0)
        self.assertTrue(project.plan_approved(self.proj))

    def test_agent_file_cannot_become_snapshot(self):
        calc = self.proj / "out" / "calc.md"
        calc.write_text("Сервисом пользуются 30 млн абонентов МегаФона " * 5, encoding="utf-8")
        rc, out = run(fetch_source.main, [str(calc), "--kind", "document"])
        self.assertNotEqual(rc, 0)
        self.assertFalse(any("calc" in p.name for p in (self.proj / "materials").glob("M-*.md")))


class HumanOnlyCommandsGuard(TempRepoCase):
    def guard(self, tool, ti, mode="default"):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.tmp))
        e.pop("STRATEGIST_MAINTAINER", None)
        p = subprocess.run([sys.executable, str(SCRIPTS / "hooks" / "guard_instructions.py")],
                           input=json.dumps({"tool_name": tool, "tool_input": ti, "permission_mode": mode}),
                           capture_output=True, text=True, env=e)
        return "deny" if '"deny"' in p.stdout or p.returncode == 2 else "allow"

    def test_human_ledger_is_protected(self):
        hl = str(self.proj / "state" / "human.jsonl")
        self.assertEqual(self.guard("Write", {"file_path": hl, "content": "{}"}), "deny")
        self.assertEqual(self.guard("Edit", {"file_path": hl}), "deny")
        self.assertEqual(self.guard("Bash", {"command": f"echo '{{}}' >> {hl}"}), "deny")

    def test_human_commands_only_in_canonical_form(self):
        self.assertEqual(self.guard("Bash", {"command": "python3 scripts/claims.py human-verified C-005 --note 'сверил'"}), "allow")
        self.assertEqual(self.guard("Bash", {"command": "python3 scripts/project.py approve-plan --note 'начать'"}), "allow")
        self.assertEqual(self.guard("Bash", {"command": "python3 ./scripts/claims.py human-verified C-005 --note x"}), "deny")
        self.assertEqual(self.guard("Bash", {"command": "cd . && python3 scripts/project.py approve-plan"}), "deny")
        self.assertEqual(self.guard("Bash", {"command": "python3 scripts/project.py --project demo approve-plan"}), "deny")

    def test_human_commands_denied_without_prompts(self):
        for mode in ("bypassPermissions", "dontAsk"):
            self.assertEqual(self.guard("Bash", {"command": "python3 scripts/project.py approve-plan"}, mode), "deny", mode)

    def test_settings_ask_rules(self):
        s = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
        ask = s["permissions"].get("ask", [])
        self.assertIn("Bash(python3 scripts/claims.py human-verified *)", ask)
        self.assertIn("Bash(python3 scripts/project.py approve-plan*)", ask)
        self.assertEqual(s["permissions"].get("disableBypassPermissionsMode"), "disable")
        for rule in s["permissions"]["allow"]:
            self.assertNotIn("human-verified", rule)
            self.assertNotIn("approve-plan", rule)
