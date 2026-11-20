---
name: revisit
description: Пересмотр решений при новых данных («Живая стратегия»-lite). Находит решения в state/decisions.md, чьи основания (ID утверждений) понижены проверкой, отозваны, заменены или оспорены новыми утверждениями (поле contradicts), и предлагает РП пересмотр (оставить, изменить или отменить). Используй, когда пришли новые материалы или наступила дата пересмотра.
when_to_use: «пришли новые данные», «результаты пилота», «пересмотри решение», флаг ПЕРЕСМОТР в сводке SessionStart
allowed-tools: Bash(python3 scripts/project.py status*) Bash(python3 scripts/project.py stage *) Bash(python3 scripts/project.py set *) Bash(python3 scripts/project.py wait *) Bash(python3 scripts/project.py log *) Bash(python3 scripts/project.py new *) Bash(python3 scripts/project.py list*) Bash(python3 scripts/project.py use *) Bash(python3 scripts/claims.py add*) Bash(python3 scripts/claims.py list*) Bash(python3 scripts/claims.py supersede *) Bash(python3 scripts/claims.py retract *) Bash(python3 scripts/fetch_source.py http*) Bash(python3 scripts/fetch_source.py projects/*) Bash(python3 scripts/verify_claims.py*) Bash(python3 scripts/promise_lint.py*) Bash(python3 scripts/decision_lint.py*) Bash(python3 scripts/compare.py*) Bash(python3 scripts/revisit.py*) Bash(python3 scripts/cost_report.py*) Bash(python3 scripts/estimate.py *) Bash(python3 scripts/research_log.py *) Bash(python3 scripts/revise.py *) Read Write Edit Grep
---

# Пересмотр решений при новых данных

1. Новые материалы — снимками (`fetch_source.py`), чтение — через `source-reader`, утверждения — `claims.py add`. Если новое утверждение противоречит старому, укажи `"contradicts": ["C-…"]`; если заменяет — `claims.py supersede`.
2. `python3 scripts/verify_claims.py --fix`, затем `python3 scripts/revisit.py` — список решений, у которых изменились основания, и просроченные даты пересмотра.
3. Для каждого флага: что изменилось, какие выводы затронуты (только они — остальное не переписываем), сработал ли kill-критерий. Предложи: оставить / изменить / отменить — с опорой.
4. **Точка человека:** решение о пересмотре принимает РП (`project.py wait "…"`). После ответа обнови статус решения в `state/decisions.md`, добавь строку «Пересмотр ГГГГ-ММ-ДД: …», при необходимости точечно поправь `out/` и запиши в журнал.
