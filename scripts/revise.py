#!/usr/bin/env python3
"""Точечная правка: меняется только один раздел документа out/, изменение записывается в журнал.

  python3 scripts/revise.py start out/comms-strategy.md --section "Ключевые обещания"
  # … правка только этого раздела (Edit) …
  python3 scripts/revise.py finish --reason "РП: не обещать «до 50 номеров», это не главное"

start сохраняет копию документа в state/revisions/; finish сравнивает разделы (по заголовкам Markdown):
если изменился не только выбранный раздел — код 1 и список «правок вне раздела» (откати их или
повтори start для нужного раздела; --allow-other — осознанно принять). Итог пишется в state/journal.md
и state/revisions/log.md (с diff). Идея: правка вместо перегенерации (spec-kit), отслеживаемые
изменения (Productboard).
"""
from __future__ import annotations

import argparse
import difflib
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

HEAD = re.compile(r"^(#{1,6})\s+(.*)$")


def sections(md: str) -> dict[str, str]:
    """Заголовок → текст раздела (до следующего заголовка любого уровня). Текст до первого заголовка — «(начало)»."""
    out: dict[str, str] = {}
    key, buf = "(начало)", []
    for line in md.splitlines():
        m = HEAD.match(line)
        if m:
            out[key] = "\n".join(buf).strip()
            key, buf = m.group(2).strip(), []
            n, base = 2, key
            while key in out:  # одинаковые заголовки
                key = f"{base} #{n}"
                n += 1
        else:
            buf.append(line)
    out[key] = "\n".join(buf).strip()
    return out


def match_section(name: str, keys) -> str | None:
    name_l = name.lower().strip()
    exact = [k for k in keys if k.lower() == name_l]
    if exact:
        return exact[0]
    part = [k for k in keys if name_l in k.lower()]
    return part[0] if len(part) == 1 else None


def changed_sections(old: str, new: str) -> list[str]:
    a, b = sections(old), sections(new)
    return [k for k in dict.fromkeys([*a, *b]) if a.get(k) != b.get(k)]


def pending_path(proj: Path) -> Path:
    return proj / "state" / "revisions" / "pending.json"


def cmd_start(proj: Path, args) -> int:
    doc = (proj / args.doc) if not Path(args.doc).is_absolute() else Path(args.doc)
    if not doc.exists():
        print(f"Нет документа {args.doc}", file=sys.stderr)
        return 2
    key = match_section(args.section, sections(doc.read_text(encoding="utf-8")))
    if not key:
        print(f"Раздел «{args.section}» не найден или неоднозначен. Разделы: " + "; ".join(sections(doc.read_text(encoding='utf-8'))), file=sys.stderr)
        return 2
    rdir = proj / "state" / "revisions"
    rdir.mkdir(parents=True, exist_ok=True)
    stamp = core.now_iso().replace(":", "")[:17]
    copy = rdir / f"{doc.stem}.{stamp}.md"
    shutil.copyfile(doc, copy)
    core.write_json(pending_path(proj), {"doc": str(doc.relative_to(proj)), "section": key, "copy": copy.name, "started_at": core.now_iso()})
    print(f"Правка начата: {doc.relative_to(proj)}, раздел «{key}». Меняй только его, затем revise.py finish --reason \"…\"")
    return 0


def cmd_finish(proj: Path, args) -> int:
    pend = core.read_json(pending_path(proj), None)
    if not pend:
        print("Нет начатой правки: сначала revise.py start", file=sys.stderr)
        return 2
    doc = proj / pend["doc"]
    old = (proj / "state" / "revisions" / pend["copy"]).read_text(encoding="utf-8")
    new = doc.read_text(encoding="utf-8")
    changed = changed_sections(old, new)
    other = [k for k in changed if k != pend["section"]]
    if other and not args.allow_other:
        print("Изменено вне выбранного раздела «" + pend["section"] + "»: " + "; ".join(f"«{k}»" for k in other)
              + ". Откати эти правки или подтверди --allow-other (и объясни в --reason).", file=sys.stderr)
        return 1
    if not changed:
        print("Документ не изменился — правка не записана.")
        pending_path(proj).unlink()
        return 0
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=1))
    plus = sum(1 for d in diff if d.startswith("+") and not d.startswith("+++"))
    minus = sum(1 for d in diff if d.startswith("-") and not d.startswith("---"))
    what = ", ".join(f"«{k}»" for k in changed)
    core.append_journal(proj, f"Правка {pend['doc']}, раздел {what}: +{plus}/−{minus} строк. Причина: {args.reason}")
    with (proj / "state" / "revisions" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {core.now_iso()} · {pend['doc']} · {what}\nПричина: {args.reason}\n\n```diff\n" + "\n".join(diff[2:]) + "\n```\n")
    pending_path(proj).unlink()
    print(f"Записано: {pend['doc']}, {what}, +{plus}/−{minus}. Проверь ворота: verify_claims, promise_lint, decision_lint.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start"); p.add_argument("doc"); p.add_argument("--section", required=True); p.set_defaults(fn=cmd_start)
    p = sub.add_parser("finish"); p.add_argument("--reason", required=True); p.add_argument("--allow-other", action="store_true"); p.set_defaults(fn=cmd_finish)
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    return args.fn(proj, args)


if __name__ == "__main__":
    sys.exit(main())
