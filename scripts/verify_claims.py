#!/usr/bin/env python3
"""«Протокол доказательств»-lite: проверка утверждений задачи без LLM.

Правила для каждого активного утверждения со статусом fact:
  1. есть источник (sources) — иначе понижение до гипотезы («прежний ответ агента не факт»);
  2. источник — сохранённый снимок M-xx в materials/ — иначе понижение;
  3. снимок не синтетический (kind: synthetic) и само утверждение не synthetic — иначе понижение;
  4. у источника есть дословная цитата (регистр, ё/е, пробелы и кавычки не важны) не короче 4 слов и 20 знаков,
     и она есть в снимке; снимок не пустой (≥100 символов) — иначе понижение;
  5. числа (с учётом «тыс./млн/млрд», % и форматов дат) и имена собственные (целым словом, основа ≥4 букв)
     есть в предложении цитаты или в атрибуции снимка (title, publisher, published) — иначе понижение;
     проценты и квантификаторы («гарантированно», «полный», «все», «всегда», «любой», «каждый», «никогда»,
     «без исключений», «100%») должны стоять в самой цитате, а не где-то в снимке;
  8. хотя бы один источник факта — не форум, блог, отзывы, соцсети (ugc) и не реклама продавца (advertising):
     тип источника пишет fetch_source.py в materials/MANIFEST.json (агент его не меняет) — иначе понижение;
     числа, имена и квантификаторы ищутся только в цитатах СИЛЬНЫХ источников: второй источник из СМИ не делает
     фактом цифру, которая есть только на форуме;
  6. «проверено человеком» — только если в state/human.jsonl есть запись РП с хэшем текущего текста
     (команду claims.py human-verified агент сам выполнить не может: Claude Code спрашивает РП);
     пометка verified в claims.jsonl без такой записи игнорируется.
  7. снимок локального файла не из inbox/ (файл, который агент сам написал в папке задачи) — не основание факта.
Семантику («подтверждает ли источник вывод») скрипт не проверяет — это осознанное ограничение.

Снимки неизменяемы: если sha256 файла не совпадает с materials/MANIFEST.json (снимок правили после
сохранения) — ошибка, а факты на этом снимке понижаются.

Плюс сверка документов out/*.md: метка [факт C-007] должна совпадать со статусом C-007 в claims,
ссылки на несуществующие и отозванные утверждения — ошибка.

  python3 scripts/verify_claims.py            # отчёт, ничего не меняет
  python3 scripts/verify_claims.py --fix      # записать понижения в state/claims.jsonl
  python3 scripts/verify_claims.py --json
Код выхода: 0 — всё чисто; 1 — есть понижения или ошибки; 2 — нет задачи или битый файл.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ID_RE = re.compile(r"\b[CMPD]-\d+\b")
MARK_RE = re.compile(r"\[(факт|гипотеза|прогноз|синтетика)[^\]\n]*?\b(C-\d+)\]", re.I)
RU_KIND = {"факт": "fact", "гипотеза": "hypothesis", "прогноз": "forecast", "синтетика": "synthetic"}


MIN_SNAPSHOT_CHARS = 100  # меньше — капча, JS-страница или пустой файл: не основание факта
MIN_QUOTE_WORDS, MIN_QUOTE_CHARS = 4, 20  # цитата из одного слова делает правило «дословная цитата» пустым
QUANTIFIERS = [
    (r"гарантир\w*", "«гарантированно»"),
    (r"\bполн(ая|ой|ую|ое|ый|ого|ым|ом|ые|ых|ыми|остью)\b", "«полный / полностью»"),
    (r"\bвс(е|ё|ех|ем|еми|я|ю|его)\b", "«все»"),
    (r"\bвсегда\b|\bнавсегда\b", "«всегда»"),
    (r"\bлюб(ой|ого|ая|ую|ое|ые|ых|ым|ом|ому)\b", "«любой»"),
    (r"\bкажд\w+", "«каждый»"),
    (r"\bникогда\b|\bни\s+од\w+", "«никогда / ни один»"),
    (r"\bабсолютн\w*|\bбез\s+исключени\w*|\b100\s*%|\bстопроцентн\w*", "«абсолютно / без исключений / 100%»"),
]
_QUANT = [(re.compile(p, re.I), label) for p, label in QUANTIFIERS]
PCT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|процент\w*)", re.I)
SENT_BOUND = re.compile(r"(?<=[.!?…])\s+(?=[«\"„(\-—–]?\s*[A-ZА-ЯЁ0-9])|\n")


def quote_regex(quote: str) -> re.Pattern | None:
    """Цитата как регулярное выражение по исходному тексту: регистр, ё/е, пробелы и кавычки не важны."""
    nq = core.norm_text(quote).strip()
    if not nq:
        return None
    parts = []
    q = r"[«»\"„“”']*"  # кавычки в снимке могут стоять где угодно: norm_text их из цитаты убрал
    for ch in nq:
        if ch == " ":
            parts.append(r"[\s«»\"„“”']+")
        elif ch == "е":
            parts.append("[её]" + q)
        else:
            parts.append(re.escape(ch) + q)
    return re.compile("".join(parts), re.I)


def quote_sentences(body: str, quote: str) -> str | None:
    """Предложение (или несколько), в котором стоит цитата; None — цитаты в снимке нет."""
    rx = quote_regex(quote)
    m = rx.search(body) if rx else None
    if not m:
        return None
    starts = [b.end() for b in SENT_BOUND.finditer(body) if b.end() <= m.start()]  # endpos ломает lookahead
    a = starts[-1] if starts else 0
    e = SENT_BOUND.search(body, m.end())
    return body[a: e.start() if e else len(body)]


def quote_too_short(quote: str) -> bool:
    return len(re.findall(r"\w+", quote)) < MIN_QUOTE_WORDS or len(quote.strip()) < MIN_QUOTE_CHARS


def missing_in_quotes(text: str, quotes: str) -> list[str]:
    """Проценты и квантификаторы утверждения, которых нет в самих цитатах (не в предложении и не в снимке)."""
    text = ID_RE.sub(" ", core.norm_text(text).replace("ё", "е"))
    q = core.norm_text(quotes).replace("ё", "е")
    miss = [label for rx, label in _QUANT if rx.search(text) and not rx.search(q)]
    for m in PCT_RE.finditer(text):
        if not core.same_quantity(m.group(0), q) and not any(core.same_quantity(m.group(0), x.group(0)) for x in PCT_RE.finditer(q)):
            miss.append(m.group(0))
    return miss


def missing_in_evidence(text: str, evidence: str, full: str) -> list[str]:
    """Числа, даты и имена собственные утверждения, которых нет в основании.

    Числа и даты — в предложении цитаты (с учётом «тыс./млн/млрд», %, форматов дат). Имена — там же целым
    словом. Первое слово предложения может быть и именем («Билайн предлагает…»), и обычным словом
    («Обзор сообщает…»), поэтому его ищем во всём снимке full."""
    text = ID_RE.sub(" ", text)
    ev_norm, full_norm = core.norm_text(evidence), core.norm_text(full)
    first = core.sentence_initial_words(text)
    missing = core.missing_quantities(text, evidence)
    for w in core.extract_proper_nouns(text):
        if not core.name_found(w, full_norm if w in first else ev_norm):
            missing.append(w)
    return list(dict.fromkeys(missing))


def check(proj: Path) -> dict:
    rep = {"errors": [], "warnings": [], "downgrade": [], "human": [], "ok": [], "stats": {}}
    try:
        claims = core.read_jsonl(proj / "state" / "claims.jsonl")
    except ValueError as e:
        rep["errors"].append(str(e))
        return rep
    mats = core.list_materials(proj)
    manifest = core.read_json(proj / "materials" / core.MANIFEST, {}) or {}
    rep["weak_hypotheses"] = []
    human_ok = core.human_verified_ids(proj, claims)
    for mid, files in core.duplicate_material_ids(proj).items():
        rep["errors"].append(f"{mid}: id снимка повторяется в файлах {', '.join(files)} — непонятно, какой из них основание")
    changed, unlisted = core.manifest_check(proj)
    for mid, why in changed.items():
        rep["errors"].append(f"{mid}: {why}")
    for mid in unlisted:
        rep["warnings"].append(f"{mid}: снимка нет в materials/MANIFEST.json — сохранён не через fetch_source.py")
    ids = {}
    for c in claims:
        cid = c.get("id")
        if not cid:
            rep["errors"].append(f"утверждение без id: {str(c)[:80]}")
            continue
        if cid in ids:
            rep["errors"].append(f"{cid}: id повторяется")
        ids[cid] = c
        if c.get("kind") not in core.CLAIM_KINDS:
            rep["errors"].append(f"{cid}: неизвестный kind «{c.get('kind')}»")
        if c.get("status", "active") not in core.CLAIM_STATUSES:
            rep["errors"].append(f"{cid}: неизвестный status «{c.get('status')}»")
        if c.get("status") == "superseded" and c.get("superseded_by") not in {x.get("id") for x in claims}:
            rep["errors"].append(f"{cid}: superseded без существующего superseded_by")

    for c in claims:
        cid = c.get("id")
        if not cid or c.get("status", "active") != "active":
            continue
        kind = c.get("kind")
        if kind == "synthetic" or c.get("origin") == "synthetic":
            if kind == "fact":
                rep["downgrade"].append((cid, "synthetic", "синтетический ответ не может быть фактом"))
            continue
        if kind != "fact":
            mids = [s.get("material") for s in c.get("sources") or [] if s.get("material") in mats]
            if kind == "hypothesis" and mids and all(core.material_source_type(proj, m, mats[m], manifest) in core.WEAK_SOURCE_TYPES for m in mids):
                rep["weak_hypotheses"].append((cid, mids))
            if kind == "forecast" and not (c.get("basis") or c.get("sources")):
                rep["warnings"].append(f"{cid}: прогноз без оснований (basis: [C-...] или sources)")
            continue
        sources = c.get("sources") or []
        if cid in human_ok:
            if not sources:
                rep["downgrade"].append((cid, "no_source", "проверено человеком, но источник не указан"))
            else:
                rep["human"].append(cid)
            continue
        if c.get("verified") == "human":
            rep["warnings"].append(f"{cid}: пометка verified: human без записи РП в state/human.jsonl — игнорируется")
        if not sources:
            reason = "прежний вывод агента без источника" if c.get("origin") == "agent" else "нет источника"
            rep["downgrade"].append((cid, "no_source", reason))
            continue
        snaps, fulls, quotes, types = [], [], [], []
        bad = None
        for s in sources:
            mid = s.get("material")
            if not mid:
                bad = ("no_snapshot", f"источник {s.get('url', '?')} без сохранённого снимка (M-xx)")
                continue
            mat = mats.get(mid)
            if not mat:
                bad = ("no_snapshot", f"снимка {mid} нет в materials/")
                continue
            if mid in changed:
                bad = ("snapshot_changed", f"{mid}: {changed[mid]}")
                continue
            if core.material_is_agent_file(mat):
                bad = ("agent_file", f"{mid} — файл из папки задачи, а не источник или материал РП из inbox/")
                continue
            if core.material_is_synthetic(mat):
                bad = ("synthetic", f"{mid} — синтетический материал, не основание факта")
                continue
            meta = mat.get("meta", {})
            attribution = " ".join(str(meta.get(k, "")) for k in ("title", "publisher", "published"))
            body = mat["body"]
            if len(body.strip()) < MIN_SNAPSHOT_CHARS:
                bad = ("empty_snapshot", f"{mid}: снимок почти пустой ({len(body.strip())} символов) — капча, JS-страница или пустой файл")
                continue
            quote = s.get("quote")
            if not quote:
                bad = ("no_quote", f"у источника {mid} нет цитаты — факт нечем проверить")
                continue
            if quote_too_short(quote):
                bad = ("short_quote", f"цитата из {mid} слишком короткая («{quote[:40]}»): нужно не меньше "
                                      f"{MIN_QUOTE_WORDS} слов и {MIN_QUOTE_CHARS} знаков, на которых держится утверждение")
                continue
            sent = quote_sentences(body, quote)
            if sent is None:
                bad = ("quote_not_found", f"цитаты нет в {mid}: «{quote[:60]}»")
                continue
            snaps.append(sent + " " + attribution)
            fulls.append(body + " " + attribution)
            quotes.append(quote)
            types.append((mid, core.material_source_type(proj, mid, mat, manifest)))
        if not snaps:
            rep["downgrade"].append((cid, *(bad or ("no_snapshot", "нет пригодного снимка"))))
            continue
        if all(t in core.WEAK_SOURCE_TYPES for _, t in types):
            rep["downgrade"].append((cid, "weak_source", "все источники — форум, блог, отзывы или реклама ("
                                     + ", ".join(f"{m}: {t}" for m, t in types)
                                     + "): для факта нужен первичный источник, исследование или СМИ"))
            continue
        # числа, имена и квантификаторы — только из сильных источников: слабый (форум, реклама) рядом с СМИ не
        # «отмывает» свою цифру («99%» с форума + «большинство» из СМИ → 99% не подтверждено)
        strong = [i for i, (_, t) in enumerate(types) if t not in core.WEAK_SOURCE_TYPES]
        miss = missing_in_evidence(c.get("text", ""), "\n".join(snaps[i] for i in strong), "\n".join(fulls[i] for i in strong))
        qmiss = missing_in_quotes(c.get("text", ""), "\n".join(quotes[i] for i in strong))
        if len(strong) < len(types) and (miss or qmiss):
            weak = ", ".join(f"{m}: {t}" for m, t in types if t in core.WEAK_SOURCE_TYPES)
            miss = [f"{x} (есть только в слабом источнике {weak})" for x in miss]
            qmiss = [f"{x} (есть только в слабом источнике {weak})" for x in qmiss]
        if miss:
            rep["downgrade"].append((cid, "not_in_snapshot", "нет в предложении цитаты: " + ", ".join(miss)))
        elif qmiss:
            rep["downgrade"].append((cid, "not_in_quote", "в самой цитате нет: " + ", ".join(qmiss)
                                     + " — квантификаторы и проценты должны стоять в цитате"))
        else:
            rep["ok"].append(cid)

    # сверка документов для РП
    out_dir = proj / "out"
    down_ids = {d[0] for d in rep["downgrade"]}
    if out_dir.is_dir():
        for doc in sorted(out_dir.glob("*.md")):
            text = doc.read_text(encoding="utf-8")
            for m in MARK_RE.finditer(text):
                label, cid = m.group(1).lower(), m.group(2)
                c = ids.get(cid)
                if not c:
                    rep["errors"].append(f"{doc.name}: ссылка на несуществующее {cid}")
                    continue
                st = c.get("status", "active")
                if st == "retracted":
                    rep["errors"].append(f"{doc.name}: {cid} отозвано, но используется")
                    continue
                if st == "superseded":
                    rep["warnings"].append(f"{doc.name}: {cid} заменено на {c.get('superseded_by')}")
                actual = "hypothesis" if cid in down_ids and c.get("kind") == "fact" else c.get("kind")
                if RU_KIND[label] == "fact" and actual != "fact":
                    rep["errors"].append(
                        f"{doc.name}: {cid} помечено как факт, а по claims это {core.KIND_RU.get(actual, actual)} — исправь формулировку и метку")

    active = [c for c in claims if c.get("status", "active") == "active"]
    rep["stats"] = {k: sum(1 for c in active if c.get("kind") == k) for k in ("fact", "hypothesis", "forecast", "synthetic")}
    rep["stats"]["downgraded_now"] = len(rep["downgrade"])
    rep["stats"]["human_verified"] = len(rep["human"])
    return rep


def apply_fix(proj: Path, rep: dict) -> int:
    if not rep["downgrade"]:
        return 0
    path = proj / "state" / "claims.jsonl"
    claims = core.read_jsonl(path)
    dmap = {d[0]: d for d in rep["downgrade"]}
    n = 0
    for c in claims:
        d = dmap.get(c.get("id"))
        if d and c.get("kind") == "fact":
            c["kind"] = "hypothesis"
            c["downgraded"] = {"from": "fact", "reason": d[1], "detail": d[2], "at": core.now_iso()}
            n += 1
    core.write_jsonl(path, claims)
    if n:
        core.append_journal(proj, f"verify_claims: понижено до гипотезы {n} утвержд.: " + ", ".join(dmap))
    return n


def render(rep: dict, fixed: bool) -> str:
    s = rep["stats"]
    lines = [
        "Протокол доказательств: "
        f"фактов {s.get('fact', 0)}, гипотез {s.get('hypothesis', 0)}, прогнозов {s.get('forecast', 0)}, "
        f"синтетики {s.get('synthetic', 0)}; проверено автоматически {len(rep['ok'])}, человеком {len(rep['human'])}"
    ]
    for cid, _, detail in rep["downgrade"]:
        verb = "понижен до гипотезы" if fixed else "будет понижен до гипотезы (--fix)"
        lines.append(f"  ↓ {cid} {verb}: {detail}")
    for e in rep["errors"]:
        lines.append(f"  ✗ {e}")
    for w in rep["warnings"]:
        lines.append(f"  ! {w}")
    for cid, mids in rep.get("weak_hypotheses", []):
        lines.append(f"  · {cid} остаётся гипотезой: все источники — форум, блог, отзывы или реклама ({', '.join(mids)}); "
                     "фактом станет только с первичным источником или СМИ")
    if not rep["downgrade"] and not rep["errors"]:
        lines.append("  ✓ все факты подтверждены снимками, метки в документах согласованы")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("--project", default=None)
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    rep = check(proj)
    if args.fix:
        apply_fix(proj, rep)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(render(rep, args.fix))
    return 1 if rep["downgrade"] or rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
