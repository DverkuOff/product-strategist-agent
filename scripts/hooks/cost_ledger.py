#!/usr/bin/env python3
"""Stop / SubagentStop: записать стоимость в state/cost-ledger.csv активной задачи.

Токены берутся из транскрипта Claude Code (JSONL; usage у сообщений ассистента, дубли по message.id
отбрасываются), стоимость — по прейскуранту Claude API (core.PRICES). На подписке это оценка,
а не счёт. Запись дельтой: строка = прирост токенов с прошлой записи по (сессия, агент, модель)
с этапом задачи на момент записи — так видно, сколько стоил каждый этап.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from _hook import read_input, root

import core  # noqa: E402

KEYS = ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens", "web_searches")


def totals_from_transcript(path: Path, main_only: bool) -> dict[str, dict]:
    """model → суммы токенов и стоимость."""
    seen = set()
    acc: dict[str, dict] = defaultdict(lambda: {k: 0 for k in KEYS} | {"cost_usd": 0.0})
    try:
        fh = path.open(encoding="utf-8")
    except OSError:
        return {}
    with fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant" or (main_only and d.get("isSidechain")):
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            model = m.get("model") or ""
            mid = m.get("id") or d.get("requestId") or d.get("uuid")
            if not u or not model or model.startswith("<") or mid in seen:
                continue
            seen.add(mid)
            a = acc[model]
            a["input_tokens"] += u.get("input_tokens", 0) or 0
            a["output_tokens"] += u.get("output_tokens", 0) or 0
            a["cache_read_tokens"] += u.get("cache_read_input_tokens", 0) or 0
            a["cache_write_tokens"] += u.get("cache_creation_input_tokens", 0) or 0
            a["web_searches"] += ((u.get("server_tool_use") or {}).get("web_search_requests", 0)) or 0
            a["cost_usd"] += core.usage_cost(model, u)
    return dict(acc)


def record(proj: Path, session: str, agent: str, totals: dict[str, dict]) -> int:
    f = proj / "state" / "cost-ledger.csv"
    rows = core.read_ledger(proj)
    prev: dict[str, dict] = defaultdict(lambda: {k: 0.0 for k in (*KEYS, "cost_usd")})
    for r in rows:
        if r.get("session_id") == session and r.get("agent") == agent:
            for k in (*KEYS, "cost_usd"):
                try:
                    prev[r["model"]][k] += float(r.get(k) or 0)
                except ValueError:
                    pass
    stage = core.load_task(proj).get("stage", "")
    new = []
    for model, t in totals.items():
        delta = {k: t[k] - prev[model][k] for k in (*KEYS, "cost_usd")}
        if all(delta[k] <= 0 for k in KEYS):
            continue
        new.append({
            "ts": core.now_iso(), "session_id": session, "agent": agent, "model": model, "stage": stage,
            **{k: int(delta[k]) for k in KEYS}, "cost_usd": f"{max(delta['cost_usd'], 0):.6f}",
        })
    if not new:
        return 0
    write_header = not f.exists() or f.stat().st_size == 0
    with f.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=core.LEDGER_FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(new)
    return len(new)


def main() -> int:
    inp = read_input()
    r = root(inp)
    proj = core.project_path(None, r)
    if not proj:
        return 0
    session = inp.get("session_id", "unknown")
    if inp.get("hook_event_name") == "SubagentStop":
        tp = inp.get("agent_transcript_path")
        agent = f"{inp.get('agent_type', 'subagent')}:{inp.get('agent_id', '')}"
        main_only = False
    else:
        tp = inp.get("transcript_path")
        agent = "main"
        main_only = True
    if not tp:
        return 0
    totals = totals_from_transcript(Path(tp).expanduser(), main_only)
    record(proj, session, agent, totals)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — учёт стоимости не должен мешать работе
        print(f"cost_ledger: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
