"""Регрессия по аудиту (К2): секреты не попадают в снимки и в контекст агента."""
import json
import os
import subprocess
import sys

from helpers import REPO, SCRIPTS, TempRepoCase
import fetch_source
from test_audit_selfverify import run


def guard(tmp, command):
    e = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp))
    e.pop("STRATEGIST_MAINTAINER", None)
    p = subprocess.run([sys.executable, str(SCRIPTS / "hooks" / "guard_instructions.py")],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
                       capture_output=True, text=True, env=e)
    return "deny" if '"deny"' in p.stdout or p.returncode == 2 else "allow"


class SecretsIntoSnapshots(TempRepoCase):
    def test_env_in_repo_root_refused(self):
        (self.tmp / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-FAKE\n", encoding="utf-8")
        self.assertNotEqual(run(fetch_source.main, [str(self.tmp / ".env"), "--kind", "document"])[0], 0)
        self.assertNotEqual(run(fetch_source.main, [".env"])[0], 0)
        self.assertFalse(any("FAKE" in p.read_text(encoding="utf-8") for p in (self.proj / "materials").glob("M-*.md")))

    def test_secret_like_names_refused_even_in_inbox(self):
        for name in (".env", ".env.local", "id_rsa", "server.pem", "aws-credentials.txt"):
            f = self.inbox_file(name, "SECRET=1\n" * 30)
            self.assertNotEqual(run(fetch_source.main, [str(f)])[0], 0, name)

    def test_symlink_out_of_inbox_refused(self):
        outside = self.tmp / "outside.txt"
        outside.write_text("PASSWORD=hunter2 " * 30, encoding="utf-8")
        (self.proj / "inbox").mkdir(exist_ok=True)
        link = self.proj / "inbox" / "notes.txt"
        link.symlink_to(outside)
        self.assertNotEqual(run(fetch_source.main, [str(link)])[0], 0)

    def test_home_files_refused(self):
        self.assertNotEqual(run(fetch_source.main, [os.path.expanduser("~/.zshrc")])[0], 0)


class SecretsViaBash(TempRepoCase):
    def test_env_mentions_denied(self):
        for cmd in ("cat .env", "head -5 ./.ENV", "less .env.local", "grep KEY .env",
                    "python3 scripts/fetch_source.py .env --kind document", "cp .Env /tmp/x",
                    "cat ~/.ssh/id_rsa", "cat ~/.aws/credentials"):
            self.assertEqual(guard(self.tmp, cmd), "deny", cmd)

    def test_recursive_search_from_root_denied(self):
        for cmd in ("grep -r API_KEY .", "grep -rn KEY", "rg KEY", "grep -R token /Users"):
            self.assertEqual(guard(self.tmp, cmd), "deny", cmd)
        self.assertEqual(guard(self.tmp, "grep -rn 'тест сообщения' projects/demo/out"), "allow")

    def test_settings(self):
        s = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow, deny = s["permissions"]["allow"], s["permissions"]["deny"]
        self.assertNotIn("Bash(grep *)", allow)
        self.assertNotIn("Bash(head *)", allow)
        for rule in ("Read(./.env)", "Read(./.env.*)", "Read(**/.env)", "Read(~/.ssh/**)", "Read(~/.aws/**)"):
            self.assertIn(rule, deny)

    def test_source_reader_has_no_network(self):
        import core
        meta, body = core.parse_frontmatter((REPO / ".claude" / "agents" / "source-reader.md").read_text(encoding="utf-8"))
        self.assertEqual([t.strip() for t in meta["tools"].split(",")], ["Read", "Grep", "Glob"])
        self.assertNotIn("WebFetch", body)
