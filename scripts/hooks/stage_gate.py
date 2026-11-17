#!/usr/bin/env python3
"""Stop: «ворота качества» перед тем, как агент отдаст ход руководителю продукта.

- этапы research и дальше: verify_claims (факт без снимка → гипотеза, метки в out/ согласованы);
- этапы strategy и дальше, если есть out/comms-strategy.md: promise_lint (обещания опираются на свойства-факты).
Нашли проблему → exit 2: Claude Code не завершает ход и передаёт агенту текст ошибок (stderr).
Повторный стоп подряд (stop_hook_active) не блокируем, а показываем предупреждение РП — без бесконечного цикла.
"""
from __future__ import annotations

import sys

from _hook import emit, read_input, root

import core  # noqa: E402
import promise_lint  # noqa: E402
import verify_claims  # noqa: E402

CLAIM_STAGES = {"research", "options", "strategy", "validation", "done"}
PROMISE_STAGES = {"strategy", "validation", "done"}


def run(proj) -> list[str]:
    problems: list[str] = []
    stage = core.load_task(proj).get("stage", "intake")
    claims_file = proj / "state" / "claims.jsonl"
    if stage in CLAIM_STAGES and claims_file.exists() and claims_file.stat().st_size > 0:
        rep = verify_claims.check(proj)
        n = verify_claims.apply_fix(proj, rep)
        for cid, _, detail in rep["downgrade"]:
            problems.append(f"{cid} понижен до гипотезы ({detail}) — поправь формулировку и метку в out/")
        problems.extend(f"claims: {e}" for e in rep["errors"])
        if n:
            core.append_journal(proj, f"Stop-хук: понижено {n} утвержд. до гипотез")
    if stage in PROMISE_STAGES and (proj / "out" / "comms-strategy.md").exists():
        rep = promise_lint.lint(proj)
        for pr in rep["promises"]:
            for code, msg in pr["issues"]:
                problems.append(f"обещание {pr['id']} «{pr['text'][:60]}»: {code} {msg}")
        problems.extend(f"обещания: {e}" for e in rep["errors"])
    return problems


def main() -> int:
    inp = read_input()
    r = root(inp)
    proj = core.project_path(None, r)
    if not proj:
        return 0
    problems = run(proj)
    if not problems:
        return 0
    head = "Ворота качества не пройдены:\n- " + "\n- ".join(problems[:15])
    if len(problems) > 15:
        head += f"\n… и ещё {len(problems) - 15}"
    if inp.get("stop_hook_active"):
        core.append_journal(proj, f"Stop-хук: ход завершён с {len(problems)} незакрытыми замечаниями")
        emit({"systemMessage": head + "\n(Агент уже пытался исправить; замечания остаются — проверь вручную: python3 scripts/verify_claims.py, python3 scripts/promise_lint.py)"})
        return 0
    print(head + "\nИсправь это до ответа РП (подробно: python3 scripts/verify_claims.py и python3 scripts/promise_lint.py).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — сбой проверки не должен запирать сессию
        print(f"stage_gate: сбой проверки {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
