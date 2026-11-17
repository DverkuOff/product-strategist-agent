#!/usr/bin/env python3
"""«Сверка обещаний»: коммуникация не обещает того, чего нет в продукте. Без LLM.

Входы задачи:
  state/product-properties.json — реестр свойств продукта: id P-xx, statement, status fact|hypothesis, claims [C-xx]
  out/comms-strategy.md        — таблица «Ключевые обещания»: | ID | Обещание | Опора | Тип |
  out/validation-plan.md        — сюда должны попасть обещания с типом «тест сообщения»
  state/claims.jsonl            — статус свойства-факта сверяется со статусами его claims

Обещание не проходит, если:
  E1 нет опоры (ни одного P-xx);                 E2 опора на несуществующее свойство;
  E3 опора на гипотезу, а тип не «тест сообщения» (перенеси в план проверки);
  E4 «тест сообщения» не внесён в план проверки;
  E5 рискованная формулировка (ст. 5 38-ФЗ: «самый», «лучший», «№1», «гарантированно», «100%»,
     «полная защита», …) без подтверждающего свойства-факта с той же формулировкой;
  E6 в обещании есть число, которого нет в опорных свойствах;
  E7 у обещания и опорного свойства меньше двух общих значимых слов (ссылка на «чужое» свойство);
  E8 рискованная формулировка в слогане, ключевом сообщении, позиционировании или заголовках (не только в таблице).
Свойство подтверждает формулировку, только если она стоит в нём утвердительно («не гарантирует» — не подтверждает).

  python3 scripts/promise_lint.py               # отчёт
  python3 scripts/promise_lint.py --matrix      # таблица «обещание → свойство → статус → источник»
  python3 scripts/promise_lint.py --json
Код выхода: 0 — чисто; 1 — есть нарушения; 2 — нет задачи или файлов.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

RISKY = [
    (r"\bсам(ый|ая|ое|ые|ым|ых)\b", "«самый»"),
    (r"\bлучш(ий|ая|ее|ие|его|ей|ую|им|их|ему|ими)\b", "«лучший»"),
    (r"№\s*1\b|\bномер\s+один\b|\bлидер\w*|\bпервы\w+\s+в\s+(россии|стране|мире)", "«№1 / лидер»"),
    (r"\bгарант\w*", "«гарантия»"),
    (r"\b100\s*%|\bстопроцентн\w*", "«100%»"),
    (r"\bполн\w*\s+защит\w*|\bполностью\s+(защищ|обезопас)\w*", "«полная защита»"),
    (r"\bабсолютн\w*\s+(защит|безопасн|надёжн|надежн|гарант)\w*|\bабсолютно\s+\w+", "«абсолютно»"),
    (r"\b(\w+(ее|ей)|лучше|хуже|дешевле|дороже|выше|ниже|больше|меньше|проще|чаще|реже|надёжней)\s+"
     r"(всех|всего|любого|любой|любых|других|конкурент\w*|аналог\w*|чем\s+у\b)",
     "сравнение «лучше / дешевле / надёжнее всех и конкурентов»"),
    (r"\bни\s+од(ин|на|но|ного|ной)\b|\bсто\s+процентов\b|#\s*1\b", "«ни один / сто процентов / #1»"),
    (r"\bот\s+(всех|любых)\s+мошенни\w*|\bвсех\s+мошенни\w*", "«от всех мошенников»"),
    (r"\bникогда\s+не\b|\bнавсегда\b", "«никогда / навсегда»"),
    (r"\bединственн\w*|\bне\s+имеет\s+аналогов\b|\bбез\s+аналогов\b", "«единственный / без аналогов»"),
    (r"\bбез\s+риска\b|\bнулев\w+\s+риск\w*", "«без риска»"),
]
_RISKY = [(re.compile(p, re.I), label) for p, label in RISKY]
PROMISE_COL = re.compile(r"обещани|сообщени", re.I)
SUPPORT_COL = re.compile(r"опор|свойств", re.I)
TYPE_COL = re.compile(r"^\s*(тип|статус)\s*$", re.I)
ID_COL = re.compile(r"^\s*id\s*$", re.I)
PROP_ID = re.compile(r"\bP-\d+\b")
KEY_SECTIONS = re.compile(r"слоган|ключев\w*\s+сообщени|позиционн|подтвержд|заголов|креатив|тексты?\s+для", re.I)
SKIP_SECTIONS = re.compile(r"отказ|не\s+говорим|запрещ|риск|возражени|чего\s+не", re.I)


NEGATION_BEFORE = re.compile(r"(\bне|\bбез|\bни|\bнельзя)\s+(\w+\s+){0,2}$", re.I)
STOP_STEMS = {"котор", "чтобы", "также", "может", "можно", "этого", "более", "всего", "только", "через", "после",
              "перед", "когда", "очень", "своих", "наших", "ваших"}
WORDS = re.compile(r"[A-Za-zА-Яа-яЁё]{5,}")


def risky_phrases(text: str, affirmative_only: bool = False) -> list[tuple[str, str]]:
    """[(ярлык, найденный фрагмент)]. affirmative_only: не считать слово после «не / без / ни»
    («не гарантирует», «не полная защита») — для свойств, которые подтверждают формулировку."""
    out = []
    for rx, label in _RISKY:
        for m in rx.finditer(text):
            if affirmative_only and NEGATION_BEFORE.search(text[: m.start()]):
                continue
            out.append((label, m.group(0)))
            break
    return out


def significant_stems(text: str) -> set[str]:
    stems = {core.norm_text(w)[:5] for w in WORDS.findall(PROP_ID.sub(" ", text))}
    return stems - STOP_STEMS


def parse_tables(md: str) -> list[list[list[str]]]:
    tables, cur = [], []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            cur.append(cells)
        else:
            if cur:
                tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    return tables


def parse_promises(md: str) -> list[dict]:
    promises = []
    for t in parse_tables(md):
        head = t[0]
        pi = next((i for i, h in enumerate(head) if PROMISE_COL.search(h)), None)
        si = next((i for i, h in enumerate(head) if SUPPORT_COL.search(h)), None)
        if pi is None or si is None or pi == si:
            continue
        ti = next((i for i, h in enumerate(head) if TYPE_COL.match(h)), None)
        ii = next((i for i, h in enumerate(head) if ID_COL.match(h)), None)
        for n, row in enumerate(t[1:], 1):
            if len(row) <= max(pi, si):
                continue
            text = re.sub(r"~~.*?~~", "", row[pi]).strip()
            if not text:
                continue
            promises.append({
                "id": (row[ii].strip() if ii is not None and ii < len(row) else "") or f"#{n}",
                "text": text,
                "props": PROP_ID.findall(row[si]),
                "type": row[ti].strip().lower() if ti is not None and ti < len(row) else "обещание",
            })
    return promises


def load_properties(proj: Path) -> tuple[dict, list[str]]:
    """P-id → свойство с effective_status. Статус факт подтверждается статусами claims."""
    errs = []
    data = core.read_json(proj / "state" / "product-properties.json", None)
    if data is None:
        return {}, ["нет state/product-properties.json"]
    props = data.get("properties", data if isinstance(data, list) else [])
    try:
        claims = {c["id"]: c for c in core.read_jsonl(proj / "state" / "claims.jsonl") if "id" in c}
    except ValueError as e:
        claims, errs = {}, [str(e)]
    out = {}
    for p in props:
        pid = p.get("id")
        if not pid:
            errs.append(f"свойство без id: {str(p)[:60]}")
            continue
        eff = p.get("status", "hypothesis")
        why = ""
        if eff == "fact":
            cids = p.get("claims") or []
            if not cids:
                eff, why = "hypothesis", "помечено фактом, но не опирается ни на один claim"
            else:
                bad = [c for c in cids if claims.get(c, {}).get("kind") != "fact" or claims.get(c, {}).get("status", "active") != "active"]
                if bad:
                    eff, why = "hypothesis", f"опорные claims не факты: {', '.join(bad)}"
        out[pid] = {**p, "effective_status": eff, "why": why}
    return out, errs


def lint(proj: Path) -> dict:
    rep = {"errors": [], "warnings": [], "promises": [], "stats": {}}
    props, perrs = load_properties(proj)
    rep["errors"].extend(perrs)
    comms = proj / "out" / "comms-strategy.md"
    if not comms.exists():
        rep["errors"].append("нет out/comms-strategy.md")
        return rep
    md = comms.read_text(encoding="utf-8")
    vplan = proj / "out" / "validation-plan.md"
    vtext = vplan.read_text(encoding="utf-8") if vplan.exists() else ""
    promises = parse_promises(md)
    if not promises:
        rep["errors"].append("в comms-strategy.md нет таблицы обещаний (колонки «Обещание» и «Опора»)")
    for pid, p in props.items():
        if p.get("why"):
            rep["warnings"].append(f"{pid}: {p['why']} — считается гипотезой")
    for pr in promises:
        issues = []
        is_test = "тест" in pr["type"]
        if not pr["props"]:
            issues.append(("E1", "нет опоры на свойство продукта"))
        unknown = [x for x in pr["props"] if x not in props]
        if unknown:
            issues.append(("E2", f"нет таких свойств: {', '.join(unknown)}"))
        known = [props[x] for x in pr["props"] if x in props]
        hyp = [p["id"] for p in known if p["effective_status"] != "fact"]
        if hyp and not is_test:
            issues.append(("E3", f"опора на гипотезу {', '.join(hyp)}: сузь обещание до фактов или сделай «тест сообщения» в плане проверки"))
        if is_test and pr["id"] not in vtext:
            issues.append(("E4", f"тест сообщения {pr['id']} не внесён в out/validation-plan.md"))
        facts = [p for p in known if p["effective_status"] == "fact"]
        fact_text = " ".join(p.get("statement", "") for p in facts)
        confirmed = {lb for lb, _ in risky_phrases(fact_text, affirmative_only=True)}
        for label, frag in risky_phrases(pr["text"]):
            if label not in confirmed:
                issues.append(("E5", f"рискованная формулировка {label} («{frag}») без подтверждающего свойства-факта (ст. 5 38-ФЗ)"))
        if known:
            ps = significant_stems(pr["text"])
            shared = ps & significant_stems(" ".join(p.get("statement", "") for p in known))
            if ps and len(shared) < min(2, len(ps)):
                issues.append(("E7", "у обещания и опорного свойства почти нет общих слов — похоже на ссылку на чужое свойство"))
        nums_ok = core.numbers_in(" ".join(p.get("statement", "") for p in known))
        bad_nums = [n for n in core.extract_numbers(PROP_ID.sub(" ", pr["text"])) if n not in nums_ok]
        if bad_nums and known:
            issues.append(("E6", f"числа без опоры в свойствах: {', '.join(bad_nums)}"))
        pr["issues"] = issues
        pr["ok"] = not issues
        rep["promises"].append(pr)

    # рискованные слова вне таблицы — предупреждение (кроме разделов про отказы и запреты)
    section = ""
    table_texts = {p["text"] for p in promises}
    for line in md.splitlines():
        if line.startswith("#"):
            section = line
            continue
        if SKIP_SECTIONS.search(section) or line.strip().startswith("|") or any(t in line for t in table_texts):
            continue
        for label, frag in risky_phrases(re.sub(r"~~.*?~~", "", line)):
            msg = f"{label} («{frag}») в строке «{line.strip()[:80]}» раздела «{section.lstrip('# ').strip()}»"
            if KEY_SECTIONS.search(section):
                rep["errors"].append(f"E8 слоган / ключевое сообщение: {msg} — главное сообщение подчиняется тем же правилам, что и обещания")
            else:
                rep["warnings"].append(f"вне таблицы обещаний: {msg}")
    n_bad = sum(1 for p in rep["promises"] if not p["ok"])
    rep["stats"] = {
        "promises": len(rep["promises"]),
        "ok": len(rep["promises"]) - n_bad,
        "failed": n_bad,
        "tests": sum(1 for p in rep["promises"] if "тест" in p["type"]),
        "properties": len(props),
        "property_facts": sum(1 for p in props.values() if p["effective_status"] == "fact"),
    }
    return rep


def matrix(proj: Path, rep: dict) -> str:
    props, _ = load_properties(proj)
    lines = ["| Обещание | Свойство | Статус свойства | Основания | Проверка |", "|---|---|---|---|---|"]
    for pr in rep["promises"]:
        refs = pr["props"] or ["—"]
        for i, pid in enumerate(refs):
            p = props.get(pid, {})
            st = core.KIND_RU.get(p.get("effective_status", ""), "—")
            check = ("✓" if pr["ok"] else "✗ " + "; ".join(code for code, _ in pr["issues"])) if i == 0 else ""
            lines.append(f"| {pr['id']} {pr['text'] if i == 0 else ''} | {pid} {p.get('statement', '')} | {st} | {', '.join(p.get('claims', [])) or '—'} | {check} |")
    return "\n".join(lines)


def render(rep: dict) -> str:
    s = rep["stats"]
    lines = [f"Сверка обещаний: обещаний {s.get('promises', 0)}, прошли {s.get('ok', 0)}, не прошли {s.get('failed', 0)} "
             f"(тестов сообщения {s.get('tests', 0)}); свойств {s.get('properties', 0)}, из них фактов {s.get('property_facts', 0)}"]
    for pr in rep["promises"]:
        if pr["ok"]:
            lines.append(f"  ✓ {pr['id']} «{pr['text'][:70]}» → {', '.join(pr['props'])}" + (" (тест сообщения)" if "тест" in pr["type"] else ""))
        else:
            for code, msg in pr["issues"]:
                lines.append(f"  ✗ {pr['id']} «{pr['text'][:70]}»: {code} {msg}")
    for e in rep["errors"]:
        lines.append(f"  ✗ {e}")
    for w in rep["warnings"]:
        lines.append(f"  ! {w}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--matrix", action="store_true")
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    rep = lint(proj)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    elif args.matrix:
        print(matrix(proj, rep))
    else:
        print(render(rep))
    if rep["errors"] and not rep["promises"]:
        return 2 if any("нет " in e for e in rep["errors"]) else 1
    return 1 if rep["errors"] or any(not p["ok"] for p in rep["promises"]) else 0


if __name__ == "__main__":
    sys.exit(main())
