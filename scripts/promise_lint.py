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
  E5 рискованная формулировка (ст. 5 38-ФЗ: «самый/самую», «лучший/наилучший», «№1», «первый в России»,
     «гарантированно», «100% / на все сто», «полная / максимальная защита», «безупречно», «лучше, чем у конкурентов»,
     «от любого мошенничества», «ни при каких обстоятельствах», «все / всегда / любой», …) без подтверждающего
     свойства-факта с той же формулировкой; латинские буквы-двойники и невидимые символы снимаются;
  E6 в обещании есть число, которого нет в опорных свойствах;
  E7 у обещания и опорного свойства меньше двух общих значимых слов (ссылка на «чужое» свойство);
  E8 рискованная формулировка в слогане, ключевом сообщении, позиционировании или заголовках (не только в таблице);
  E9 рискованная формулировка в другой таблице документа («Роль каналов» → «Что говорим») без свойства-факта в строке.
Сравнение с конкурентами («в отличие от аналогов» в позиционировании по Муру) — не риск само по себе: ловится вместе
со сравнительной или превосходной формой («надёжнее, чем у конкурентов»), а в таблице обещаний — без свойства-факта,
которое говорит о сравнении. Отрицание («не гарантирует блокировку всех звонков») и устойчивые обороты («тем самым»,
«всё просто», «больше всего», «самому близкому», «любого возраста», «каждый раз») не считаются; «не пропустит ни одного»
— считается. Матрица «обещание → свойство» (раздел «Матрица») не проверяется второй раз.
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

# Сравнительная степень: «быстрее», «надёжней», «лучше» (не существительные на -ей: «родителей», «детей»)
COMPARATIVE = (r"\w+ее|(быстр|надёжн|надежн|сильн|верн|удобн|выгодн|безопасн|точн|прост|умн|дешевл)ей|лучше|хуже|дешевле|"
               r"дороже|выше|ниже|больше|меньше|проще|чаще|реже")

