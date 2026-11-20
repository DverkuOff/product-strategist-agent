"""Ворота качества задачи: одни и те же проверки для Stop-хука и для перехода этапа (project.py stage).

Проверяется всё, что уже есть в задаче, независимо от текущего этапа: откат на research не выключает проверку
обещаний в out/comms-strategy.md, а переход дальше при красных проверках запрещён.
  - утверждения (если есть): verify_claims — факт без снимка → гипотеза, метки в out/ согласованы;
  - варианты и решения (если есть out/options.md или решения в state/decisions.md): decision_lint;
  - обещания (если есть out/comms-strategy.md): promise_lint;
  - результаты пройденных этапов (по этапу в task.json) обязательны.
"""
from __future__ import annotations

import re
from pathlib import Path

import core
import decision_lint
import promise_lint
import verify_claims


def problems(proj: Path, fix: bool = False) -> tuple[list[str], list[str]]:
    """(проблемы, которые блокируют; предупреждения). fix=True — записать понижения (как Stop-хук)."""
    probs: list[str] = []
    warns: list[str] = []
    stage = core.load_task(proj).get("stage", "intake")
    claims_file = proj / "state" / "claims.jsonl"
    if claims_file.exists() and claims_file.stat().st_size > 0:
        rep = verify_claims.check(proj)
        n = verify_claims.apply_fix(proj, rep) if fix else 0
        for cid, _, detail in rep["downgrade"]:
            probs.append(f"{cid} {'понижен' if fix else 'будет понижен'} до гипотезы ({detail}) — поправь формулировку и метку в out/")
        probs.extend(f"claims: {e}" for e in rep["errors"])
        warns.extend(f"claims: {w}" for w in rep["warnings"])
        if n:
            core.append_journal(proj, f"Ворота качества: понижено {n} утвержд. до гипотез")
    probs.extend(f"этапы: {m}" for m in core.missing_artifacts(proj, stage=stage))
    dec = proj / "state" / "decisions.md"
    has_decisions = dec.exists() and re.search(r"^##\s+D-\d+", dec.read_text(encoding="utf-8"), re.M)
    if (proj / "out" / "options.md").exists() or has_decisions:
        probs.extend(f"варианты: {e}" for e in decision_lint.check_options(proj))
        derrs, downs = decision_lint.check_decisions(proj)
        probs.extend(f"решения: {e}" for e in derrs)
        if fix:
            decision_lint.apply_downgrades(proj, downs)
        probs.extend(f"решение {d}: вердикт «делать» {'понижен' if fix else 'будет понижен'} до «нужна ясность» ({why})"
                     for d, why in downs)
        warns.extend(f"варианты: {w}" for w in decision_lint.option_warnings(proj))
    passed_strategy = "strategy" in core.stages_passed(stage)
    if (proj / "out" / "comms-strategy.md").exists() or passed_strategy:
        rep = promise_lint.lint(proj)
        for pr in rep["promises"]:
            for code, msg in pr["issues"]:
                probs.append(f"обещание {pr['id']} «{pr['text'][:60]}»: {code} {msg}")
        probs.extend(f"обещания: {e}" for e in rep["errors"])
        warns.extend(f"обещания: {w}" for w in rep["warnings"])
    return probs, warns
