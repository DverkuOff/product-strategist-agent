@AGENTS.md

## Специфика Claude Code
- Скиллы этапов вызываются как `/intake`, `/research`, `/options`, `/strategy`, `/validation` (и `/compare`, `/synthetic-interview`, `/revisit`). Ты можешь вызывать их сам, когда этап готов к запуску.
- Чтение источников поручай субагенту `source-reader` (`.claude/agents/source-reader.md`, Haiku, без Write/Bash/Edit).
- Хуки (`.claude/settings.json`): SessionStart печатает сводку задачи; PreToolUse блокирует правку инструкций, методики и скриптов; PostToolUse помечает материалы как недоверенные; Stop запускает «ворота качества» (verify_claims, promise_lint) и пишет стоимость в `state/cost-ledger.csv`. Если Stop-хук вернул замечания, исправь их, а не обходи.
- Не используй встроенную память (MEMORY.md) для фактов задачи: всё состояние — в `projects/<задача>/state/`.
