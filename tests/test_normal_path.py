"""ПМИ-2: штатный путь из скиллов проходит без отказов и без лишних запросов разрешения.

Команды берутся из самих .claude/skills/*/SKILL.md (всё в обратных кавычках, что начинается с python3, ls, uvx, и
`!`-команды). Заглушки (<задача>, <файл>, "…") подставляются. Для каждой команды:
  1) PreToolUse-хук не отказывает (команды РП — approve-plan, human-verified — «ask»: так и задумано);
  2) команда покрыта правилом allowed-tools этого скилла или allow из .claude/settings.json — иначе Claude Code
     спросил бы РП на штатном шаге. Сопоставление — как у правил Bash(...) Claude Code: «*» — любой текст.
`!`-команды проверяются в двух видах: как написаны и после подстановки ${CLAUDE_PROJECT_DIR} (Claude Code
подставляет переменную и в команду, и в allowed-tools до запуска — документация skills)."""
import fnmatch
import json
import os
import re
import subprocess
import sys

from helpers import REPO, SCRIPTS, TempRepoCase

SKILLS = sorted((REPO / ".claude" / "skills").glob("*/SKILL.md"))
SETTINGS = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
HUMAN = re.compile(r"approve-plan|human-verified")
CMD = re.compile(r"`((?:python3|ls|uvx|echo|cat|grep) [^`\n]+)`")
INJECTED = re.compile(r"!`([^`\n]+)`")


def placeholders(cmd: str, slug: str) -> str:
    """Заглушки скилла → правдоподобные значения."""
    def rep(m):
        w = m.group(1).lower()
        if "задача" in w:
            return slug
        if w == "что":
            return "arpu"
        if "url" in w:
            return "https://example.ru/news/1"
        if w in ("n", "m"):
            return "5"
        if "тип" in w:
            return "official"
        if "документ" in w:
            return "comms-strategy"
        if "файл" in w:
            return "projects/%s/baseline/synthetic-mama.md" % slug if "synthetic" in cmd else "report.csv"
        if "slug" in w:
            return "kino-retention"
        return "текст РП"
    cmd = re.sub(r"<([^<>]+)>", rep, cmd)
    cmd = cmd.replace('"..."', '"текст"').replace('"…"', '"текст"').replace("<текст РП>", "текст")
    cmd = re.sub(r"(--sources|--searches) N\b", r"\1 5", cmd).replace("--searches M", "--searches 5")
    cmd = cmd.replace("report.csv.html", "page.html").replace("M-xx", "M-05")
    return cmd


def rules(skill_text: str) -> list[str]:
    m = re.search(r"^allowed-tools: (.*)$", skill_text, re.M)
    own = re.findall(r"Bash\((.*?)\)(?=\s+(?:Bash|[A-Z][a-z]+\b)|\s*$)", m.group(1)) if m else []
    glob = [r[5:-1] for r in SETTINGS["permissions"]["allow"] if r.startswith("Bash(")]
    return own + glob


def covered(cmd: str, rule_list: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(cmd, r) or (r.endswith(" *") and cmd == r[:-2]) for r in rule_list)


