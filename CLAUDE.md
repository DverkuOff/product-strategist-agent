@AGENTS.md

## Специфика Claude Code
- Скиллы этапов вызываются как `/intake`, `/research`, `/options`, `/strategy`, `/validation` (и `/revise`, `/compare`, `/synthetic-interview`, `/revisit`). Ты можешь вызывать их сам, когда этап готов к запуску. В Claude Code запускай этап **только инструментом Skill**, а не чтением `SKILL.md`: модель этапа (Opus у options и strategy) задаётся в скилле и при чтении файла не включается. Если Skill недоступен (нет разрешения), скажи об этом РП одной строкой и только тогда следуй файлу.
- Чтение источников поручай субагенту `source-reader` (`.claude/agents/source-reader.md`, Haiku, без Write/Bash/Edit). Возражения к вариантам — субагенту `critic` (`.claude/agents/critic.md`, Opus, чистый контекст, только чтение).
- Хуки (`.claude/settings.json`): SessionStart печатает сводку задачи; PreToolUse блокирует правку инструкций, методики и скриптов; PostToolUse помечает материалы как недоверенные; Stop запускает «ворота качества» (verify_claims, decision_lint, promise_lint) и пишет стоимость в `state/cost-ledger.csv`. Если Stop-хук вернул замечания, исправь их, а не обходи.
- Не используй встроенную память (MEMORY.md) для фактов задачи: всё состояние — в `projects/<задача>/state/`.
