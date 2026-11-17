#!/usr/bin/env python3
"""Отчёт о стоимости задачи из state/cost-ledger.csv: по этапам, моделям и агентам.

Стоимость — оценка по прейскуранту Claude API (на подписке это не счёт, а эквивалент).
  python3 scripts/cost_report.py [--project <slug>] [--md]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402


def summarize(rows: list[dict]) -> dict:
    by = {"stage": defaultdict(float), "model": defaultdict(float), "agent": defaultdict(float)}
    tokens = defaultdict(int)
    total = 0.0
    times = []
    for r in rows:
        c = float(r.get("cost_usd") or 0)
        total += c
        by["stage"][r.get("stage") or "?"] += c
        by["model"][r.get("model") or "?"] += c
        by["agent"][(r.get("agent") or "?").split(":")[0]] += c
        for k in ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens", "web_searches"):
            tokens[k] += int(float(r.get(k) or 0))
        try:
            times.append(datetime.fromisoformat(r["ts"]))
        except (KeyError, ValueError):
            pass
    sessions = len({r.get("session_id") for r in rows})
    return {"total": total, "by": by, "tokens": dict(tokens), "sessions": sessions,
            "first": min(times).isoformat() if times else None, "last": max(times).isoformat() if times else None}


def render(s: dict, md: bool) -> str:
    def table(title, d):
        lines = [f"\n{title}:"] if not md else [f"\n**{title}**\n", "| | $ | доля |", "|---|---|---|"]
        for k, v in sorted(d.items(), key=lambda x: -x[1]):
            share = (v / s["total"] * 100) if s["total"] else 0
            lines.append(f"| {k} | {v:.4f} | {share:.0f}% |" if md else f"  {k:28} ${v:.4f}  {share:4.0f}%")
        return "\n".join(lines)

    t = s["tokens"]
    def n(k):
        return f"{t.get(k, 0):,}".replace(",", " ")

    out = [f"Стоимость задачи: ${s['total']:.4f} (оценка по прейскуранту Claude API), сессий: {s['sessions']}",
           f"Токены: вход {n('input_tokens')}, запись кэша {n('cache_write_tokens')}, "
           f"чтение кэша {n('cache_read_tokens')}, выход {n('output_tokens')}; веб-поисков {t.get('web_searches', 0)}"]
    if s["first"]:
        out.append(f"Период записей: {s['first']} — {s['last']}")
    out.append(table("По этапам", s["by"]["stage"]))
    out.append(table("По моделям", s["by"]["model"]))
    out.append(table("По агентам (main — оркестратор)", s["by"]["agent"]))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=None)
    ap.add_argument("--md", action="store_true", help="вывод таблицами Markdown")
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    rows = core.read_ledger(proj)
    if not rows:
        print("Журнал стоимости пуст: он заполняется хуком Stop в Claude Code (state/cost-ledger.csv).")
        return 0
    print(render(summarize(rows), args.md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
