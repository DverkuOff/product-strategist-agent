#!/usr/bin/env python3
"""Stop: «ворота качества» перед тем, как агент отдаст ход руководителю продукта.

Проверяется всё, что уже есть в задаче, НЕЗАВИСИМО от текущего этапа (scripts/gates.py): откат на research не
выключает проверку обещаний, а project.py stage не переводит дальше при красных проверках.
- если есть утверждения: verify_claims (факт без снимка → гипотеза, метки в out/ согласованы);
- если есть out/options.md или решения: decision_lint (≥3 вариантов, «Цена бездействия», вердикт с причиной,
  «Что заставит пересмотреть»; «делать» без проработанного варианта → «нужна ясность»);
- если есть out/comms-strategy.md (а после strategy — обязательно): promise_lint;
- результаты пройденных этапов (research.md, options.md и решение, comms-strategy.md и реестр свойств,
  validation-plan.md на done) обязательны: пустой этап не проходит ворота «✓».
Нашли проблему → exit 2: Claude Code не завершает ход и передаёт агенту текст ошибок (stderr).
Повторный стоп подряд (stop_hook_active) не блокируем, а показываем предупреждение РП — без бесконечного цикла.
Значит, хук возвращает агента на исправление один раз за ход; незакрытые замечания РП видит в сообщении.
Сбой самой проверки (битый task.json) — fail-closed: первый стоп блокируется с объяснением.
"""
from __future__ import annotations

import sys

from _hook import emit, read_input, root

import core  # noqa: E402,F401
import gates  # noqa: E402


def run(proj) -> tuple[list[str], list[str]]:
    """(проблемы, которые блокируют стоп; предупреждения, которые показываем РП и агенту)."""
    return gates.problems(proj, fix=True)


LAST_INPUT: dict = {}


def main() -> int:
    inp = read_input()
    LAST_INPUT.update(inp)
    r = root(inp)
    proj = core.project_path(None, r)
    if not proj:
        return 0
    problems, warnings = run(proj)
    warn_text = ("\nПредупреждения (не блокируют, но проверь):\n- " + "\n- ".join(warnings[:10])) if warnings else ""
    if not problems:
        if warnings:
            emit({"systemMessage": "Ворота качества пройдены с предупреждениями:" + warn_text.split(":", 1)[1]})
        return 0
    head = "Ворота качества не пройдены:\n- " + "\n- ".join(problems[:15])
    if len(problems) > 15:
        head += f"\n… и ещё {len(problems) - 15}"
    head += warn_text
    if inp.get("stop_hook_active"):
        core.append_journal(proj, f"Stop-хук: ход завершён с {len(problems)} незакрытыми замечаниями")
        emit({"systemMessage": head + "\n(Агент уже пытался исправить; замечания остаются — проверь вручную: python3 scripts/verify_claims.py, python3 scripts/promise_lint.py)"})
        return 0
    print(head + "\nИсправь это до ответа РП (подробно: python3 scripts/verify_claims.py и python3 scripts/promise_lint.py).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    _inp: dict = {}
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        # fail-closed: сбой проверки (например, битый task.json) не должен молча выключать ворота.
        # Первый стоп блокируем с понятным сообщением, повторный отпускаем, чтобы не зациклиться.
        msg = (f"Ворота качества не смогли выполниться: {type(e).__name__}: {e}. Проверь файлы состояния "
               "(state/task.json, state/claims.jsonl — валидный JSON) и запусти python3 scripts/verify_claims.py.")
        if LAST_INPUT.get("stop_hook_active"):
            emit({"systemMessage": msg})
            sys.exit(0)
        print(msg, file=sys.stderr)
        sys.exit(2)
