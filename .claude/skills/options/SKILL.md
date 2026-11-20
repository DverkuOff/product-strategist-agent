---
name: options
description: Этап 3 — варианты решения. Не меньше трёх содержательно разных вариантов, включая «оставить как есть» и рассмотрение «закрыть направление»; для каждого — что должно быть правдой (с опорой на утверждения и их статус), сильные возражения (pre-mortem), цена и обратимость. Заканчивается выбором РП. Используй после исследования.
when_to_use: этап options в state/task.json; «какие варианты», «что можно сделать»
model: opus
allowed-tools: Bash(python3 "${CLAUDE_PROJECT_DIR}/scripts/project.py" status *) Bash(python3 scripts/project.py status*) Bash(python3 scripts/project.py stage *) Bash(python3 scripts/project.py set *) Bash(python3 scripts/project.py wait *) Bash(python3 scripts/project.py log *) Bash(python3 scripts/project.py new *) Bash(python3 scripts/project.py list*) Bash(python3 scripts/project.py use *) Bash(python3 scripts/claims.py add*) Bash(python3 scripts/claims.py list*) Bash(python3 scripts/claims.py supersede *) Bash(python3 scripts/claims.py retract *) Bash(python3 scripts/fetch_source.py http*) Bash(python3 scripts/fetch_source.py projects/*) Bash(python3 scripts/verify_claims.py*) Bash(python3 scripts/promise_lint.py*) Bash(python3 scripts/decision_lint.py*) Bash(python3 scripts/compare.py*) Bash(python3 scripts/revisit.py*) Bash(python3 scripts/cost_report.py*) Bash(python3 scripts/estimate.py *) Bash(python3 scripts/research_log.py *) Bash(python3 scripts/revise.py *) Bash(python3 scripts/table_calc.py *) Bash(python3 -c *) Bash(python3 projects/*/out/calc-*.py) Bash(python3 projects/*/out/calc-*.py *) Read Write Edit Glob Grep
---

# Этап 3. Варианты

Текущее состояние: !`python3 "${CLAUDE_PROJECT_DIR}/scripts/project.py" status --short`

Методика: `methodology/playing-to-win.md`, `methodology/premortem.md`, `methodology/decision-records.md` (обратимость).
Опора: `out/research.md`, `python3 scripts/claims.py list`. Новых фактов на этом этапе не выдумывай: нужен факт — вернись в research.

## Шаги
1. Сформулируй 3–5 вариантов. Они различаются «где играем» (сегмент, канал) или «как выигрываем» (чем лучше альтернатив), а не силой одного действия. Обязательно:
   - **«Оставить как есть»** — обязательный блок **«Цена бездействия»**: базовая линия (что есть сейчас, `[факт C-…]`), что будет без изменений (`forecast` с основаниями) и чего это стоит. Бездействие — не бесплатный вариант (идея spec-kit assess, Cost of Inaction);
   - **«Закрыть направление»** — рассмотри всерьёз; если отбрасываешь, напиши почему (одна строка с опорой).
2. Для каждого варианта (шаблон [template.md](template.md)):
   - суть в одной фразе; для кого; что меняется для клиента;
   - **что должно быть правдой** — 3–5 условий, у каждого ID утверждения и статус (`[факт C-…]`, `[гипотеза C-…]`); условие без опоры — новая гипотеза (`claims.py add`, `kind: hypothesis`, `origin: agent`);
   - **сильные возражения** — 2–3 в форме «через год провалилось, потому что …», на чём держится возражение и что его снимет;
   - цена и усилия (порядок величины, это прогноз или гипотеза), выгоды, риски, обратимость (дверь 1-го или 2-го типа);
   - вклад в цель из `out/brief.md`.
3. Таблица сравнения вариантов по 4–6 критериям из цели и ограничений. Факты отдельно от гипотез и прогнозов.
4. Твоя рекомендация: какой вариант и **при каких условиях** она меняется (какие гипотезы, если не подтвердятся, переключают выбор).
5. **Независимая критика.** Вызови субагента **critic** (`.claude/agents/critic.md`, чистый контекст, Opus): передай пути `out/options.md` и `state/claims.jsonl`, попроси возражения к каждому варианту. Его таблицу вставь в конец `out/options.md` разделом «## Возражения критика» без правок. Для каждого возражения силы «высокая» заполни «Ответ автора»: поправил вариант (как) или почему возражение не меняет выбор; если меняет — перепиши рекомендацию. В Cursor без субагентов сделай этот шаг отдельным чатом с текстом `.claude/agents/critic.md` как инструкцией.
   `python3 scripts/verify_claims.py --fix` — метки в `out/options.md` должны совпадать со статусами.
6. **Точка человека (существенный выбор):** коротко покажи варианты, рекомендацию, главный риск и самые сильные возражения критика. Спроси, какой вариант берём (можно комбинацию или «нужны данные»). `python3 scripts/project.py wait "Выбрать вариант: A/B/C/D"` и закончи ход.
7. После ответа запиши решение в `state/decisions.md` (формат в файле): `D-001`, статус «принято», **Вариант** (буква из options.md), **Вердикт** — «делать», «нужна ясность» или «стоп» и причина после «—», **Основания** — ID утверждений из «что должно быть правдой» выбранного варианта, **Что заставит пересмотреть** — какие из этих условий, если окажутся неправдой, отменяют решение (уточнишь в плане проверки).
8. Проверка: `python3 scripts/decision_lint.py --fix` (её же запускает Stop-хук). «Делать» без проработанного варианта (нет «что должно быть правдой», возражений или меток утверждений) или без оснований автоматически понижается до «нужна ясность». Затем `python3 scripts/project.py stage strategy --note "выбран вариант …"` и переходи к скиллу strategy.

## Готово, когда
≥3 содержательно разных варианта, включая «оставить как есть» с «Ценой бездействия»; у каждого условия «должно быть правдой» и возражения с опорой; РП выбрал; решение записано с вердиктом и «Что заставит пересмотреть»; `decision_lint.py` чист.
