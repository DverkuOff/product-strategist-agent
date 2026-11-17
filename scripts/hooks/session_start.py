#!/usr/bin/env python3
"""SessionStart: сводка «где остановились, что дальше» для нового или продолженного чата.

Печатает обычный текст: Claude Code добавляет stdout SessionStart-хука в контекст модели.
"""
from __future__ import annotations

import os
import sys

from _hook import SCRIPTS, read_input, root  # noqa: F401

import core  # noqa: E402
import project  # noqa: E402


def main() -> int:
    inp = read_input()
    r = root(inp)
    os.environ.setdefault("STRATEGIST_ROOT", str(r))
    proj = core.project_path(None, r)
    head = "[Стратег Фабрики продуктов] Состояние из projects/ (файлы, а не память модели)."
    if not proj:
        others = [d.name for d in (r / "projects").iterdir() if d.is_dir() and not d.name.startswith((".", "_"))] if (r / "projects").is_dir() else []
        print(head)
        print("Активной задачи нет. Новая задача: python3 scripts/project.py new <slug> \"<название>\", затем скилл intake.")
        if others:
            print("Есть задачи: " + ", ".join(others) + " (выбрать: python3 scripts/project.py use <slug>)")
        return 0
    print(head)
    print(project.status_text(proj))
    print("Продолжай с текущего этапа; сделанное не повторяй. Если есть «ЖДЁТ РЕШЕНИЯ РП» — сначала задай этот вопрос.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — хук не должен ломать запуск сессии
        print(f"[Стратег] сводка недоступна: {type(e).__name__}: {e}. Выполни python3 scripts/project.py status")
        sys.exit(0)
