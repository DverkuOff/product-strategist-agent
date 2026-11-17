#!/usr/bin/env python3
"""«Протокол доказательств»-lite: проверка утверждений задачи без LLM.

Правила для каждого активного утверждения со статусом fact:
  1. есть источник (sources) — иначе понижение до гипотезы («прежний ответ агента не факт»);
  2. источник — сохранённый снимок M-xx в materials/ — иначе понижение;
  3. снимок не синтетический (kind: synthetic) и само утверждение не synthetic — иначе понижение;
  4. все числа и имена собственные из текста есть в снимке — в окрестности цитаты (±700 знаков) или
     в атрибуции снимка (title, publisher, published); без цитаты — во всём снимке (слабее) — иначе понижение;
  5. verified: human — «недоступно автоматически, проверено человеком»: автоматическую проверку
     пропускаем, но источник (url или материал) обязателен.
Семантику («подтверждает ли источник вывод») скрипт не проверяет — это осознанное ограничение.

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


def missing_in_snapshot(text: str, snapshot: str, full: str | None = None) -> list[str]:
    """Числа и имена собственные из text, которых нет в snapshot (окрестности цитаты).

    Слово в начале предложения может быть и именем («Билайн предлагает…»), и обычным словом
    («Обзор сообщает…»), поэтому его ищем во всём снимке full: так ловим чужие бренды и не
    понижаем факт из-за обычного слова.
    """
    text = ID_RE.sub(" ", text)
    snap_norm = core.norm_text(snapshot)
    full_norm = core.norm_text(full) if full is not None else snap_norm
    snap_nums = core.numbers_in(snapshot)
    first = core.sentence_initial_words(text)
    missing = []
    for n in core.extract_numbers(text):
        if n not in snap_nums:
            missing.append(n)
    for w in core.extract_proper_nouns(text):
        where = full_norm if w in first else snap_norm
        if core.stem(w) not in where:
            missing.append(w)
    # без дублей, порядок сохраняем
    return list(dict.fromkeys(missing))


WINDOW = 700  # символов вокруг цитаты: на новостной странице много посторонних чисел и имён


def evidence_window(body: str, quote: str | None, cid: str, mid: str, rep: dict) -> str:
    """Где искать числа и имена: окрестность цитаты, если она нашлась, иначе весь снимок (с предупреждением)."""
    nb = core.norm_text(body)
    if quote:
        nq = core.norm_text(quote).strip()
        key = nq[:120]
        i = nb.find(key) if key else -1
        if i >= 0:
            return nb[max(0, i - WINDOW): i + len(nq) + WINDOW]
        rep["warnings"].append(f"{cid}: цитата не найдена дословно в {mid} — числа и имена проверены по всему снимку")
    else:
        rep["warnings"].append(f"{cid}: у источника {mid} нет цитаты — числа и имена проверены по всему снимку (слабее)")
    return nb


def check(proj: Path) -> dict:
    rep = {"errors": [], "warnings": [], "downgrade": [], "human": [], "ok": [], "stats": {}}
    try:
        claims = core.read_jsonl(proj / "state" / "claims.jsonl")
    except ValueError as e:
        rep["errors"].append(str(e))
        return rep
    mats = core.list_materials(proj)
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
            if kind == "forecast" and not (c.get("basis") or c.get("sources")):
                rep["warnings"].append(f"{cid}: прогноз без оснований (basis: [C-...] или sources)")
            continue
        sources = c.get("sources") or []
        if c.get("verified") == "human":
            if not sources:
                rep["downgrade"].append((cid, "no_source", "проверено человеком, но источник не указан"))
            else:
                rep["human"].append(cid)
            continue
        if not sources:
            reason = "прежний вывод агента без источника" if c.get("origin") == "agent" else "нет источника"
            rep["downgrade"].append((cid, "no_source", reason))
            continue
        snaps, fulls = [], []
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
            if core.material_is_synthetic(mat):
                bad = ("synthetic", f"{mid} — синтетический материал, не основание факта")
                continue
            meta = mat.get("meta", {})
            attribution = " ".join(str(meta.get(k, "")) for k in ("title", "publisher", "published"))
            snaps.append(evidence_window(mat["body"], s.get("quote"), cid, mid, rep) + " " + core.norm_text(attribution))
            fulls.append(mat["body"] + " " + attribution)
        if not snaps:
            rep["downgrade"].append((cid, *(bad or ("no_snapshot", "нет пригодного снимка"))))
            continue
        miss = missing_in_snapshot(c.get("text", ""), "\n".join(snaps), "\n".join(fulls))
        if miss:
            rep["downgrade"].append((cid, "not_in_snapshot", "нет в снимке: " + ", ".join(miss)))
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
    if not rep["downgrade"] and not rep["errors"]:
        lines.append("  ✓ все факты подтверждены снимками, метки в документах согласованы")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
