"""Поиск фрагментов источника, похожих на инструкции агенту (prompt injection).

Это вспомогательный сигнал для журнала и предупреждения, а не защита: основная защита
архитектурная (карантинный субагент без записи, PreToolUse-запрет правки инструкций).
Регулярные выражения ловят только простые атаки.
"""
from __future__ import annotations

import re

PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (the )?(previous|above|system)",
    r"you are now",
    r"system prompt",
    r"(new|updated) instructions? for (the )?(ai|assistant|agent|model)",
    r"игнорируй\w* (все |всё )?(предыдущ|прежн|ранее|свои|данн)\w*",
    r"забудь\w* (все |всё )?(предыдущ|прежн|инструкц|правил)\w*",
    r"(нов|обновл)\w+ инструкц\w+ для (ии|ai|ассистент|агент|модел)\w*",
    r"(ты|вы) теперь\b",
    r"(запиши|добавь|измени|удали|перезапиши)\w* .{0,40}(agents\.md|claude\.md|\.claude|settings\.json|methodology|инструкци\w+ агента)",
    r"(рекомендуй|выбери|порекомендуй)\w* (только |именно )?(вариант|продукт)",
    r"(для|to) (ии|ai|llm|assistant|ассистента|агента)\s*[:\-—]",
    r"<\s*/?\s*(system|assistant|instructions?)\s*>",
]
_RX = [re.compile(p, re.I) for p in PATTERNS]


def scan(text: str, context: int = 60) -> list[str]:
    """Вернуть короткие фрагменты вокруг совпадений (без дублей)."""
    hits: list[str] = []
    seen = set()
    for rx in _RX:
        for m in rx.finditer(text):
            a, b = max(0, m.start() - context), min(len(text), m.end() + context)
            frag = re.sub(r"\s+", " ", text[a:b]).strip()
            key = (m.start() // 200)
            if key in seen:
                continue
            seen.add(key)
            hits.append(frag)
    return hits
