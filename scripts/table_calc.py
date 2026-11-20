#!/usr/bin/env python3
"""Расчёт по таблице РП из снимка — без чтения текста снимка в контекст агента (карантин).

Таблицу РП (csv, tsv, xlsx через markitdown) сохраняет fetch_source.py в materials/. Читать снимок агенту нельзя
(хук), а считать по таблице нужно. Этот скрипт читает снимок сам и печатает только числа: число строк, столбцы с
номерами и типом, сумму, среднее, минимум, максимум, при группировке — по группам. Имена столбцов и значения групп
обрезаются до 40 знаков, из них убираются служебные символы, а похожее на инструкцию агенту скрывается.

  python3 scripts/table_calc.py M-05 --describe                   # строки, столбцы, сводка по числовым
  python3 scripts/table_calc.py M-05 --sum 3 --mean 4              # по номерам столбцов (с 1) или точным именам
  python3 scripts/table_calc.py M-05 --sum 3 --group-by 2          # по группам (не больше 50 групп)
  python3 scripts/table_calc.py M-05 --sum 3 --where 2=Москва      # фильтр по точному значению
  python3 scripts/table_calc.py M-05 --table 2 --describe          # вторая таблица снимка
Результат — гипотеза или прогноз агента с basis на факт о снимке, а не факт: число не из источника, а из расчёта.
Код выхода: 0 — посчитано; 2 — нет снимка, таблицы или столбца; 3 — снимок изменён после сохранения.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import injection  # noqa: E402

MAX_GROUPS = 50
NAME_LEN = 40


def safe_name(text: str) -> str:
    """Имя столбца или группы для вывода: без разметки и служебных символов, коротко; инструкции — скрыты."""
    t = re.sub(r"[^\w\s%.,()/+\-№]", " ", str(text), flags=re.U)
    t = re.sub(r"\s+", " ", t).strip()
    if injection.scan(str(text)) or re.search(r"(?i)\b(ai|ии|агент|assistant|инструкц|ignore|игнорир)", t):
        return "[скрыто: похоже на инструкцию]"
    return (t[:NAME_LEN] + "…") if len(t) > NAME_LEN else (t or "—")


def tables_in(body: str) -> list[list[list[str]]]:
    """Таблицы снимка: CSV/TSV в блоке ``` и таблицы Markdown (markitdown для xlsx/docx)."""
    out = []
    for block in re.findall(r"```[^\n]*\n(.*?)```", body, re.S):
        sample = block[:2000]
        delim = "\t" if sample.count("\t") > sample.count(",") and sample.count("\t") > sample.count(";") else \
            (";" if sample.count(";") > sample.count(",") else ",")
        rows = [r for r in csv.reader(io.StringIO(block.strip()), delimiter=delim) if any(c.strip() for c in r)]
        if len(rows) >= 2:
            out.append(rows)
    cur: list[list[str]] = []
    for line in body.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                cur.append(cells)
        elif cur:
            if len(cur) >= 2:
                out.append(cur)
            cur = []
    return out


def to_number(cell: str) -> float | None:
    s = str(cell).strip().replace(" ", "").replace(" ", "").replace("%", "").replace("₽", "").replace("$", "")
    if re.fullmatch(r"-?\d+(,\d+)?", s):
        s = s.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def col_index(head: list[str], ref: str) -> int:
    if re.fullmatch(r"\d+", ref) and 1 <= int(ref) <= len(head):
        return int(ref) - 1
    for i, h in enumerate(head):
        if h.strip().casefold() == ref.strip().casefold():
            return i
    raise SystemExit(f"нет столбца «{safe_name(ref)}»: укажи номер (с 1) из --describe")


def fmt(x: float) -> str:
    return f"{x:,.4f}".rstrip("0").rstrip(".").replace(",", " ") if x == x else "—"


def summary(vals: list[float]) -> str:
    if not vals:
        return "чисел нет"
    return (f"n={len(vals)}, сумма {fmt(sum(vals))}, среднее {fmt(statistics.mean(vals))}, "
            f"медиана {fmt(statistics.median(vals))}, мин {fmt(min(vals))}, макс {fmt(max(vals))}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("material", help="ID снимка, например M-05")
    ap.add_argument("--project", default=None)
    ap.add_argument("--table", type=int, default=1, help="номер таблицы в снимке (с 1)")
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--sum", action="append", default=[])
    ap.add_argument("--mean", action="append", default=[])
    ap.add_argument("--group-by", default=None)
    ap.add_argument("--where", action="append", default=[], help="СТОЛБЕЦ=значение (точное совпадение)")
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    mats = core.list_materials(proj)
    mat = mats.get(args.material)
    if not mat or not re.fullmatch(r"M-\d+", args.material):
        print(f"Нет снимка {args.material} в materials/", file=sys.stderr)
        return 2
    changed, _ = core.manifest_check(proj)
    if args.material in changed:
        print(f"{args.material}: {changed[args.material]} — считать по нему нельзя", file=sys.stderr)
        return 3
    tabs = tables_in(mat["body"])
    if not tabs or not 1 <= args.table <= len(tabs):
        print(f"В {args.material} таблиц: {len(tabs)} — таблицы №{args.table} нет", file=sys.stderr)
        return 2
    head, rows = tabs[args.table - 1][0], tabs[args.table - 1][1:]
    try:
        for w in args.where:
            ref, _, val = w.partition("=")
            ci = col_index(head, ref)
            rows = [r for r in rows if ci < len(r) and r[ci].strip().casefold() == val.strip().casefold()]
        print(f"{args.material}, таблица {args.table} из {len(tabs)}: строк {len(rows)}, столбцов {len(head)}"
              + (f" (фильтр: {len(args.where)})" if args.where else ""))
        if args.describe or not (args.sum or args.mean):
            for i, h in enumerate(head):
                vals = [v for r in rows if i < len(r) for v in [to_number(r[i])] if v is not None]
                kind = "числа" if vals and len(vals) >= 0.6 * max(1, len(rows)) else "текст"
                print(f"  {i + 1}. {safe_name(h)} — {kind}" + (f": {summary(vals)}" if kind == "числа" else ""))
        targets = [(col_index(head, c), "сумма") for c in args.sum] + [(col_index(head, c), "среднее") for c in args.mean]
        gi = col_index(head, args.group_by) if args.group_by else None
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    for ci, what in targets:
        vals = [v for r in rows if ci < len(r) for v in [to_number(r[ci])] if v is not None]
        if gi is None:
            val = sum(vals) if what == "сумма" else (statistics.mean(vals) if vals else float("nan"))
            print(f"{what} столбца {ci + 1}: {fmt(val)} (чисел {len(vals)} из {len(rows)} строк)")
            continue
        groups: dict[str, list[float]] = {}
        for r in rows:
            if ci < len(r) and gi < len(r):
                v = to_number(r[ci])
                if v is not None:
                    groups.setdefault(r[gi].strip(), []).append(v)
        print(f"{what} столбца {ci + 1} по столбцу {gi + 1} (групп {len(groups)}"
              + (f", показаны первые {MAX_GROUPS}" if len(groups) > MAX_GROUPS else "") + "):")
        for k in sorted(groups)[:MAX_GROUPS]:
            v = groups[k]
            print(f"  {safe_name(k)}: {fmt(sum(v) if what == 'сумма' else statistics.mean(v))} (n={len(v)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