RISKY = [
    (r"\bсам(ый|ая|ое|ые|ым|ых|ую|ыми)\b|\bсам(ого|ой|ому|ом)\s+\w+(ого|ой|ому|ом|ее|ей|ая|ый)\b", "«самый»"),
    (r"\b(наи)?лучш(ий|ая|ее|ие|его|ей|ую|им|их|ему|ими|ем)\b|\bнаилучш\w*", "«лучший»"),
    (r"№\s*1\b|\bномер\s+один\b|\bлидер\w*|\bперв(ый|ая|ое|ые|ой|ого|ую|ым|ом|ых)\s+(\w+\s+){0,3}в\s+"
     r"(россии|рф|стране|мире|европе|отрасли|мегафоне)", "«№1 / лидер / первый в России»"),
    (r"\bгарант\w*", "«гарантия»"),
    (r"\b100\s*%|\bстопроцентн\w*|\bна\s+все\s+сто\b|\bсто\s+процентов\b|\b100\s+процент\w*", "«100%»"),
    (r"\bполн\w*\s+защит\w*|\bполностью\s+(защищ|обезопас)\w*", "«полная защита»"),
    (r"\bабсолютн\w*\s+(защит|безопасн|надёжн|надежн|гарант)\w*|\bабсолютно\s+\w+|\bбезупречн\w*|\bидеальн\w*|\bнепревзойд\w*|\bуникальн\w*|"
     r"\bмаксимальн\w*\s+(защит|безопасн|надёжн|надежн|выгод|качеств|эффект|точн|охват)\w*",
     "«абсолютно / безупречно / максимально»"),
    (r"\b(" + COMPARATIVE + r")\s*,?\s+(чем\s+(у\s+)?(других|конкурент\w*|аналог\w*|любо\w+|все\w*|остальн\w*)|чем\s+у\b|"
     r"всех|любого|любой|любых|других|конкурент\w*|аналог\w*|не\s+бывает|некуда)|"
     r"\b(" + COMPARATIVE + r")\s+всего\b|\bкак\s+никто\s+(другой|иной)\b|\bкак\s+ни\s+(один|одна|одно)\b",
     "сравнение «лучше / дешевле / надёжнее всех и конкурентов»"),
    (r"\bни\s+од(ин|на|но|ного|ной)\b|\b(ни|без)\s+единого\b|#\s*1\b|\bни\s+при\s+каких\b",
     "«ни один / ни при каких обстоятельствах / #1»"),
    (r"\bот\s+(всех|любых|любого|любой)\s+\w*|\bвсех\s+мошенни\w*", "«от всех / от любого мошенничества»"),
    (r"\bвс(е|ё|ех|ем|еми)\b|\bвсегда\b|\bлюб(ой|ого|ая|ую|ое|ые|ых|ым|ом)\b|\bкажд(ый|ая|ое|ого|ую|ой|ом)\b",
     "«все / всегда / любой» (если свойство говорит «большинство» или «часть»)"),
    (r"\bникогда\s+не\b|\bнавсегда\b", "«никогда / навсегда»"),
    (r"\bединственн\w*|\bне\s+имеет\s+аналогов\b|\bбез\s+аналогов\b", "«единственный / без аналогов»"),
    (r"\bбез\s+риска\b|\bнулев\w+\s+риск\w*", "«без риска»"),
]
# Упоминание конкурентов само по себе не риск (позиционное утверждение Мура: «в отличие от …»). В таблице обещаний
# оно требует свойства-факта, которое говорит о сравнении; в тексте ловится только вместе со сравнительной формой.
COMPETITORS = (r"\bконкурент\w*|\bаналог\w*|\bу\s+других\s+оператор\w*", "сравнение с конкурентами")
QUANT_LABEL = "«все / всегда / любой» (если свойство говорит «большинство» или «часть»)"
# Формулировки, которые отрицание не снимает: «не пропустит ни одного» — то же «все»
NEG_PROOF = {"«ни один / ни при каких обстоятельствах / #1»", "«никогда / навсегда»", "«без риска»"}
# Устойчивые обороты, в которых слова из списка — не рекламное утверждение (вырезаются до проверки)
SET_PHRASES = re.compile(
    r"\bтем\s+самым\b|\b(то|тот|та|те|той|тому|тем|того|тех)\s+же\s+сам\w*|\bна\s+самом\s+деле\b|\bв\s+самом\s+деле\b|"
    r"\b(с|в|до)\s+сам(ого|ом)\s+(начал|конц)\w*|\bсам\w*\s+(близк|родн)\w*|\bсам(ое|ым)\s+(главн|важн)\w*|"
    r"\bсам(ому|ого|ой|ом)\s+\w+(аем|яем)\w*|"
    r"\bвс[её]\s+(просто|равно|ещ[её]|же|это|понятно|сразу)\b|\bвс[её]-таки\b|\bпрежде\s+всего\b|"
    r"\b(больше|меньше|чаще|реже|выше|ниже)\s+всего\b|\bкажд(ый|ого|ому|ым|ом)\s+раз\w*|"
    r"\b(родител|дет|люд|пользовател|клиент|абонент|человек|сем)\w*\s+любого\s+возраст\w*|\bлюбого\s+возраст\w*",
    re.I)
# Латиница, похожая на кириллицу: «Гaрантированно» с латинской a не должна проходить мимо проверки
HOMOGLYPHS = str.maketrans("aAeEoOpPcCxXyBHKMTkmt", "аАеЕоОрРсСхХуВНКМТкмт")
INVISIBLE = re.compile(r"[\u00ad\u200b-\u200f\u2060\ufeff]")


def normalize(text: str) -> str:
    """Убрать невидимые символы и заменить латинские двойники в словах, где есть кириллица."""
    text = INVISIBLE.sub("", text)
    return re.sub(r"\w+", lambda m: m.group(0).translate(HOMOGLYPHS) if re.search(r"[А-Яа-яЁё]", m.group(0)) else m.group(0), text)


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


def risky_phrases(text: str, affirmative_only: bool = False, competitors: bool = False,
                  quantifiers: bool = True) -> list[tuple[str, str]]:
    """[(ярлык, найденный фрагмент)]. affirmative_only: не считать слово после «не / без / ни» («не гарантирует
    блокировку всех звонков», «не полная защита»), кроме формулировок, которые отрицание не снимает («не пропустит ни
    одного»). Устойчивые обороты («тем самым», «всё просто», «больше всего», «самому близкому», «любого возраста»)
    не считаются. competitors: упоминание конкурентов без сравнительной формы тоже риск (для таблицы обещаний).
    quantifiers=False — без «все / всегда / любой» (для сравнения с текстом чата, где это не обещание)."""
    out = []
    text = SET_PHRASES.sub(lambda m: " " * len(m.group(0)), normalize(text))
    pats = _RISKY + ([(re.compile(COMPETITORS[0], re.I), COMPETITORS[1])] if competitors else [])
    for rx, label in pats:
        if not quantifiers and label == QUANT_LABEL:
            continue
        for m in rx.finditer(text):
            if affirmative_only and label not in NEG_PROOF and NEGATION_BEFORE.search(text[: m.start()]):
                continue
            out.append((label, m.group(0).strip()))
            break
    return out


