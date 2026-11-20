---
name: strategy
description: Этап 4 — продуктовая и коммуникационная стратегия выбранного варианта. Реестр свойств продукта (факт/гипотеза) в state/product-properties.json; продуктовая стратегия (аудитория и задача, альтернативы, направление и осознанные отказы, польза ↔ затраты и доходы); коммуникационная стратегия (аудитория и ситуация, барьер, ключевое сообщение и подтверждение, роль каналов), где каждое обещание опирается на свойство — «Сверка обещаний».
when_to_use: этап strategy в state/task.json после выбора варианта
model: opus
allowed-tools: Bash(python3 "${CLAUDE_PROJECT_DIR}/scripts/project.py" status *) Bash(python3 scripts/project.py status*) Bash(python3 scripts/project.py stage *) Bash(python3 scripts/project.py set *) Bash(python3 scripts/project.py wait *) Bash(python3 scripts/project.py log *) Bash(python3 scripts/project.py new *) Bash(python3 scripts/project.py list*) Bash(python3 scripts/project.py use *) Bash(python3 scripts/claims.py add*) Bash(python3 scripts/claims.py list*) Bash(python3 scripts/claims.py supersede *) Bash(python3 scripts/claims.py retract *) Bash(python3 scripts/fetch_source.py http*) Bash(python3 scripts/fetch_source.py projects/*) Bash(python3 scripts/verify_claims.py*) Bash(python3 scripts/promise_lint.py*) Bash(python3 scripts/decision_lint.py*) Bash(python3 scripts/compare.py*) Bash(python3 scripts/revisit.py*) Bash(python3 scripts/cost_report.py*) Bash(python3 scripts/estimate.py *) Bash(python3 scripts/research_log.py *) Bash(python3 scripts/revise.py *) Read Write Edit Glob Grep
---

# Этап 4. Продуктовая и коммуникационная стратегия

Текущее состояние: !`python3 "${CLAUDE_PROJECT_DIR}/scripts/project.py" status --short`

Методика: `methodology/jtbd.md`, `methodology/positioning-dunford.md`, `methodology/north-star-unit-economics.md`, `methodology/comms-strategy.md`, `methodology/advertising-law-ru.md`.
Опора: выбранный вариант в `out/options.md` и `state/decisions.md`, утверждения в `state/claims.jsonl`.

## 1. Реестр свойств продукта — сначала
`state/product-properties.json` (пример — [properties-example.json](properties-example.json)):
- свойство = что продукт **делает** или **даёт**, одним предложением, числа как в источнике;
- `status: fact` — только если опирается на утверждения-факты (`claims: ["C-…"]`); всё запланированное, обещанное в выбранном варианте, но не подтверждённое — `hypothesis`;
- свойство-факт, чьи claims понижены проверкой, автоматически считается гипотезой.

## 2. Продуктовая стратегия → `out/product-strategy.md` ([template-product.md](template-product.md))
Аудитория и её задача (ситуация, работа, силы прогресса) · альтернативы (включая «ничего не делать») · выбранное направление: где играем и как выигрываем · **осознанные отказы** (что не делаем и почему) · связь пользы с затратами и доходами (цепочка «польза → метрика → деньги», расчёты кодом, статусы) · ключевые свойства (P-xx) · риски. Каждый раздел называет методику.

## 3. Коммуникационная стратегия → `out/comms-strategy.md` ([template-comms.md](template-comms.md))
Аудитория и ситуация (та же, что в продуктовой) · барьер понимания или выбора (из тревоги и привычки) · ключевое сообщение и подтверждение · роль каналов · **таблица «Ключевые обещания»**:

| ID | Обещание | Опора | Тип |
|---|---|---|---|
| MSG-01 | текст обещания | P-01, P-03 | обещание |
| MSG-02 | текст, опирающийся на гипотезу | P-05 | тест сообщения |

Правила (их проверяет `scripts/promise_lint.py`, его же запускает Stop-хук):
- каждое обещание опирается хотя бы на одно свойство P-xx;
- обещание на свойстве-гипотезе — только «тест сообщения», и его ID обязан быть в `out/validation-plan.md` (добавь строку-заготовку сразу);
- никаких «самый», «лучший», «№1», «гарантированно», «100%», «полная защита», «от всех …», если опорное свойство-факт этого не говорит;
- числа в обещании — только те, что есть в опорных свойствах;
- не обещай шире свойства: если свойство «разрывает около 10% мошеннических звонков», нельзя «защищает от мошенников».

## 4. Согласованность
- `python3 scripts/promise_lint.py` и `python3 scripts/promise_lint.py --matrix` (вставь матрицу «обещание → свойство → статус → основания» в конец comms-strategy.md).
- Аудитория, направление и отказы одинаковы в обоих документах.
- `python3 scripts/verify_claims.py --fix` — метки статусов в документах.

## 5. Точка человека
Покажи РП: направление, 3 главных отказа, ключевое сообщение и что ушло в тесты сообщений. Спроси подтверждение (`project.py wait "Утвердить отказы и ключевое сообщение"`), закончи ход. После ответа — правки, затем `python3 scripts/project.py stage validation --note "..."` и скилл validation.
