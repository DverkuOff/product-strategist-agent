---
name: revise
description: Точечная правка результата по просьбе РП («исправь раздел X», «поправь обещание», «убери вариант C»). Меняется только один раздел одного документа out/, остальное не перегенерируется; что и почему изменено, пишется в state/journal.md и state/revisions/log.md с diff.
when_to_use: «исправь», «поправь раздел», «перепиши только», «не так в …», замечание РП к готовому документу
allowed-tools: Bash(python3 scripts/project.py status*) Bash(python3 scripts/project.py stage *) Bash(python3 scripts/project.py set *) Bash(python3 scripts/project.py wait *) Bash(python3 scripts/project.py log *) Bash(python3 scripts/project.py new *) Bash(python3 scripts/project.py list*) Bash(python3 scripts/project.py use *) Bash(python3 scripts/claims.py add*) Bash(python3 scripts/claims.py list*) Bash(python3 scripts/claims.py supersede *) Bash(python3 scripts/claims.py retract *) Bash(python3 scripts/fetch_source.py http*) Bash(python3 scripts/fetch_source.py projects/*) Bash(python3 scripts/verify_claims.py*) Bash(python3 scripts/promise_lint.py*) Bash(python3 scripts/decision_lint.py*) Bash(python3 scripts/compare.py*) Bash(python3 scripts/revisit.py*) Bash(python3 scripts/cost_report.py*) Bash(python3 scripts/estimate.py *) Bash(python3 scripts/research_log.py *) Bash(python3 scripts/revise.py *) Read Edit Grep
---

# Точечная правка (вместо перегенерации)

Идея: правка вместо перегенерации этапа (github/spec-kit) и отслеживаемые изменения (Productboard).

1. Пойми, какой документ и какой раздел (заголовок) РП просит изменить. Если неясно — один вопрос с вариантами.
2. `python3 scripts/revise.py start out/<документ>.md --section "<заголовок раздела>"` — копия документа сохранится.
3. Измени **только этот раздел** (Edit). Не переписывай соседние разделы и не «улучшай заодно».
4. Если правка затрагивает факты или обещания — обнови `state/claims.jsonl` (`claims.py supersede/retract`) или `state/product-properties.json` — это не раздел документа и проверкой не считается.
5. `python3 scripts/revise.py finish --reason "<слова РП или причина>"`. Если скрипт нашёл изменения вне раздела — откати их; осознанно менять несколько разделов можно только с `--allow-other` и объяснением в `--reason`.
6. Ворота: `python3 scripts/verify_claims.py --fix`, `python3 scripts/promise_lint.py`, `python3 scripts/decision_lint.py`.
7. Если правка тянет последствия в других документах (поменялось обещание → план проверки; поменялся выбранный вариант → стратегия), **не правь их молча**: перечисли РП, что ещё затронуто, и спроси, править ли (каждое — отдельной точечной правкой).
8. Скажи РП одной-двумя строками: что изменено, где, сколько строк, что ещё затронуто.
