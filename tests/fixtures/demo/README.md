# Эталонная задача для тестов и проверки «ворот качества» без LLM

Копия демо-задачи «Защита близких» (`projects/demo-zashchita-blizkih/`) с заполненными результатами этапов:
снимки открытых источников (`materials/`, те же M-01…M-11), 22 утверждения (`state/claims.jsonl`), реестр свойств
(`state/product-properties.json`), решение D-001, сокращённые `out/` и ответ обычного чата (`baseline/`).

Состояние и `out/` подготовлены разработчиком по снимкам до сквозного прогона агента: это эталон для тестов, а не
результат работы агента. Результат агента появится в `projects/demo-zashchita-blizkih/out/` после прогона в Claude Code.

Попробовать проверки:
```bash
python3 scripts/verify_claims.py --project tests/fixtures/demo
python3 scripts/promise_lint.py  --project tests/fixtures/demo --matrix
python3 scripts/compare.py       --project tests/fixtures/demo --no-write
python3 scripts/revisit.py       --project tests/fixtures/demo
```
Тесты (`python3 -m unittest discover -s tests`) копируют эту папку во временный каталог и портят её: меняют число в факте,
убирают опору обещания, добавляют «гарантированно» — и проверяют, что ворота это ловят.
