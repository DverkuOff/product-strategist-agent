"""Общее для хуков: чтение JSON со stdin, корень проекта, безопасный запуск."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import core  # noqa: E402,F401


def read_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def root(inp: dict | None = None) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    if inp and inp.get("cwd"):
        return core.repo_root(inp["cwd"])
    return core.repo_root()


def emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))
