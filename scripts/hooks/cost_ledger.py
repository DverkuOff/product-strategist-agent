#!/usr/bin/env python3
"""Stop / SubagentStop / SessionEnd / SessionStart: записать стоимость в state/cost-ledger.csv.

Токены берутся из транскрипта Claude Code (JSONL, usage у сообщений ассистента), стоимость — по прейскуранту
Claude API для точного id модели (core.MODEL_PRICES; неизвестная модель — пустая цена и пометка в отчёте,
а не $0). На подписке это оценка, а не счёт.

Без двойного счёта: каждый message.id учитывается один раз на весь репозиторий (projects/.cost-seen.json)
и относится к задаче, активной в момент первого учёта. Поэтому смена задачи в той же сессии (`project.py use`)
и сессия-копия (`--fork-session`) не пересчитывают уже учтённое. Строка журнала — прирост по модели с этапом
задачи на момент записи.

Транскрипт пишется асинхронно: в момент Stop последний ответ может быть ещё не записан. Поэтому хук немного
ждёт, пока файл перестанет расти, а пути транскриптов запоминаются (projects/.cost-transcripts.json) и
недостающее досчитывается на SessionEnd и следующем SessionStart.
"""
from __future__ import annotations

import contextlib
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from _hook import read_input, root

import core  # noqa: E402

KEYS = ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens", "web_searches")
SEEN = ".cost-seen.json"
TRANSCRIPTS = ".cost-transcripts.json"


def messages_from_transcript(path: Path, main_only: bool) -> list[dict]:
    """Ответы ассистента с usage, по одному на message.id."""
    seen, out, idx = set(), [], {}
    try:
        fh = path.open(encoding="utf-8")
    except OSError:
        return out
    with fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant" or (main_only and d.get("isSidechain")):
                continue
            m = d.get("message") or {}
            u, model = m.get("usage"), m.get("model") or ""
            mid = m.get("id") or d.get("requestId") or d.get("uuid")
            # WebSearch в Claude Code — клиентский инструмент: в usage ответа поиск не виден, считаем вызовы
            n_ws = sum(1 for b in (m.get("content") or []) if isinstance(b, dict)
                       and b.get("type") == "tool_use" and b.get("name") == "WebSearch")
            if n_ws and mid in idx:
                _add_ws(idx[mid], n_ws)
            if not u or not model or model.startswith("<") or not mid or mid in seen:
                continue
            seen.add(mid)
            e = {"id": mid, "model": model, "usage": dict(u), "ws_tools": 0}
            if n_ws:
                _add_ws(e, n_ws)
            out.append(e)
            idx[mid] = e
    return out


def _add_ws(e: dict, n: int) -> None:
    """Число поисков ответа = max(серверный счётчик, вызовы WebSearch): без двойного счёта."""
    e["ws_tools"] += n
    stu = dict(e["usage"].get("server_tool_use") or {})
    stu["web_search_requests"] = max(stu.get("web_search_requests", 0) or 0, e["ws_tools"])
    e["usage"]["server_tool_use"] = stu


@contextlib.contextmanager
def locked(r: Path):
    pdir = core.projects_dir(r)
    pdir.mkdir(exist_ok=True)
    fh = open(pdir / ".cost.lock", "a+")
    try:
        try:
            import fcntl

            fcntl.flock(fh, fcntl.LOCK_EX)
        except ImportError:  # Windows: без блокировки
            pass
        yield
    finally:
        fh.close()


def record(r: Path, proj: Path, session: str, agent: str, msgs: list[dict]) -> int:
    """Учесть ещё не учтённые сообщения в журнале задачи proj. Возвращает число новых строк."""
    seen_f = core.projects_dir(r) / SEEN
    seen = core.read_json(seen_f, {}) or {}
    fresh = [m for m in msgs if m["id"] not in seen]
    if not fresh:
        return 0
    acc: dict[str, dict] = defaultdict(lambda: {k: 0 for k in KEYS} | {"cost": 0.0, "unknown": False})
    for m in fresh:
        u, a = m["usage"], acc[m["model"]]
        a["input_tokens"] += u.get("input_tokens", 0) or 0
        a["output_tokens"] += u.get("output_tokens", 0) or 0
        a["cache_read_tokens"] += u.get("cache_read_input_tokens", 0) or 0
        a["cache_write_tokens"] += u.get("cache_creation_input_tokens", 0) or 0
        a["web_searches"] += ((u.get("server_tool_use") or {}).get("web_search_requests", 0)) or 0
        c = core.usage_cost(m["model"], u)
        if c is None:
            a["unknown"] = True
        else:
            a["cost"] += c
    stage = core.load_task(proj).get("stage", "")
    rows = [{"ts": core.now_iso(), "session_id": session, "agent": agent, "model": model, "stage": stage,
             **{k: int(a[k]) for k in KEYS}, "cost_usd": "" if a["unknown"] else f"{a['cost']:.6f}"}
            for model, a in acc.items()]
    f = proj / "state" / "cost-ledger.csv"
    write_header = not f.exists() or f.stat().st_size == 0
    with f.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=core.LEDGER_FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(rows)
    for m in fresh:
        seen[m["id"]] = proj.name
    core.write_json(seen_f, seen)
    return len(rows)


def wait_for_flush(path: Path, max_wait: float = 2.5, step: float = 0.25) -> None:
    """Подождать, пока транскрипт перестанет расти (дозапись последнего ответа)."""
    last, stable, waited = -1, 0, 0.0
    while waited < max_wait:
        try:
            size = path.stat().st_size
        except OSError:
            return
        stable = stable + 1 if size == last else 0
        if stable >= 2:
            return
        last = size
        time.sleep(step)
        waited += step


def reconcile(r: Path) -> int:
    """Досчитать запомненные транскрипты: только неучтённые сообщения, в задачу, активную при их записи."""
    data = core.read_json(core.projects_dir(r) / TRANSCRIPTS, {}) or {}
    n = 0
    for tp, e in data.items():
        proj = core.project_path(e.get("slug"), r)
        p = Path(tp).expanduser()
        if proj and p.exists():
            n += record(r, proj, e["session"], e["agent"], messages_from_transcript(p, e.get("main_only", True)))
    return n


def main() -> int:
    inp = read_input()
    r = root(inp)
    event = inp.get("hook_event_name", "Stop")
    with locked(r):
        if event in {"SessionEnd", "SessionStart"}:
            reconcile(r)
            return 0
    proj = core.project_path(None, r)
    if not proj:
        return 0
    session = inp.get("session_id", "unknown")
    if event == "SubagentStop":
        tp = inp.get("agent_transcript_path")
        agent = f"{inp.get('agent_type', 'subagent')}:{inp.get('agent_id', '')}"
        main_only = False
    else:
        tp = inp.get("transcript_path")
        agent, main_only = "main", True
    if not tp:
        return 0
    path = Path(tp).expanduser()
    if not inp.get("_no_wait"):
        wait_for_flush(path)
    with locked(r):
        tf = core.projects_dir(r) / TRANSCRIPTS
        data = core.read_json(tf, {}) or {}
        data[str(path)] = {"session": session, "agent": agent, "main_only": main_only, "slug": proj.name}
        core.write_json(tf, data)
        record(r, proj, session, agent, messages_from_transcript(path, main_only))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — учёт стоимости не должен мешать работе
        print(f"cost_ledger: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