def significant_stems(text: str) -> set[str]:
    stems = {core.norm_text(w)[:5] for w in WORDS.findall(PROP_ID.sub(" ", text))}
    return stems - STOP_STEMS


def parse_tables(md: str, with_sections: bool = False) -> list:
    """Таблицы Markdown: [строки] или, с with_sections, [(заголовок раздела, строки)]."""
    tables, cur, section, cur_sec = [], [], "", ""
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if not cur:
                cur_sec = section
            cur.append(cells)
        else:
            if cur:
                tables.append((cur_sec, cur))
            cur = []
            if s.startswith("#"):
                section = s
    if cur:
        tables.append((cur_sec, cur))
    return tables if with_sections else [t for _, t in tables]


MATRIX_SECTION = re.compile(r"матриц", re.I)  # матрица «обещание → свойство» повторяет обещания, её не проверяем дважды


def promise_columns(head: list[str]) -> tuple[int | None, int | None]:
    pi = next((i for i, h in enumerate(head) if PROMISE_COL.search(h)), None)
    si = next((i for i, h in enumerate(head) if SUPPORT_COL.search(h)), None)
    return (pi, si) if pi is not None and si is not None and pi != si else (None, None)


def parse_promises(md: str) -> list[dict]:
    promises = []
    for sec, t in parse_tables(md, with_sections=True):
        head = t[0]
        pi, si = promise_columns(head)
        if pi is None or MATRIX_SECTION.search(sec) or any(re.fullmatch(r"проверка", h, re.I) for h in head):
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
    if not props and "strategy" in core.stages_passed(core.load_task(proj).get("stage")):
        rep["errors"].append("этап strategy пройден, а реестр свойств state/product-properties.json пуст")
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
        confirmed = {lb for lb, _ in risky_phrases(fact_text, affirmative_only=True, competitors=True)}
        for label, frag in risky_phrases(pr["text"], affirmative_only=True, competitors=True):
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

    # другие таблицы документа («Роль каналов»: «Что говорим», креативы) — то же, что обещания: риск без
    # подтверждающего свойства-факта в той же строке — ошибка E9
    for sec, t in parse_tables(md, with_sections=True):
        if promise_columns(t[0])[0] is not None or SKIP_SECTIONS.search(sec) or MATRIX_SECTION.search(sec):
            continue
        for row in t[1:]:
            line = " | ".join(re.sub(r"~~.*?~~", "", c) for c in row)
            refs = [props[x] for x in PROP_ID.findall(line) if x in props and props[x]["effective_status"] == "fact"]
            ok = {lb for lb, _ in risky_phrases(" ".join(p.get("statement", "") for p in refs), affirmative_only=True)}
            for label, frag in risky_phrases(line, affirmative_only=True):
                if label not in ok:
                    rep["errors"].append(f"E9 таблица раздела «{sec.lstrip('# ').strip() or 'без заголовка'}»: {label} («{frag}») "
                                         f"в строке «{line.strip()[:80]}» без подтверждающего свойства-факта — "
                                         "в каналах говорим то же, что в обещаниях")
    # рискованные слова вне таблиц: в слогане, ключевом сообщении, позиционировании — ошибка, в остальном — предупреждение
    section = ""
    table_texts = {p["text"] for p in promises}
    for line in md.splitlines():
        if line.startswith("#"):
            section = line
            continue
        if SKIP_SECTIONS.search(section) or MATRIX_SECTION.search(section) or line.strip().startswith("|") \
                or any(t in line for t in table_texts):
            continue
        for label, frag in risky_phrases(re.sub(r"~~.*?~~", "", line), affirmative_only=True):
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
            check = (("✓ тест сообщения (в плане проверки)" if "тест" in pr["type"] else "✓") if pr["ok"] else "✗ " + "; ".join(code for code, _ in pr["issues"])) if i == 0 else ""
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
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
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
