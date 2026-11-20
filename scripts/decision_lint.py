#!/usr/bin/env python3
"""Проверка вариантов и решений без LLM.

out/options.md:
  O1 меньше трёх вариантов;              O2 нет варианта «оставить как есть»;
  O3 у «оставить как есть» нет блока «Цена бездействия» (базовая линия: что будет без изменений
     и чего это стоит) — идея из spec-kit assess (Cost of Inaction);
  O4 у варианта нет «что должно быть правдой»;  O5 у варианта нет сильных возражений.
state/decisions.md (для действующих решений):
  D1 нет вердикта «делать / нужна ясность / стоп» с причиной после «—»;
  D2 нет поля «Что заставит пересмотреть» (kill-критерии; идея pm-brain «what would reopen them»);
     на этапах validation и done заглушка «будут в плане проверки» уже не годится;
  O6/O7 (предупреждения) нет раздела «Возражения критика» от субагента critic или сильное возражение без ответа автора;
  A0 этап options пройден (task.json), а out/options.md нет или в state/decisions.md нет ни одного решения;
  D3 вердикт «делать» без проработанного варианта (вариант из options.md с условиями «должно быть правдой»,
     возражениями и метками утверждений) и без оснований → понижается до «нужна ясность» (--fix пишет в файл).

  python3 scripts/decision_lint.py [--project <slug|путь>] [--fix]
Код выхода: 0 — чисто; 1 — есть замечания или понижения.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import revisit  # noqa: E402

VARIANT = re.compile(r"^##+\s*Вариант\s+([A-Za-zА-Яа-я0-9]+)[.:)]?\s*(.*)$", re.M)
STATUS_QUO = re.compile(r"оставить как есть|ничего не делать|статус-кво", re.I)
MARK = re.compile(r"\[(факт|гипотеза|прогноз|синтетика)[^\]\n]*?C-\d+\]", re.I)
VERDICTS = ("делать", "нужна ясность", "стоп")
REJECTED = re.compile(r"\bотброшен|\bотвергнут", re.I)
# Заглушка — пустое поле, многоточие или TODO вместо текста, строка из шаблона, «будут в плане проверки».
# Многоточие ВНУТРИ текста («сравнение до… после») — не заглушка.
PLACEHOLDER = re.compile(r"будут\s+в\s+плане|(определим|уточним|решим|заполним|допишем)\s+позже|\bTBD\b|\bTODO\b|"
                         r"^\s*(\.\.\.|…|-|—|\?)?\s*$|при каком результате проверки или каком новом факте", re.I)
DASH = re.compile(r"\s[-–]{1,2}\s")  # «делать - причина», «делать – причина», «делать -- причина» = длинное тире


def parse_variants(md: str) -> dict[str, dict]:
    """Вариант → {title, body}. Раздел варианта заканчивается на следующем заголовке того же или более высокого уровня."""
    out = {}
    for m in VARIANT.finditer(md):
        level = len(re.match(r"#+", m.group(0)).group(0))
        nxt = re.search(rf"^#{{1,{level}}}\s", md[m.end():], re.M)
        body = md[m.end(): m.end() + nxt.start()] if nxt else md[m.end():]
        out[m.group(1).upper()] = {"title": m.group(2).strip(), "body": body}
    return out


def variant_worked_out(v: dict) -> list[str]:
    """Чего не хватает варианту, чтобы считаться проработанным."""
    miss = []
    if not re.search(r"должно быть правдой", v["body"], re.I):
        miss.append("нет «что должно быть правдой»")
    if not re.search(r"возражени|провал\w*,? потому что", v["body"], re.I):
        miss.append("нет сильных возражений")
    if not MARK.search(v["body"]):
        miss.append("нет опоры на утверждения (меток [факт C-…] и т. п.)")
    return miss


def check_options(proj: Path) -> list[str]:
    f = proj / "out" / "options.md"
    if not f.exists():
        return []
    md = f.read_text(encoding="utf-8")
    allv = parse_variants(md)
    # «Закрыть направление», рассмотренное и отброшенное, вариантом для выбора не считается
    vs = {k: v for k, v in allv.items() if not REJECTED.search(v["title"] + " " + v["body"][:200])}
    errs = []
    if len(vs) < 3:
        errs.append(f"O1 options.md: вариантов {len(vs)}, нужно не меньше трёх содержательно разных")
    sq = [k for k, v in vs.items() if STATUS_QUO.search(v["title"])]
    if not sq:
        errs.append("O2 options.md: нет варианта «Оставить как есть»")
    for k in sq:
        b = vs[k]["body"]
        # блок = строка с «Цена бездействия» и продолжение до следующего пункта списка или заголовка
        m = re.search(r"цена бездействия[^\n]*(?:\n(?!\s*[-*]\s|\s*#)[^\n]*)*", b, re.I)
        if not m:
            errs.append(f"O3 вариант {k} («оставить как есть»): нет блока «Цена бездействия» — базовая линия, что будет без изменений и чего это стоит")
        elif not MARK.search(m.group(0)):
            errs.append(f"O3 вариант {k}: «Цена бездействия» без опоры — нужна метка [факт/прогноз C-…]")
    for k, v in vs.items():
        if not re.search(r"должно быть правдой", v["body"], re.I):
            errs.append(f"O4 вариант {k}: нет «что должно быть правдой»")
        if not re.search(r"возражени|провал\w*,? потому что", v["body"], re.I):
            errs.append(f"O5 вариант {k}: нет сильных возражений")
    return errs


def option_warnings(proj: Path) -> list[str]:
    """Не блокирующие замечания: критика вариантов (субагент critic) и ответы автора на сильные возражения."""
    f = proj / "out" / "options.md"
    if not f.exists():
        return []
    md = f.read_text(encoding="utf-8")
    m = re.search(r"^##\s+Возражения критика.*?(?=^##\s(?!#)|\Z)", md, re.M | re.S)
    if not m:
        return ["O6 options.md: нет раздела «Возражения критика» — вызови субагента critic (скилл options, шаг 5)"]
    warns = []
    for row in m.group(0).splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")] if row.strip().startswith("|") else []
        if len(cells) >= 6 and cells[3].lower() == "высокая" and not cells[5]:
            warns.append(f"O7 сильное возражение к варианту {cells[0]} без ответа автора: «{cells[1][:70]}»")
    return warns


def field(d: dict, *names: str) -> str:
    for n in names:
        for k, v in d["fields"].items():
            if k.startswith(n):
                return v
    return ""


def check_decisions(proj: Path) -> tuple[list[str], list[tuple[str, str]]]:
    """(ошибки, понижения [(D-id, причина)])."""
    f = proj / "state" / "decisions.md"
    if not f.exists():
        return [], []
    stage = core.load_task(proj).get("stage", "")
    decisions = revisit.parse_decisions(f.read_text(encoding="utf-8"))
    opt = proj / "out" / "options.md"
    variants = parse_variants(opt.read_text(encoding="utf-8")) if opt.exists() else {}
    errs, downs = [], []
    for d in decisions:
        if not d["status"].startswith(revisit.ACTIVE):
            continue
        did = d["id"]
        verdict = field(d, "вердикт")
        m = DASH.search(verdict or "")
        if m and ("—" not in verdict or m.start() < verdict.index("—")):
            verdict = verdict[: m.start()] + " — " + verdict[m.end():]
        head = verdict.split("—")[0].strip().lower() if verdict else ""
        if head not in VERDICTS:
            errs.append(f"D1 {did}: вердикт должен быть «делать», «нужна ясность» или «стоп», затем тире « — » и причина "
                        f"(сейчас: «{verdict or 'нет'}»)")
        elif "—" not in verdict or not verdict.split("—", 1)[1].strip():
            errs.append(f"D1 {did}: у вердикта нет причины после тире («делать — потому что …»)")
        reopen = field(d, "что заставит пересмотреть", "kill")
        if not reopen:
            errs.append(f"D2 {did}: нет поля «Что заставит пересмотреть» (kill-критерии)")
        elif stage in {"validation", "done"} and PLACEHOLDER.search(reopen):
            m = PLACEHOLDER.search(reopen)
            errs.append(f"D2 {did}: «Что заставит пересмотреть» — заглушка («{m.group(0).strip() or 'пусто'}»); на этапе {stage} "
                        "нужны конкретные kill-критерии из плана проверки")
        if head == "делать":
            why = []
            vid = re.search(r"\b([A-Za-zА-Яа-я0-9])\b", field(d, "вариант"))
            v = variants.get(vid.group(1).upper()) if vid else None
            if not v:
                why.append("вариант не указан или его нет в out/options.md")
            else:
                why += [f"вариант {vid.group(1).upper()}: {m}" for m in variant_worked_out(v)]
            if not d["basis"]:
                why.append("нет оснований (ID утверждений)")
            if why:
                downs.append((did, "; ".join(why)))
    return errs, downs


def apply_downgrades(proj: Path, downs: list[tuple[str, str]]) -> int:
    if not downs:
        return 0
    f = proj / "state" / "decisions.md"
    text = f.read_text(encoding="utf-8")
    for did, why in downs:
        sec = re.search(rf"^##\s+{re.escape(did)}\b.*?(?=^##\s|\Z)", text, re.M | re.S)
        if not sec:
            continue
        new = re.sub(r"^(\s*[-*]\s*Вердикт:\s*)(делать)(.*)$",
                     lambda m: f"{m.group(1)}нужна ясность — понижено проверкой: {why} (было: делать{m.group(3)})",
                     sec.group(0), count=1, flags=re.M | re.I)
        text = text[: sec.start()] + new + text[sec.end():]
    f.write_text(text, encoding="utf-8")
    core.append_journal(proj, "decision_lint: вердикт «делать» понижен до «нужна ясность»: " + ", ".join(d for d, _ in downs))
    return len(downs)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("--project", default=None)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    errs = core.missing_artifacts(proj, only={"options"}) + check_options(proj)
    derrs, downs = check_decisions(proj)
    errs += derrs
    if args.fix:
        apply_downgrades(proj, downs)
    for e in errs:
        print(f"  ✗ {e}")
    for w in option_warnings(proj):
        print(f"  ! {w}")
    for did, why in downs:
        print(f"  ↓ {did}: «делать» → «нужна ясность»{'' if args.fix else ' (--fix)'}: {why}")
    if not errs and not downs:
        print("Варианты и решения: ✓ структура полная, вердикты обоснованы")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
