"""Общее для тестов: временный репозиторий с копией эталонной задачи (tests/fixtures/demo)."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
FIXTURE = REPO / "tests" / "fixtures" / "demo"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "hooks"))


class TempRepoCase(unittest.TestCase):
    """Каждый тест получает свой корень: AGENTS.md + projects/_template + projects/demo (копия эталона)."""

    slug = "demo"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="strategist-test-"))
        (self.tmp / "AGENTS.md").write_text("# test\n", encoding="utf-8")
        shutil.copytree(REPO / "projects" / "_template", self.tmp / "projects" / "_template")
        shutil.copytree(FIXTURE, self.tmp / "projects" / self.slug)
        (self.tmp / "projects" / ".active").write_text(self.slug + "\n", encoding="utf-8")
        self.proj = self.tmp / "projects" / self.slug
        self._env = {k: os.environ.get(k) for k in ("STRATEGIST_ROOT", "CLAUDE_PROJECT_DIR", "STRATEGIST_MAINTAINER")}
        os.environ["STRATEGIST_ROOT"] = str(self.tmp)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.tmp)
        os.environ.pop("STRATEGIST_MAINTAINER", None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- утилиты правки состояния ---
    def claims(self) -> list[dict]:
        return [json.loads(x) for x in (self.proj / "state" / "claims.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]

    def write_claims(self, rows: list[dict]) -> None:
        (self.proj / "state" / "claims.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def edit_claim(self, cid: str, **fields) -> None:
        rows = self.claims()
        for r in rows:
            if r["id"] == cid:
                r.update(fields)
        self.write_claims(rows)

    def replace_in(self, rel: str, old: str, new: str) -> None:
        p = self.proj / rel
        s = p.read_text(encoding="utf-8")
        assert old in s, f"нет «{old}» в {rel}"
        p.write_text(s.replace(old, new), encoding="utf-8")
