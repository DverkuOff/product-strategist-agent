#!/usr/bin/env python3
"""Утверждения задачи (state/claims.jsonl): добавить, показать, заменить, отозвать.

Добавить (JSON-объект или массив на stdin; id назначается автоматически):
  echo '{"text": "...", "kind": "fact", "sources": [{"material": "M-01", "quote": "..."}]}' \
    | python3 scripts/claims.py add
Показать:   python3 scripts/claims.py list [--kind fact] [--all]
Заменить:   python3 scripts/claims.py supersede C-003 --by C-015 --reason "новые данные ЦБ"
Отозвать:   python3 scripts/claims.py retract C-004 --reason "источник недостоверен"
Проверено человеком (только РП: Claude Code спросит разрешение):
  python3 scripts/claims.py human-verified C-006 --note "сверил в личном кабинете 17.11"

Формат и правила: .claude/skills/research/claims-format.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ALLOWED_FIELDS = {"text", "kind", "sources", "origin", "confidence", "note", "basis", "contradicts", "supports",
                  "question", "valid_until"}
# verified, downgraded и status ставят только скрипты: «проверено человеком» — запись РП в state/human.jsonl


def _path(proj: Path) -> Path:
    return proj / "state" / "claims.jsonl"


def next_id(claims: list[dict]) -> str:
    nums = [int(m.group(1)) for c in claims if (m := re.fullmatch(r"C-(\d+)", str(c.get("id", ""))))]
    return f"C-{(max(nums) + 1) if nums else 1:03d}"


def validate_new(c: dict) -> list[str]:
    errs = []
    if not str(c.get("text", "")).strip():
        errs.append("нет text")
    kind = c.get("kind")
    if kind not in core.CLAIM_KINDS:
        errs.append(f"kind должен быть одним из {sorted(core.CLAIM_KINDS)}")
    if kind == "synthetic" and c.get("origin") not in (None, "synthetic"):
        errs.append("synthetic-утверждение должно иметь origin: synthetic")
    for s in c.get("sources", []) or []:
        if not isinstance(s, dict) or not (s.get("material") or s.get("url")):
            errs.append("каждый source — объект с material (M-xx) или url")
    unknown = set(c) - ALLOWED_FIELDS - {"id", "status", "created_at"}
    if unknown:
        errs.append(f"неизвестные поля: {sorted(unknown)}")
    return errs


def cmd_add(proj: Path, args) -> int:
    raw = sys.stdin.read() if not args.json else args.json
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Не JSON: {e}", file=sys.stderr)
        return 2
    items = data if isinstance(data, list) else [data]
    claims = core.read_jsonl(_path(proj))
    added = []
    for item in items:
        errs = validate_new(item)
        if errs:
            print(f"Пропущено «{str(item.get('text', ''))[:60]}»: {'; '.join(errs)}", file=sys.stderr)
            continue
        c = {"id": next_id(claims), **{k: v for k, v in item.items() if k != "id"}}
        c.setdefault("origin", "synthetic" if c["kind"] == "synthetic" else ("source" if c.get("sources") else "agent"))
        c.setdefault("sources", [])
        c["status"] = "active"
        c["created_at"] = core.now_iso()
        claims.append(c)
        added.append(c["id"])
    core.write_jsonl(_path(proj), claims)
    print(f"Добавлено: {', '.join(added) if added else 'ничего'}")
    return 0 if added or not items else 1


def cmd_list(proj: Path, args) -> int:
    for c in core.read_jsonl(_path(proj)):
        if not args.all and c.get("status", "active") != "active":
            continue
        if args.kind and c.get("kind") != args.kind:
            continue
        src = ",".join(s.get("material") or s.get("url", "?") for s in c.get("sources", []))
        flag = " ↓" if c.get("downgraded") else ""
        st = "" if c.get("status", "active") == "active" else f" [{c['status']}]"
        print(f"{c['id']} {core.KIND_RU.get(c.get('kind'), c.get('kind'))}{flag}{st}: {c.get('text')} ({src or 'без источника'})")
    return 0


def _update(proj: Path, cid: str, fn) -> int:
    claims = core.read_jsonl(_path(proj))
    for c in claims:
        if c.get("id") == cid:
            fn(c)
            core.write_jsonl(_path(proj), claims)
            return 0
    print(f"Нет утверждения {cid}", file=sys.stderr)
    return 2


def cmd_supersede(proj: Path, args) -> int:
    ids = {c.get("id") for c in core.read_jsonl(_path(proj))}
    if args.by not in ids:
        print(f"Сначала добавь новое утверждение {args.by}", file=sys.stderr)
        return 2

    def fn(c):
        c.update(status="superseded", superseded_by=args.by, status_reason=args.reason, status_at=core.now_iso())

    rc = _update(proj, args.id, fn)
    if rc == 0:
        core.append_journal(proj, f"{args.id} заменено на {args.by}: {args.reason}")
        print(f"{args.id} → superseded ({args.by})")
    return rc


def cmd_retract(proj: Path, args) -> int:
    rc = _update(proj, args.id, lambda c: c.update(status="retracted", status_reason=args.reason, status_at=core.now_iso()))
    if rc == 0:
        core.append_journal(proj, f"{args.id} отозвано: {args.reason}")
        print(f"{args.id} → retracted")
    return rc


def cmd_human(proj: Path, args) -> int:
    """Подтверждение РП. Claude Code спрашивает разрешение на эту команду (permissions.ask), поэтому
    агент не может выполнить её сам; запись идёт в state/human.jsonl с хэшем текста утверждения."""
    claims = {c.get("id"): c for c in core.read_jsonl(_path(proj))}
    c = claims.get(args.id)
    if not c:
        print(f"Нет утверждения {args.id}", file=sys.stderr)
        return 2
    if not (c.get("sources")):
        print(f"{args.id}: нет источника (url или M-xx) — подтверждать нечего", file=sys.stderr)
        return 2
    core.human_add(proj, {"type": "claim_verified", "claim": args.id, "text_sha": core.text_sha(c.get("text", "")),
                          "note": args.note})

    def fn(x):
        x["verified"] = "human"  # для показа; проверка верит только state/human.jsonl
        x["verified_note"] = args.note
        x["verified_at"] = core.now_iso()
        if x.get("downgraded") and x["downgraded"].get("from") == "fact":
            x["kind"] = "fact"
            x.pop("downgraded")

    _update(proj, args.id, fn)
    core.append_journal(proj, f"{args.id} проверено человеком: {args.note}")
    print(f"{args.id}: проверено человеком (state/human.jsonl)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add"); p.add_argument("--json", default=None); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("list"); p.add_argument("--kind"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("supersede"); p.add_argument("id"); p.add_argument("--by", required=True); p.add_argument("--reason", required=True); p.set_defaults(fn=cmd_supersede)
    p = sub.add_parser("retract"); p.add_argument("id"); p.add_argument("--reason", required=True); p.set_defaults(fn=cmd_retract)
    p = sub.add_parser("human-verified"); p.add_argument("id"); p.add_argument("--note", required=True); p.set_defaults(fn=cmd_human)
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    return args.fn(proj, args)


if __name__ == "__main__":
    sys.exit(main())
