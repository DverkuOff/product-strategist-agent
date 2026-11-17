#!/usr/bin/env python3
"""Оценка стоимости и времени исследования до его начала — для плана на утверждение РП.

  python3 scripts/estimate.py --sources 8 --searches 6            # показать оценку
  python3 scripts/estimate.py --sources 8 --searches 6 --save     # записать в state/research-plan.json (ждёт утверждения)
  python3 scripts/project.py approve-plan                          # после «начать» от РП

Модель затрат (прейскурант core.PRICES, допущения — в ASSUMPTIONS ниже, их можно уточнять по факту):
  - на каждый источник оркестратор (Sonnet) делает ~3 хода: найти, сохранить снимок, поручить чтение и добавить
    утверждения; каждый ход перечитывает контекст из кэша и дописывает немного нового;
  - чтение снимка — субагент source-reader на Haiku: снимок + системный промпт на входе, JSON утверждений на выходе;
  - поисковый запрос — $0,01 за поиск плюс ход оркестратора;
  - постоянная часть этапа: план, сопоставление источников, out/research.md.
Если в задачах есть завершённые исследования с оценкой и фактом (state/research-plan.json + cost-ledger.csv),
оценка домножается на средний коэффициент «факт / оценка» — калибровка по своему опыту.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ASSUMPTIONS = {
    "orch_turns_per_source": 3,
    "orch_turns_per_search": 1,
    "orch_turns_fixed": 8,            # план, сопоставление, research.md, ворота качества
    "orch_context_tokens": 45_000,    # перечитывается из кэша каждый ход
    "orch_new_input_tokens": 1_500,   # запись кэша за ход (TTL 1 час → 2× цены входа)
    "orch_output_tokens": 600,        # за ход
    "fixed_output_tokens": 5_000,     # текст research.md и плана
    "reader_system_tokens": 3_000,
    "snapshot_tokens_default": 6_000, # если снимков ещё нет; иначе — средний размер снимков задачи
    "chars_per_token": 3.0,           # русский текст
    "reader_output_tokens": 1_500,
    "seconds_per_source": 70,
    "seconds_per_search": 20,
    "seconds_fixed": 240,
    "low_factor": 0.6,
    "high_factor": 1.8,
}


def avg_snapshot_tokens(proj: Path | None) -> int:
    a = ASSUMPTIONS
    if not proj:
        return a["snapshot_tokens_default"]
    mats = [m for m in core.list_materials(proj).values() if m["body"].strip()]
    if not mats:
        return a["snapshot_tokens_default"]
    return int(sum(len(m["body"]) for m in mats) / len(mats) / a["chars_per_token"])


def turn_cost(model: str) -> float:
    a = ASSUMPTIONS
    p = core.PRICES[model]
    return (a["orch_context_tokens"] * p["cache_read"] + a["orch_new_input_tokens"] * p["input"] * 2.0
            + a["orch_output_tokens"] * p["output"]) / 1_000_000


def calibration(root: Path | None = None) -> tuple[float, int]:
    """Средний коэффициент факт/оценка по завершённым исследованиям во всех задачах."""
    ratios = []
    pdir = core.projects_dir(root)
    for d in pdir.iterdir() if pdir.is_dir() else []:
        if not (d / "state").is_dir():
            continue
        plan = core.read_json(d / "state" / "research-plan.json", None)
        stage = core.load_task(d).get("stage", "")
        if not plan or stage in ("intake", "research") or not plan.get("estimate", {}).get("usd"):
            continue
        fact = sum(float(r.get("cost_usd") or 0) for r in core.read_ledger(d) if r.get("stage") == "research")
        if fact > 0:
            ratios.append(fact / plan["estimate"]["usd"])
    return (sum(ratios) / len(ratios), len(ratios)) if ratios else (1.0, 0)


def estimate(sources: int, searches: int, proj: Path | None = None, calibrate: bool = True) -> dict:
    a = ASSUMPTIONS
    snap = avg_snapshot_tokens(proj)
    t = turn_cost("sonnet")
    orch = t * (a["orch_turns_per_source"] * sources + a["orch_turns_per_search"] * searches + a["orch_turns_fixed"])
    orch += a["fixed_output_tokens"] * core.PRICES["sonnet"]["output"] / 1_000_000
    h = core.PRICES["haiku"]
    reader = sources * ((snap + a["reader_system_tokens"]) * h["input"] + a["reader_output_tokens"] * h["output"]) / 1_000_000
    search = searches * core.WEB_SEARCH_USD
    k, n = calibration(proj.parent.parent if proj else None) if calibrate else (1.0, 0)
    usd = (orch + reader + search) * k
    minutes = (a["seconds_per_source"] * sources + a["seconds_per_search"] * searches + a["seconds_fixed"]) / 60
    return {
        "sources": sources, "searches": searches, "snapshot_tokens": snap,
        "parts_usd": {"оркестратор (Sonnet)": round(orch * k, 4), "чтение источников (Haiku)": round(reader * k, 4),
                      "веб-поиск": round(search * k, 4)},
        "usd": round(usd, 4), "usd_low": round(usd * a["low_factor"], 4), "usd_high": round(usd * a["high_factor"], 4),
        "minutes": round(minutes, 1), "calibration": {"factor": round(k, 2), "from_tasks": n},
    }


def render(e: dict) -> str:
    lines = [f"Оценка исследования: {e['sources']} источников, {e['searches']} поисковых запросов "
             f"(средний снимок ≈ {e['snapshot_tokens']} токенов)",
             f"  стоимость ≈ ${e['usd']:.2f} (диапазон ${e['usd_low']:.2f}–${e['usd_high']:.2f}), оценка по прейскуранту API",
             f"  время ≈ {e['minutes']:.0f} мин работы агента"]
    for k, v in e["parts_usd"].items():
        lines.append(f"    {k}: ${v:.3f}")
    c = e["calibration"]
    lines.append(f"  калибровка по прошлым задачам: ×{c['factor']} ({c['from_tasks']} задач)" if c["from_tasks"]
                 else "  калибровки пока нет: оценка по допущениям (scripts/estimate.py, ASSUMPTIONS)")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--sources", type=int, required=True, help="сколько источников планируем прочитать")
    ap.add_argument("--searches", type=int, default=0, help="сколько поисковых запросов")
    ap.add_argument("--save", action="store_true", help="записать в state/research-plan.json (статус: ждёт утверждения)")
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    e = estimate(args.sources, args.searches, proj)
    print(render(e))
    if args.save:
        if not proj:
            print("Нет активной задачи", file=sys.stderr)
            return 2
        plan = {"created_at": core.now_iso(), "estimate": e, "approved": False, "approved_at": None,
                "note": "Вопросы и список источников — в out/research-plan.md"}
        core.write_json(proj / "state" / "research-plan.json", plan)
        core.append_journal(proj, f"План исследования: оценка ${e['usd']:.2f} (${e['usd_low']:.2f}–${e['usd_high']:.2f}), "
                                  f"≈{e['minutes']:.0f} мин; ждёт утверждения РП")
        core.log_research(proj, "plan", f"{e['sources']} источников, {e['searches']} запросов",
                          f"оценка ${e['usd']:.2f}, ≈{e['minutes']:.0f} мин, ждёт утверждения")
        print("Записано в state/research-plan.json. Покажи РП out/research-plan.md и оценку, жди «начать» или правок; "
              "после «начать» — python3 scripts/project.py approve-plan")
    return 0


def plan_vs_fact(proj: Path) -> dict | None:
    """Оценка из плана против факта этапа research (для cost_report и сводки)."""
    plan = core.read_json(proj / "state" / "research-plan.json", None)
    if not plan:
        return None
    rows = [r for r in core.read_ledger(proj) if r.get("stage") == "research"]
    fact = sum(float(r.get("cost_usd") or 0) for r in rows)
    since = plan.get("approved_at") or plan.get("created_at") or ""
    mats = [m for m in core.list_materials(proj).values() if str(m["meta"].get("retrieved_at", "")) >= since]
    return {"approved": core.plan_approved(proj), "estimate": plan["estimate"], "fact_usd": round(fact, 4),
            "fact_sources": len(mats)}


if __name__ == "__main__":
    sys.exit(main())
