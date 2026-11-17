#!/usr/bin/env python3
"""«Живая стратегия»-lite: какие решения пора пересмотреть из-за новых данных. Без LLM.

Решения — в state/decisions.md (разделы «## D-001 · …» с полями «Статус», «Основания: C-…»,
«Kill-критерии», «Пересмотреть до: ГГГГ-ММ-ДД»). Флаг ставится, если у действующего решения:
  - основание отсутствует, отозвано (retracted) или заменено (superseded);
  - основание-факт понижено проверкой до гипотезы (verify_claims);
  - появилось утверждение-факт, которое ему противоречит (поле contradicts);
  - наступила дата пересмотра.
Противоречие от гипотезы (например, слух с форума) флага не даёт: шум не должен переоткрывать решения.

  python3 scripts/revisit.py [--project <slug|путь>]
Код выхода: 0 — пересматривать нечего; 1 — есть флаги.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

HEAD = re.compile(r"^##\s+(D-\d+)\s*[·\-—:]?\s*(.*)$")
FIELD = re.compile(r"^\s*[-*]\s*([^:]+):\s*(.*)$")
ACTIVE = ("принято", "предложено", "accepted", "proposed")


def parse_decisions(text: str) -> list[dict]:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, cur = [], None
    for line in text.splitlines():
        m = HEAD.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2).strip(), "fields": {}}
            out.append(cur)
            continue
        if cur:
            f = FIELD.match(line)
            if f:
                cur["fields"][f.group(1).strip().lower()] = f.group(2).strip()
    for d in out:
        f = d["fields"]
        d["status"] = f.get("статус", "").lower()
        d["basis"] = re.findall(r"C-\d+", f.get("основания", ""))
        d["revisit_by"] = f.get("пересмотреть до", "")
    return out


def check(proj: Path, today: dt.date | None = None) -> list[str]:
    today = today or dt.date.today()
    path = proj / "state" / "decisions.md"
    if not path.exists():
        return []
    decisions = parse_decisions(path.read_text(encoding="utf-8"))
    claims = {c["id"]: c for c in core.read_jsonl(proj / "state" / "claims.jsonl") if "id" in c}
    flags = []
    for d in decisions:
        if not d["status"].startswith(ACTIVE):
            continue
        for cid in d["basis"]:
            c = claims.get(cid)
            if not c:
                flags.append(f"{d['id']}: основания {cid} нет в claims")
                continue
            st = c.get("status", "active")
            if st == "retracted":
                flags.append(f"{d['id']}: основание {cid} отозвано ({c.get('status_reason', '')})")
            elif st == "superseded":
                flags.append(f"{d['id']}: основание {cid} заменено на {c.get('superseded_by')} ({c.get('status_reason', '')})")
            elif c.get("downgraded"):
                flags.append(f"{d['id']}: основание {cid} понижено до гипотезы ({c['downgraded'].get('detail', '')})")
        for c in claims.values():
            if c.get("status", "active") != "active" or c.get("kind") != "fact":
                continue
            hit = [x for x in c.get("contradicts", []) or [] if x in d["basis"]]
            if hit:
                flags.append(f"{d['id']}: новое утверждение-факт {c['id']} противоречит основанию {', '.join(hit)}: «{c.get('text', '')[:80]}»")
        if d["revisit_by"]:
            try:
                due = dt.date.fromisoformat(d["revisit_by"][:10])
                if due <= today:
                    flags.append(f"{d['id']}: наступила дата пересмотра {due.isoformat()}")
            except ValueError:
                flags.append(f"{d['id']}: дата пересмотра не в формате ГГГГ-ММ-ДД: «{d['revisit_by']}»")
    return flags


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    flags = check(proj)
    if not flags:
        print("Пересмотр не нужен: основания решений не изменились, сроки пересмотра не наступили.")
        return 0
    print("Решения, которые стоит пересмотреть:")
    for f in flags:
        print(f"  ⟳ {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
