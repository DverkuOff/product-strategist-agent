#!/usr/bin/env python3
"""Stop: «ворота качества» перед тем, как агент отдаст ход руководителю продукта.

- любой этап, если есть утверждения: verify_claims (факт без снимка → гипотеза, метки в out/ согласованы);
- этапы options и дальше: decision_lint (≥3 вариантов, «Цена бездействия», вердикт с причиной, «Что заставит пересмотреть»;
  «делать» без проработанного варианта → «нужна ясность»);
- этапы strategy и дальше, если есть out/comms-strategy.md: promise_lint (обещания опираются на свойства-факты).
Нашли проблему → exit 2: Claude Code не завершает ход и передаёт агенту текст ошибок (stderr).
Повторный стоп подряд (stop_hook_active) не блокируем, а показываем предупреждение РП — без бесконечного цикла.
Значит, хук возвращает агента на исправление один раз за ход; незакрытые замечания РП видит в сообщении.
Сбой самой проверки (битый task.json) — fail-closed: первый стоп блокируется с объяснением.
"""
from __future__ import annotations

import sys

from _hook import emit, read_input, root

import core  # noqa: E402
import decision_lint  # noqa: E402
import promise_lint  # noqa: E402
import verify_claims  # noqa: E402

CLAIM_STAGES = {"research", "options", "strategy", "validation", "done"}
PROMISE_STAGES = {"strategy", "validation", "done"}


def run(proj) -> tuple[list[str], list[str]]:
    """(проблемы, которые блокируют стоп; предупреждения, которые показываем РП и агенту)."""
    problems: list[str] = []
    warnings: list[str] = []
    stage = core.load_task(proj).get("stage", "intake")
    claims_file = proj / "state" / "claims.jsonl"
    if claims_file.exists() and claims_file.stat().st_size > 0:  # утверждения проверяются на любом этапе
        rep = verify_claims.check(proj)
        n = verify_claims.apply_fix(proj, rep)
        for cid, _, detail in rep["downgrade"]:
            problems.append(f"{cid} понижен до гипотезы ({detail}) — поправь формулировку и метку в out/")
        problems.extend(f"claims: {e}" for e in rep["errors"])
        warnings.extend(f"claims: {w}" for w in rep["warnings"])
        if n:
            core.append_journal(proj, f"Stop-хук: понижено {n} утвержд. до гипотез")
    if stage in CLAIM_STAGES and stage != "research":
        problems.extend(f"варианты: {e}" for e in decision_lint.check_options(proj))
        derrs, downs = decision_lint.check_decisions(proj)
        problems.extend(f"решения: {e}" for e in derrs)
        decision_lint.apply_downgrades(proj, downs)
        problems.extend(f"решение {d}: вердикт «делать» понижен до «нужна ясность» ({why})" for d, why in downs)
        warnings.extend(f"варианты: {w}" for w in decision_lint.option_warnings(proj))
    if stage in PROMISE_STAGES and (proj / "out" / "comms-strategy.md").exists():
        rep = promise_lint.lint(proj)
        for pr in rep["promises"]:
            for code, msg in pr["issues"]:
                problems.append(f"обещание {pr['id']} «{pr['text'][:60]}»: {code} {msg}")
        problems.extend(f"обещания: {e}" for e in rep["errors"])
        warnings.extend(f"обещания: {w}" for w in rep["warnings"])
    return problems, warnings


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