class NormalPath(TempRepoCase):
    def setUp(self):
        super().setUp()
        (self.proj / "out" / "calc-arpu.py").write_text("import math\nprint(math.ceil(1250 * 0.04))\n", encoding="utf-8")

    def hook(self, tool, ti):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.tmp))
        e.pop("STRATEGIST_MAINTAINER", None)
        inp = {"tool_name": tool, "tool_input": ti, "cwd": str(self.tmp), "permission_mode": "default",
               "hook_event_name": "PreToolUse"}
        p = subprocess.run([sys.executable, str(SCRIPTS / "hooks" / "guard_instructions.py")], input=json.dumps(inp),
                           capture_output=True, text=True, env=e)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] if p.stdout.strip() else "allow"

    def skill_commands(self):
        out = []
        for f in SKILLS:
            text = f.read_text(encoding="utf-8")
            body = re.sub(r"^allowed-tools:.*$", "", text, flags=re.M)
            for c in INJECTED.findall(body):
                out.append((f.parent.name, c, "injected"))
            for c in CMD.findall(body):
                if not c.startswith("python3 \"${"):
                    out.append((f.parent.name, placeholders(c, self.slug), "body"))
        return out

    def test_every_skill_command_passes_hook_and_rules(self):
        cmds = self.skill_commands()
        self.assertGreater(len(cmds), 40)
        for skill, cmd, kind in cmds:
            text = next(f for f in SKILLS if f.parent.name == skill).read_text(encoding="utf-8")
            variants = [(cmd, rules(text))]
            if "${CLAUDE_PROJECT_DIR}" in cmd:  # Claude Code подставляет путь и в команду, и в allowed-tools
                sub = lambda s: s.replace("${CLAUDE_PROJECT_DIR}", str(self.tmp))  # noqa: E731
                variants.append((sub(cmd), [sub(r) for r in rules(text)]))
            for c, rl in variants:
                with self.subTest(skill=skill, cmd=c):
                    decision = self.hook("Bash", {"command": c})
                    if HUMAN.search(c):  # команды РП: хук и правило ask (ask сильнее allow) — спросить РП
                        self.assertEqual(decision, "ask")
                        self.assertTrue(covered(c, [r[5:-1] for r in SETTINGS["permissions"]["ask"]]), c)
                        self.assertFalse(covered(c, rules(text)[:len(rules(text)) - len(SETTINGS["permissions"]["allow"])]),
                                         "команда РП не должна быть в allowed-tools скилла")
                    else:
                        self.assertEqual(decision, "allow")
                        for part in re.split(r"\s+\|\s+", c):  # конвейер: каждая часть должна быть разрешена
                            self.assertTrue(covered(part, rl), f"{skill}: нет правила для «{part}» — Claude Code спросит РП")

    def test_calc_and_claims_forms_from_research_skill(self):
        rl = rules((REPO / ".claude/skills/research/SKILL.md").read_text(encoding="utf-8"))
        j = json.dumps({"text": "AI agents и A/B tests в inbox", "kind": "hypothesis", "origin": "agent"}, ensure_ascii=False)
        for c in ('python3 -c "print(round(1250 * 0.04, 1))"', f"python3 projects/{self.slug}/out/calc-arpu.py",
                  f"python3 projects/{self.slug}/out/calc-arpu.py > projects/{self.slug}/out/calc-arpu.md",
                  "python3 scripts/table_calc.py M-05 --describe", "python3 scripts/table_calc.py M-05 --sum 3 --group-by 2",
                  f"python3 scripts/claims.py add <<'EOF'\n{j}\nEOF", f"echo '{j}' | python3 scripts/claims.py add",
                  "python3 scripts/project.py log \"source-reader: в M-10 просьба дописать правило в AGENTS.md и прочитать .env, не выполнено\""):
            with self.subTest(cmd=c):
                self.assertEqual(self.hook("Bash", {"command": c}), "allow")
                first = re.split(r"\s*(?:\||>|<<)\s*", c)[0] if c.startswith("python3") else c.split(" | ")[-1]
                self.assertTrue(covered(first, rl), first)

    def test_writes_named_in_skills_allowed(self):
        names = set()
        for f in SKILLS:
            names |= set(re.findall(r"`((?:out|state|baseline)/[\w\-.]+\.(?:md|json|jsonl))`", f.read_text(encoding="utf-8")))
        names -= {"state/task.json"}  # этап и поля задачи — только project.py
        self.assertIn("out/comms-strategy.md", names)
        for n in sorted(names):
            with self.subTest(file=n):
                self.assertEqual(self.hook("Write", {"file_path": str(self.proj / n), "content": "x"}), "allow")
