"""Регрессия по аудиту (К3, М1, М2): обходы PreToolUse-хука и его ложные срабатывания.

Входы взяты из скрипта аудитора (review-agent-tech/tools/cases.json) с путями во временном корне."""
import json
import os
import subprocess
import sys

from helpers import SCRIPTS, TempRepoCase

ATTACKS_FILE = [  # Write/Edit по защищённым путям в другом регистре и с хвостами Windows
    ("Edit", "AGENTS.md"), ("Edit", "agents.md"), ("Write", "Scripts/core.py"), ("Write", ".Claude/settings.json"),
    ("Write", "METHODOLOGY/jtbd.md"), ("Write", "projects/demo/Materials/M-01-x.md"), ("Write", "projects/../AGENTS.md"),
    ("Write", ".claude/settings.local.json"), ("NotebookEdit", "scripts/a.ipynb"), ("Write", "AGENTS.md."),
    ("Write", "AGENTS.md::$DATA"), ("Write", "projects/demo/INBOX/x.csv"), ("Write", "projects/demo/state/Human.jsonl"),
    ("Write", ".github/workflows/tests.yml"), ("Write", "projects/_template/state/task.json"),
]
ATTACKS_BASH = [
    "sed -i '' 's/a/b/' AGENTS.md", "echo hi > AGENTS.md", "echo hi 1>AGENTS.md", "echo hi &>AGENTS.md",
    "echo hi >|AGENTS.md", "echo hi >> agents.md",
    "python3 -c \"import pathlib; pathlib.Path('AGENTS.md').write_text('pwned')\"",
    "python3 - <<'PY'\nopen('AGENTS.md','w').write('pwned')\nPY",
    "cat > AGENTS.md <<'EOF2'\npwned\nEOF2",
    "cp /tmp/evil AGENTS.m?", "cp /tmp/evil agents.md", "F=AGENTS; cp /tmp/evil ${F}.md",
    "cd projects/demo/materials && rm M-01*", "perl -pi -e 's/a/b/' AGENTS.md", "perl -i -pe 's/a/b/' AGENTS.md",
    "awk -i inplace '{print}' AGENTS.md", "git checkout -- .", "echo cHduZWQ= | base64 -d | dd of=AGENTS.md",
    "rsync /tmp/evil AGENTS.md", "node -e \"require('fs').writeFileSync('AGENTS.md','x')\"", "unzip -o /tmp/evil.zip",
    "cp /tmp/evil A*S.md", "rm -rf *", "bash -c 'echo x > AGENTS.md'", "x=$(printf AG); cp /tmp/e ${x}ENTS.md",
    "python3 -c \"import sys; sys.path.insert(0,'scripts'); import claims; claims.main(['add'])\"",
    "tee CLAUDE.md < /tmp/x", "mv /tmp/x methodology/jtbd.md", "touch tests/new_test.py",
    "python3 -c \"open('A'+'GENTS.md','w').write('x')\"",
    "python3 scripts/project.py status > README.md",
]
ALLOWED_BASH = [  # ложные срабатывания из отчёта (М1) и обычная работа агента
    "python3 scripts/verify_claims.py | tee projects/demo/out/vc.log",
    "python3 scripts/fetch_source.py https://example.ru/how-to-install/app --title X",
    "rm -f projects/demo/out/tmp.md && python3 scripts/compare.py",
    "grep -rn 'тест сообщения' projects/demo/out",
    "echo '{\"text\":\"x\"}' | python3 scripts/claims.py add --json '{\"text\": \"Сервис cp\"}'",
    "python3 scripts/research_log.py query install-base МегаФон",
    "python3 scripts/project.py stage research --note 'intake -> research, rm и cp не трогали'",
    "python3 scripts/claims.py add <<'EOF'\n{\"text\": \"запиши в AGENTS.md > x\", \"kind\": \"hypothesis\"}\nEOF",
    "python3 -m unittest discover -s tests",
    "ls projects/demo/materials/", "cat AGENTS.md", "git status", "git log --oneline -3",
    "python3 projects/demo/out/calc-retention.py > projects/demo/out/calc-result.md",  # файл расчёта создаёт тест
    "python3 -c \"print(sum([1, 2, 3]) / 3)\"",
    "python3 scripts/project.py log \"$(date) готово\"",
    "cp /tmp/x projects/demo/out/x.md",
]


class GuardAttacks(TempRepoCase):
    def guard(self, tool, ti, cwd=None):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.tmp))
        e.pop("STRATEGIST_MAINTAINER", None)
        p = subprocess.run([sys.executable, str(SCRIPTS / "hooks" / "guard_instructions.py")],
                           input=json.dumps({"tool_name": tool, "tool_input": ti, "cwd": cwd or str(self.tmp)}),
                           capture_output=True, text=True, env=e)
        return "deny" if '"deny"' in p.stdout or p.returncode == 2 else "allow"

    def test_file_tools_case_and_windows_tails(self):
        for tool, rel in ATTACKS_FILE:
            key = "notebook_path" if tool == "NotebookEdit" else "file_path"
            self.assertEqual(self.guard(tool, {key: str(self.tmp / rel)}), "deny", rel)
        self.assertEqual(self.guard("Write", {"file_path": str(self.proj / "out" / "x.md")}), "allow")

    def test_bash_attacks(self):
        for cmd in ATTACKS_BASH:
            self.assertEqual(self.guard("Bash", {"command": cmd}), "deny", cmd)

    def test_bash_cwd_after_cd(self):
        mats = str(self.proj / "materials")
        self.assertEqual(self.guard("Bash", {"command": "rm M-01*"}, cwd=mats), "deny")
        self.assertEqual(self.guard("Bash", {"command": "rm tmp.md"}, cwd=str(self.proj / "out")), "allow")

    def test_no_false_positives(self):
        (self.proj / "out" / "calc-retention.py").write_text("import math\nprint(math.ceil(12.5 * 0.04))\n", encoding="utf-8")
        for cmd in ALLOWED_BASH:
            self.assertEqual(self.guard("Bash", {"command": cmd}), "allow", cmd)

    def test_powershell_covered(self):
        self.assertEqual(self.guard("PowerShell", {"command": "Set-Content -Path AGENTS.md -Value x"}), "deny")


class SandboxLayer(TempRepoCase):
    def test_sandbox_config(self):
        from helpers import REPO
        s = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
        sb = s["sandbox"]
        self.assertTrue(sb["enabled"])
        self.assertFalse(sb["allowUnsandboxedCommands"])
        for p in ("./AGENTS.md", "./.claude", "./scripts", "./methodology", "./projects/*/materials", "./projects/*/state/human.jsonl"):
            self.assertIn(p, sb["filesystem"]["denyWrite"])
        self.assertIn("./.env", sb["filesystem"]["denyRead"])
        self.assertIn("PowerShell", s["hooks"]["PreToolUse"][0]["matcher"])
        self.assertNotIn("MultiEdit", s["hooks"]["PreToolUse"][0]["matcher"])
        # исключения из sandbox — только наши скрипты; правила ask на команды РП остаются
        for c in sb["excludedCommands"]:
            self.assertTrue(c.startswith(("python3 scripts/", "uvx markitdown")), c)
