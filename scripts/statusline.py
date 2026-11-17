#!/usr/bin/env python3
"""Строка состояния Claude Code: задача · этап · стоимость сессии (оценка по прейскуранту API)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402


def main() -> int:
    try:
        inp = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        inp = {}
    r = Path(os.environ.get("CLAUDE_PROJECT_DIR") or (inp.get("workspace") or {}).get("project_dir") or core.repo_root())
    proj = core.project_path(None, r)
    cost = (inp.get("cost") or {}).get("total_cost_usd")
    model = (inp.get("model") or {}).get("display_name", "")
    parts = ["Стратег"]
    if proj:
        t = core.load_task(proj)
        parts.append(f"{proj.name} · этап {t.get('stage', '?')}")
        if t.get("waiting_for"):
            parts.append("ждёт решения РП")
        total = core.ledger_total(proj)
        if total:
            parts.append(f"задача ${total:.2f}")
    else:
        parts.append("нет активной задачи")
    if cost is not None:
        parts.append(f"сессия ${cost:.2f}")
    if model:
        parts.append(model)
    print(" · ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
