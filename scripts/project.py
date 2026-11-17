#!/usr/bin/env python3
"""Задачи агента-стратега: создать, выбрать, показать сводку, сменить этап, записать в журнал.

Примеры:
  python3 scripts/project.py new retention-q4 "Почему падает удержание подписки"
  python3 scripts/project.py status            # сводка «где остановились, что дальше»
  python3 scripts/project.py stage research --note "постановка подтверждена"
  python3 scripts/project.py set next_step "собрать отчётность за 2025"
  python3 scripts/project.py wait "Какой вариант берём: B или C?"   # ждём решения РП
  python3 scripts/project.py log "РП уточнил: получатель — CPO"
  python3 scripts/project.py list | use <slug>
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

NEXT_HINT = {
    "intake": "уточнить вопрос, цель, получателя, ограничения и данные (скилл intake)",
    "research": "план исследования от вопросов, меняющих решение; собрать снимки и claims (скилл research)",
    "options": "≥3 содержательно разных варианта с возражениями, РП выбирает (скилл options)",
    "strategy": "реестр свойств, продуктовая и коммуникационная стратегии (скилл strategy)",
    "validation": "план проверки и запись решения с kill-критериями (скилл validation)",
    "done": "задача завершена; при новых данных — скилл revisit",
}


def cmd_new(args) -> int:
    root = core.repo_root()
    slug = args.slug
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{1,60}", slug):
        print("slug: латиница в нижнем регистре, цифры и дефисы, например retention-q4", file=sys.stderr)
        return 2
    dst = core.projects_dir(root) / slug
    if dst.exists():
        print(f"Задача {slug} уже есть: {dst}", file=sys.stderr)
        return 2
    shutil.copytree(core.projects_dir(root) / "_template", dst)
    task = core.load_task(dst)
    task.update({
        "slug": slug,
        "title": args.title,
        "stage": "intake",
        "created_at": core.now_iso(),
        "updated_at": core.now_iso(),
        "next_step": NEXT_HINT["intake"],
    })
    core.write_json(dst / "state" / "task.json", task)
    core.append_journal(dst, f"Создана задача «{args.title}»")
    (core.projects_dir(root) / ".active").write_text(slug + "\n", encoding="utf-8")
    print(f"Создана задача {slug}: {dst.relative_to(root)}. Она активна. Этап: intake.")
    return 0


def cmd_use(args) -> int:
    root = core.repo_root()
    if not (core.projects_dir(root) / args.slug / "state").is_dir():
        print(f"Нет задачи {args.slug}", file=sys.stderr)
        return 2
    (core.projects_dir(root) / ".active").write_text(args.slug + "\n", encoding="utf-8")
    print(f"Активная задача: {args.slug}")
    return 0


def cmd_list(args) -> int:
    root = core.repo_root()
    act = core.active_slug(root)
    for d in sorted(core.projects_dir(root).iterdir()):
        if d.is_dir() and not d.name.startswith((".", "_")) and (d / "state" / "task.json").exists():
            t = core.load_task(d)
            mark = "*" if d.name == act else " "
            print(f"{mark} {d.name:32} {t.get('stage', '?'):10} {t.get('title', '')}")
    return 0


def claims_summary(proj: Path) -> str:
    try:
        claims = core.read_jsonl(proj / "state" / "claims.jsonl")
    except ValueError as e:
        return f"claims.jsonl повреждён: {e}"
    active = [c for c in claims if c.get("status", "active") == "active"]
    if not claims:
        return "claims: пока нет"
    cnt = {k: sum(1 for c in active if c.get("kind") == k) for k in core.CLAIM_KINDS}
    down = sum(1 for c in active if c.get("downgraded"))
    old = len(claims) - len(active)
    parts = [f"{core.KIND_RU[k]} {cnt[k]}" for k in ("fact", "hypothesis", "forecast", "synthetic") if cnt[k]]
    s = "claims: " + ", ".join(parts)
    if down:
        s += f"; понижено проверкой: {down}"
    if old:
        s += f"; отозвано/заменено: {old}"
    return s


def status_text(proj: Path, short: bool = False) -> str:
    t = core.load_task(proj)
    stage = t.get("stage", "intake")
    idx = core.STAGES.index(stage) + 1 if stage in core.STAGES else "?"
    lines = [
        f"Задача: {t.get('title', proj.name)} ({proj.name})",
        f"Этап: {idx}/5 {stage} — {core.STAGE_TITLES.get(stage, '')}" if stage != "done" else "Этап: done — задача завершена",
    ]
    if t.get("waiting_for"):
        lines.append(f"ЖДЁТ РЕШЕНИЯ РП: {t['waiting_for']}")
    lines.append(f"Дальше: {t.get('next_step') or NEXT_HINT.get(stage, '')}")
    if short:
        return "\n".join(lines)
    for key, label in (("question", "Вопрос"), ("goal", "Цель"), ("recipient", "Получатель")):
        if t.get(key):
            lines.append(f"{label}: {t[key]}")
    mats = core.list_materials(proj)
    lines.append(f"Материалы: {len(mats)} снимков; {claims_summary(proj)}")
    outs = sorted(p.name for p in (proj / "out").glob("*.md") if p.name != "README.md") if (proj / "out").is_dir() else []
    if outs:
        lines.append("Готово в out/: " + ", ".join(outs))
    try:
        import revisit  # noqa: WPS433 (Should-фича, может отсутствовать)

        flags = revisit.check(proj)
        for f in flags[:5]:
            lines.append(f"ПЕРЕСМОТР: {f}")
    except Exception:  # noqa: BLE001 — сводка не должна падать из-за доп. модуля
        pass
    total = core.ledger_total(proj)
    if total:
        lines.append(f"Потрачено: ${total:.2f} (оценка по прейскуранту API, state/cost-ledger.csv)")
    j = proj / "state" / "journal.md"
    if j.exists():
        tail = [ln for ln in j.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")][-3:]
        if tail:
            lines.append("Последние записи журнала:")
            lines.extend("  " + ln for ln in tail)
    return "\n".join(lines)


def cmd_status(args) -> int:
    proj = core.project_path(args.slug)
    if not proj:
        print("Активной задачи нет. Создай: python3 scripts/project.py new <slug> \"<название>\"")
        return 0
    print(status_text(proj, short=args.short))
    return 0


def _proj_or_fail(slug):
    proj = core.project_path(slug)
    if not proj:
        print("Нет активной задачи (projects/.active). Сначала new или use.", file=sys.stderr)
        sys.exit(2)
    return proj


def cmd_stage(args) -> int:
    if args.stage not in core.STAGES:
        print(f"Этап должен быть одним из: {', '.join(core.STAGES)}", file=sys.stderr)
        return 2
    proj = _proj_or_fail(args.slug)
    t = core.load_task(proj)
    prev = t.get("stage")
    done = t.setdefault("stages_done", [])
    if prev and prev != args.stage and prev not in done and core.STAGES.index(args.stage) > core.STAGES.index(prev):
        done.append(prev)
    t["stage"] = args.stage
    t["next_step"] = args.next or NEXT_HINT[args.stage]
    t["updated_at"] = core.now_iso()
    t.pop("waiting_for", None)
    core.write_json(proj / "state" / "task.json", t)
    core.append_journal(proj, f"Этап {prev} → {args.stage}" + (f": {args.note}" if args.note else ""))
    print(f"Этап: {args.stage}. Дальше: {t['next_step']}")
    return 0


def cmd_set(args) -> int:
    allowed = {"title", "question", "goal", "recipient", "deadline", "constraints", "data", "next_step", "decision_owner"}
    if args.key not in allowed:
        print(f"Можно задать: {', '.join(sorted(allowed))}", file=sys.stderr)
        return 2
    proj = _proj_or_fail(args.slug)
    t = core.load_task(proj)
    t[args.key] = args.value
    t["updated_at"] = core.now_iso()
    core.write_json(proj / "state" / "task.json", t)
    print(f"{args.key} = {args.value}")
    return 0


def cmd_wait(args) -> int:
    proj = _proj_or_fail(args.slug)
    t = core.load_task(proj)
    t["waiting_for"] = args.question
    t["updated_at"] = core.now_iso()
    core.write_json(proj / "state" / "task.json", t)
    core.append_journal(proj, f"Вопрос РП: {args.question}")
    print("Записано: ждём решения РП.")
    return 0


def cmd_log(args) -> int:
    proj = _proj_or_fail(args.slug)
    core.append_journal(proj, args.text)
    print("Записано в журнал.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", dest="slug", default=None, help="slug задачи (по умолчанию активная)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("slug"); p.add_argument("title"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("use"); p.add_argument("slug"); p.set_defaults(fn=cmd_use)
    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("status"); p.add_argument("--short", action="store_true"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("stage"); p.add_argument("stage"); p.add_argument("--note"); p.add_argument("--next"); p.set_defaults(fn=cmd_stage)
    p = sub.add_parser("set"); p.add_argument("key"); p.add_argument("value"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("wait"); p.add_argument("question"); p.set_defaults(fn=cmd_wait)
    p = sub.add_parser("log"); p.add_argument("text"); p.set_defaults(fn=cmd_log)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
