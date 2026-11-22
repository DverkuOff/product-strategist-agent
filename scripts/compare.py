#!/usr/bin/env python3
"""Сравнение с исходным способом: результат агента против ответа обычного чата на тот же запрос.

Оба текста прогоняются через одни и те же детерминированные проверки (без LLM):
  - рискованные формулировки ст. 5 38-ФЗ (с учётом отрицаний «не обещать 100%»);
  - числа без метки статуса и без ссылки на источник;
  - числа, которых нет ни в одном снимке materials/ задачи (непроверяемые цифры);
  - разметка факт / гипотеза / прогноз и обязательные блоки брифа (варианты, «оставить как есть»,
    возражения, «чего не знаем», план проверки: контроль, срок, нежелательные последствия, kill-критерий);
  - обещания: у агента — promise_lint; у чата — baseline/promise-review.json (разметка обещаний чата
    по реестру свойств, если есть; это суждение модели или человека, а не автоматическая проверка);
  - время и стоимость: агент — state/cost-ledger.csv, чат — baseline/meta.json.

  python3 scripts/compare.py [--project <slug|путь>] [--no-write]
Результат печатается и сохраняется в out/compare.md.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import promise_lint  # noqa: E402
import verify_claims  # noqa: E402

NEGATION = re.compile(r"(\bне\b|\bнельзя\b|избега\w*|\bбез\b|запрещ\w*|отказ\w*|не\s+говорим)[^.\n]{0,40}$", re.I)
LABEL = re.compile(r"\[(факт|гипотеза|прогноз|синтетика)|\b[CMPT]-\d+\b|MSG-\d+|https?://|гипотез\w*|прогноз\w*|оценк\w*|по данным|сообщает", re.I)
LIST_NUM = re.compile(r"^\s*(#+\s*)?(\d+[.)]\s*)+")
IDS = re.compile(r"\b(?:[CMPDT]|MSG)-\d+\b")
# «k=100 %», «при 100 % приписывании» — значение параметра в расчёте, а не обещание
PARAM_BEFORE = re.compile(r"(?:[=≤≥<>]|\bпри)\s*$", re.I)
# варианты в виде «## Вариант A», «**A. …**» или строк таблицы «| **B. …** |»
OPTION_MARK = re.compile(r"^#+\s*вариант\s+(\S+)|^\s*(?:\|\s*)?\*\*(?:вариант\s+)?([A-DА-Г])[.)]\s", re.I | re.M)

CHECKS = [
    ("≥3 вариантов решения", lambda t: len({(a or b).upper() for a, b in OPTION_MARK.findall(t)}) >= 3),
    ("вариант «оставить как есть»", lambda t: bool(re.search(r"оставить как есть|ничего не делать|статус-кво|без изменений", t, re.I))),
    ("рассмотрено «закрыть направление»", lambda t: bool(re.search(r"закрыть направление|закрыть продукт|свернуть", t, re.I))),
    ("сильные возражения", lambda t: bool(re.search(r"возражени|провал\w*,? потому что|pre-mortem", t, re.I))),
    ("раздел «чего не знаем»", lambda t: bool(re.search(r"чего (мы )?не знаем|пробел|неизвестн", t, re.I))),
    ("осознанные отказы", lambda t: bool(re.search(r"отказ\w*|не делаем|чего не говорим", t, re.I))),
    ("план: с чем сравниваем (контроль)", lambda t: bool(re.search(r"контрольн\w+ групп|holdout|с чем сравниваем", t, re.I))),
    ("план: срок наблюдения", lambda t: bool(re.search(r"\bсрок\b|\d+\s*недел|\d+\s*месяц", t, re.I))),
    ("план: нежелательные последствия", lambda t: bool(re.search(r"нежелательн|guardrail|стоп-сигнал|стоп-правил", t, re.I))),
    ("план: kill-критерий", lambda t: bool(re.search(r"kill|критери\w+ отмен|отменя\w+ решени|\bостановить\b", t, re.I))),
]


def _context(line: str, frag: str, width: int = 40) -> str:
    """Фрагмент строки вокруг совпадения: жюри видит само слово, а не начало строки."""
    i = promise_lint.normalize(line).lower().find(frag.lower())
    if i < 0:
        return line.strip()[:2 * width]
    a, b = max(0, i - width), min(len(line), i + len(frag) + width)
    return ("…" if a else "") + line[a:b].strip() + ("…" if b < len(line) else "")


def risky(text: str) -> list[str]:
    """Рискованные формулировки (та же логика, что в promise_lint: отрицание, устойчивые обороты) вне разделов про
    отказы и риски, вне цитат возражений; одинаково для обоих текстов. «Все / любой» здесь не считаются: в общем
    тексте это не обещание, а риск обещания проверяет promise_lint по реестру свойств."""
    out = []
    section = ""
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            section = line
            continue
        if promise_lint.SKIP_SECTIONS.search(section) or promise_lint.MATRIX_SECTION.search(section):
            continue
        clean = re.sub(r"«[^»]*»|\"[^\"]*\"", lambda m: " " * len(m.group(0)), line)  # цитаты клиентов и возражений
        for label, frag in promise_lint.risky_phrases(clean, affirmative_only=True, quantifiers=False):
            pos = promise_lint.normalize(clean).lower().find(frag.lower())
            if pos >= 0 and (NEGATION.search(clean[:pos]) or ("100" in frag and PARAM_BEFORE.search(clean[:pos]))):
                continue
            out.append(f"{label}: «{frag}» — {_context(line, frag)}")
    return out


def number_lines(text: str, material_numbers: set[str]) -> tuple[list[str], list[str]]:
    """(строки с числами без метки/источника, числа, которых нет в материалах)."""
    unlabeled, unknown = [], []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        body = IDS.sub(" ", LIST_NUM.sub("", line))
        nums = core.extract_numbers(body)
        if not nums:
            continue
        if not LABEL.search(line):
            unlabeled.append(line.strip()[:100])
        unknown.extend(n for n in nums if n not in material_numbers)
    return unlabeled, sorted(set(unknown), key=lambda x: float(x))


def analyze(text: str, material_numbers: set[str]) -> dict:
    unl, unk = number_lines(text, material_numbers)
    return {
        "chars": len(text),
        "risky": risky(text),
        "unlabeled_number_lines": unl,
        "unknown_numbers": unk,
        "status_marks": len(verify_claims.MARK_RE.findall(text)),
        "checks": {name: fn(text) for name, fn in CHECKS},
    }


def agent_text(proj: Path) -> str:
    docs = [p for p in sorted((proj / "out").glob("*.md")) if p.name not in {"compare.md", "README.md", "research-log.md"}]
    return "\n\n".join(p.read_text(encoding="utf-8") for p in docs)


def ledger_time_cost(proj: Path) -> tuple[float | None, str]:
    rows = core.read_ledger(proj)
    if not rows:
        return None, "нет данных: сквозной прогон в Claude Code ещё не записан"
    total = sum(float(r.get("cost_usd") or 0) for r in rows)
    ts = sorted(datetime.fromisoformat(r["ts"]) for r in rows if r.get("ts"))
    span = (ts[-1] - ts[0]).total_seconds() / 60 if len(ts) > 1 else 0
    return total, f"≈{span:.0f} мин между первой и последней записью журнала стоимости"


def build(proj: Path) -> str:
    chat_file = proj / "baseline" / "chat-answer.md"
    if not chat_file.exists():
        raise SystemExit("Нет baseline/chat-answer.md — сохрани ответ обычного чата на тот же запрос (скилл compare).")
    chat = chat_file.read_text(encoding="utf-8")
    meta = core.read_json(proj / "baseline" / "meta.json", {}) or {}
    mats = core.list_materials(proj)
    mat_nums: set[str] = set()
    for m in mats.values():
        mat_nums |= core.numbers_in(m["body"])
    a_text = agent_text(proj)
    if not a_text.strip():
        raise SystemExit("В out/ нет документов агента — сравнивать нечего.")
    A, C = analyze(a_text, mat_nums), analyze(chat, mat_nums)
    vrep = verify_claims.check(proj)
    prep = promise_lint.lint(proj) if (proj / "out" / "comms-strategy.md").exists() else {"stats": {}, "promises": []}
    review = core.read_json(proj / "baseline" / "promise-review.json", None)
    a_cost, a_time = ledger_time_cost(proj)

    def yn(b):
        return "да" if b else "нет"

    L = [f"# Сравнение: агент против обычного чата ({proj.name})", "",
         f"Запрос: {meta.get('prompt', '(см. baseline/meta.json)')}", "",
         f"Обычный чат: {meta.get('model', '?')}, {meta.get('date', '?')}; {meta.get('how', '')}", "",
         "Все строки ниже, кроме отмеченных «суждение», посчитаны детерминированно (`scripts/compare.py`, без LLM).", "",
         "| Показатель | Агент | Обычный чат |", "|---|---|---|"]
    ps = prep.get("stats", {})
    L.append(f"| Ключевых обещаний | {ps.get('promises', '—')} | {len(review['promises']) if review else 'не размечено'} |")
    L.append(f"| …с опорой на подтверждённое свойство продукта | {ps.get('ok', 0) - ps.get('tests', 0)} (ещё {ps.get('tests', 0)} — тесты сообщения в плане проверки) | "
             + (f"{sum(1 for p in review['promises'] if p['verdict'] == 'опора')} (суждение, см. ниже)" if review else "—") + " |")
    if review:
        for v in ("шире свойства", "противоречит факту", "нет опоры"):
            L.append(f"| …{v} (суждение) | 0 | {sum(1 for p in review['promises'] if p['verdict'] == v)} |")
    L.append(f"| Рискованные формулировки (ст. 5 38-ФЗ) | {len(A['risky'])} | {len(C['risky'])} |")
    L.append(f"| Строк с числами без метки статуса и источника | {len(A['unlabeled_number_lines'])} | {len(C['unlabeled_number_lines'])} |")
    L.append(f"| Чисел, которых нет в материалах задачи | {len(A['unknown_numbers'])} | {len(C['unknown_numbers'])} |")
    L.append(f"| Меток факт/гипотеза/прогноз с ID утверждения | {A['status_marks']} | {C['status_marks']} |")
    vs = vrep.get("stats", {})
    L.append(f"| Фактов, подтверждённых снимками источников | {len(vrep.get('ok', []))} из {vs.get('fact', 0)} | 0 (источников нет) |")
    for name in A["checks"]:
        L.append(f"| {name} | {yn(A['checks'][name])} | {yn(C['checks'][name])} |")
    a_cost_s = f"${a_cost:.2f}" if a_cost is not None else "нет данных (журнал стоимости пуст: прогон не записан)"
    L.append(f"| Стоимость (оценка по прейскуранту API) | {a_cost_s} | ${float(meta.get('cost_usd') or 0):.2f} |")
    L.append(f"| Время | {a_time} | {meta.get('duration_s', '?')} с генерации + проверка человеком: {meta.get('human_minutes_to_verify') or 'не замерено'} |")
    L += ["", "## Как читать",
          "- Чат не видел материалов задачи — так и выглядит исходный способ: правдоподобный текст без проверяемой опоры. Числа чата в основном — целевые значения и сегменты «из головы»; проверки показывают, что их нечем подтвердить, а не что они ложны.",
          "- Проверки не оценивают смысловую точность и качество идей: хорошие идеи чата (подарочная механика, триггер после подозрительного звонка) агент может взять как гипотезы для плана проверки.",
          "- Цена разницы: агент дороже и дольше одного ответа чата; выигрыш — в проверяемости и в том, что обещания не расходятся с продуктом."]
    if review:
        L += ["", "## Обещания чата по реестру свойств (суждение)", f"Разметка: {review.get('by', '?')}", "",
              "| Обещание чата | Вердикт | Свойство | Почему |", "|---|---|---|---|"]
        for p in review["promises"]:
            L.append(f"| {p['text']} | {p['verdict']} | {', '.join(p.get('props', [])) or '—'} | {p.get('note', '')} |")
    if C["risky"]:
        L += ["", "## Рискованные формулировки в ответе чата"] + [f"- {r}" for r in C["risky"][:10]]
    if A["risky"]:
        L += ["", "## Рискованные формулировки у агента"] + [f"- {r}" for r in A["risky"][:10]]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("--project", default=None)
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    try:
        md = build(proj)
    except SystemExit as e:  # нет baseline или документов агента — это ошибка, а не «сравнение готово»
        print(e, file=sys.stderr)
        return 2
    print(md)
    if not args.no_write:
        (proj / "out" / "compare.md").write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
