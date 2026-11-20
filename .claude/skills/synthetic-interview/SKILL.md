---
name: synthetic-interview
description: Модельные респонденты — беседа с ИИ-собеседниками в заданной роли, чтобы найти гипотезы и отточить гайд реальных интервью. Каждая реплика помечается synthetic, материалы — kind synthetic, утверждения — kind synthetic; они никогда не становятся основанием факта и не доказывают спрос.
when_to_use: «синтетическое интервью», «модельные респонденты», «поговори с персонами», нет доступа к реальным пользователям на этапе research
model: sonnet
allowed-tools: Bash(python3 scripts/project.py status*) Bash(python3 scripts/project.py stage *) Bash(python3 scripts/project.py set *) Bash(python3 scripts/project.py wait *) Bash(python3 scripts/project.py log *) Bash(python3 scripts/project.py new *) Bash(python3 scripts/project.py list*) Bash(python3 scripts/project.py use *) Bash(python3 scripts/claims.py add*) Bash(python3 scripts/claims.py list*) Bash(python3 scripts/claims.py supersede *) Bash(python3 scripts/claims.py retract *) Bash(python3 scripts/fetch_source.py http*) Bash(python3 scripts/fetch_source.py projects/*) Bash(python3 scripts/verify_claims.py*) Bash(python3 scripts/promise_lint.py*) Bash(python3 scripts/decision_lint.py*) Bash(python3 scripts/compare.py*) Bash(python3 scripts/revisit.py*) Bash(python3 scripts/cost_report.py*) Bash(python3 scripts/estimate.py *) Bash(python3 scripts/research_log.py *) Bash(python3 scripts/revise.py *) Bash(python3 scripts/table_calc.py *) Bash(python3 -c *) Bash(python3 projects/*/out/calc-*.py) Bash(python3 projects/*/out/calc-*.py *) Read Write Edit
---

# Синтетические интервью (только для гипотез)

Методика и границы: `methodology/synthetic-respondents.md`. Синтетика льстит, поверхностна и не даёт поведенческих данных.

1. **Персоны** (2–4) — из сегментов в `out/research.md`; у каждой ситуация, работа, силы прогресса. Помечай: «Персона создана моделью».
2. **Гайд** — 6–8 вопросов о прошлом поведении («расскажите, как в последний раз …»), а не «купили бы вы». Вопросы из гипотез «что должно быть правдой».
3. **Беседа** — веди сам, отвечая за персону строго в роли; у каждой реплики персоны префикс `[СИНТЕТИКА]`. Без выдуманных статистик.
4. Сохрани стенограмму в файл (например, во временный `projects/<задача>/baseline/synthetic-<персона>.md`) и сделай снимок: `python3 scripts/fetch_source.py <файл> --kind synthetic --title "Синтетическое интервью: <персона>"`.
5. Утверждения — только `kind: synthetic` (`origin: synthetic`) со ссылкой на синтетический снимок. Если что-то из беседы важно — сформулируй как `hypothesis` с `basis: [C-…]` и добавь в план реальных интервью или проверки.
6. Итог в `out/research.md`, раздел «Синтетические интервью»: новые гипотезы, изменения гайда, явная пометка «не доказывает спрос и распространённость». `verify_claims.py` понизит любой факт, который попытается опереться на синтетику.
