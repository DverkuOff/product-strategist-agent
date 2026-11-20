---
name: compare
description: Сравнение с исходным способом — ответ обычного чата на тот же запрос прогоняется через те же детерминированные проверки, что и результат агента (рискованные формулировки, обещания без опоры, числа, которых нет в материалах, наличие обязательных блоков), плюс время и стоимость. Используй после того, как стратегия готова, или когда РП спрашивает «а чем это лучше чата».
when_to_use: «сравни с обычным чатом», «чем лучше ChatGPT», «сколько сэкономили»
allowed-tools: Bash(python3 scripts/project.py status*) Bash(python3 scripts/project.py stage *) Bash(python3 scripts/project.py set *) Bash(python3 scripts/project.py wait *) Bash(python3 scripts/project.py log *) Bash(python3 scripts/project.py new *) Bash(python3 scripts/project.py list*) Bash(python3 scripts/project.py use *) Bash(python3 scripts/claims.py add*) Bash(python3 scripts/claims.py list*) Bash(python3 scripts/claims.py supersede *) Bash(python3 scripts/claims.py retract *) Bash(python3 scripts/fetch_source.py http*) Bash(python3 scripts/fetch_source.py projects/*) Bash(python3 scripts/verify_claims.py*) Bash(python3 scripts/promise_lint.py*) Bash(python3 scripts/decision_lint.py*) Bash(python3 scripts/compare.py*) Bash(python3 scripts/revisit.py*) Bash(python3 scripts/cost_report.py*) Bash(python3 scripts/estimate.py *) Bash(python3 scripts/research_log.py *) Bash(python3 scripts/revise.py *) Read Write Edit
---

# Сравнение с обычным чатом

1. Нужен ответ обычного чата на **тот же** исходный запрос РП, без инструментов и материалов задачи: `projects/<задача>/baseline/chat-answer.md`, и `baseline/meta.json` — модель, дата, время, стоимость, как получен. Если файла нет — попроси РП вставить ответ его привычного чата или получи его сам одним вызовом модели без инструментов и честно запиши в meta.json, как получен.
2. `python3 scripts/compare.py` — таблица «агент / обычный чат» (Markdown) в `out/compare.md`:
   - обещания без опоры на свойство продукта и рискованные формулировки (ст. 5 38-ФЗ);
   - числа, которых нет ни в одном снимке материалов задачи (непроверяемые цифры);
   - разметка факт/гипотеза/прогноз, источник у утверждений;
   - обязательные блоки брифа: ≥3 варианта и «оставить как есть», возражения, план проверки (контроль, срок, guardrails);
   - время и стоимость (агент — `state/cost-ledger.csv`, чат — `meta.json`).
3. Объясни РП разницу в 3–5 строках и **цену** разницы (сколько дороже/дольше агент). Не преувеличивай: что проверки не ловят (смысловую точность), так и скажи.
