#!/usr/bin/env python3
"""Журнал исследования out/research-log.md: что искали, что открыли, что отбросили и почему.

  python3 scripts/research_log.py query "МегаФон Защита близких цена" --result "3 релевантных из 10, взяты M-02, M-06"
  python3 scripts/research_log.py discard "https://…/forum" --result "анонимный форум, нет первоисточника"
  python3 scripts/research_log.py note "цены на сайте оператора нет — пробел Q3"
Открытые и неоткрывшиеся источники записывает scripts/fetch_source.py сам.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("--project", default=None)
    ap.add_argument("action", choices=["query", "discard", "note", "open"])
    ap.add_argument("what")
    ap.add_argument("--result", default="")
    args = ap.parse_args(argv)
    proj = core.project_path(args.project)
    if not proj:
        print("Нет активной задачи", file=sys.stderr)
        return 2
    core.log_research(proj, args.action, args.what, args.result)
    print("Записано в out/research-log.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
