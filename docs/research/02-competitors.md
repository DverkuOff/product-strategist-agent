# 02. Конкуренты и аналоги: ИИ для продуктовой стратегии и исследований

Роль: competitor-analyst. Режим: глубоко (~15 поисков, ~6 открытых страниц, плюс GitHub API для звёзд и свежести). Дата: 11.11.2026.

## TL;DR
- **Ниша «папка skills для PM в Claude Code» плотно занята и очень популярна.** phuryn/pm-skills (27,9k★, обновлён 08.11.2026) уже даёт `/strategy`, `/discover`, `/market-scan`. deanpeters/Product-Manager-Skills (8k★) даёт 77 skills и 6 workflow, product-on-purpose/pm-skills (0,8k★) — 68 skills и 5 субагентов. Сам по себе «набор PM-фреймворков» жюри не удивит. Для нас: отличаться нужно сквозным процессом с доказательной базой, а не числом skills.
- **Самый близкий аналог — github/spec-kit, расширение `assess` (149k★).** Цепочка intake → research → define → shape → decide, решение `go / needs-clarification / kill`. В research «uncited assumptions are not established facts», есть теги источника и уверенности, правка артефактов вместо перегенерации этапа. Нет: коммуникационной стратегии, плана проверки, учёта стоимости, явного варианта «оставить как есть». Для нас: этот уровень уже норма, а пробелы как раз совпадают с обязательным минимумом кейса.
- **Журнал решений с происхождением фактов делает phuryn/pm-brain (961★, research preview).** Markdown-папка `knowledge/ hypotheses/ decisions/`, неизменяемый `source/`, теги происхождения (интервью, устно, догадка, общее знание), еженедельный `/review`, eval на 17 сценариях (404/406 проверок). Нет веб-исследования со ссылками, вариантов с возражениями, стратегий, стоимости. Остальные «decision log» репо имеют 0–1★. Для нас: память, которая «не превращает ответ агента в факт», уже показана, её надо превзойти или явно совместить.
- **Deep research (ChatGPT, Gemini, Claude, Perplexity, «Алиса AI — Исследовать») даёт отчёт, но не решение.** Ссылки галлюцинируются в 3–13% случаев, у Gemini Deep Research до 13,3% (arXiv 2604.03173, 2026). Проверка ссылок отдельным инструментом снижает долю нерабочих до 0,1–0,8%. Нет вариантов, журнала решений, стоимости запуска, продолжения по сохранённому состоянию. Для нас: автоматическая проверка ссылок и разделение «факт / гипотеза / прогноз» на уровне каждого утверждения — измеримое отличие.
- **Учёт стоимости и времени на артефакт не показывает ни один аналог.** ChatPRD и Productboard Spark считают кредиты на тарифе, ChatGPT Deep Research — лимит запусков в месяц. pm-brain ставит `--max-cost` только для своих тестов. Для нас: журнал «сколько стоило это решение» прямо закрывает критерий 4 кейса и незанят.

## Аналоги (10)
| Название | Ссылка | Что делает | Для кого | Модель и цена | Сильные стороны | Слабые стороны и жалобы | Open-source, взять за основу? |
|---|---|---|---|---|---|---|---|
| **phuryn/pm-skills** | github.com/phuryn/pm-skills | 72 skills и 42 workflow в 9 плагинах: discovery, strategy, GTM, метрики. `/strategy` строит 9-секционный Strategy Canvas | PM в Claude Code и Cowork, Codex; skills копируются в Cursor | Бесплатно, MIT. 27 861★, push 08.11.2026, 50 issues | Фреймворки Cagan, Torres, Savoia; команды предлагают следующий шаг; ставится как маркетплейс | `/strategy` заполняет шаблон по ответам пользователя: нет веб-исследования со ссылками, нет ≥3 вариантов с возражениями, нет статуса факт/гипотеза, нет стоимости [вывод по тексту команды] | Да (MIT). Можно ссылаться или брать отдельные фреймворки с атрибуцией |
| **phuryn/pm-brain** | github.com/phuryn/pm-brain | «Второй мозг» PM в Markdown: ingest → source → propagate в knowledge/hypotheses/decisions → теги происхождения → еженедельный `/review` | PM одного продукта, Claude Code | Бесплатно, MIT. 961★, push 20.05.2026 | Неизменяемые источники, теги «documented > verbal > intuition», решения с условием пересмотра («what would reopen them»), eval-харнесс | «Research preview»: по словам автора, у реальных пользователей «days old». Нет веб-поиска, вариантов, стратегий, стоимости. Последний push полгода назад | Да (MIT). Идеи схемы памяти и eval |
| **deanpeters/Product-Manager-Skills** | github.com/deanpeters/Product-Manager-Skills | 77 skills и 6 command workflow: positioning, product-strategy-session, competitive-analysis-process, SWOT | PM в Claude Code, Cursor, Codex, n8n | Бесплатно, лицензия не SPDX (NOASSERTION). 7 957★, push 16.10.2026 | «Adaptive Decision Ladder»: 3–5 вопросов, затем пронумерованные рекомендации. Принцип «Evidence first, framework last. SWOT on top of no research is opinion with a 2×2 around it» | Нет хранения состояния задачи и журнала стоимости. Skills независимы, сквозного пути «запрос → стратегия» нет (по README) | Частично: лицензию проверить перед заимствованием |
| **product-on-purpose/pm-skills** | github.com/product-on-purpose/pm-skills | 68 skills (Triple Diamond, Design Sprint), 10 `/workflow-*`, `/chain`, 5 субагентов (pm-critic и др.), 200+ примеров, опциональная проектная память с подтверждением записи | PM и авторы PM-инструментов | Бесплатно, Apache-2.0. 796★, push 10.11.2026 | CI-контракты на формат артефактов; v2.34 (17.10.2026) «samples that mark invented evidence»; субагент-критик | Узкая аудитория; фокус на артефактах PRD и спринта, не на стратегии и коммуникации | Да (Apache-2.0) |
| **github/spec-kit + assess** | github.com/github/spec-kit | SDD для кода плюс расширение оценки идеи: intake, research, define, shape, decide → `decision.md` | Разработчики и команды, любые агенты (Copilot, Claude, Cursor) | Бесплатно, MIT. 149 240★, push 10.11.2026, 210 issues | Поддерживающие и опровергающие доказательства, «cost of doing nothing», правка вместо перегенерации, артефакты по slug в `.specify/assessments/` | Нет коммуникационной стратегии, плана проверки и учёта стоимости. Варианта «ничего не делать» нет в shape (по гайду). Вход и язык ориентированы на софт | Да (MIT). Сильный ориентир по структуре этапов |
| **BMAD Method** | github.com/bmad-code-org/BMAD-METHOD | Агентный AI-driven development: Analyst (brainstorm, project brief) → PM (PRD) → Architect → Dev; «Durable context» | Разработчики, соло и команды | Бесплатно, MIT по бейджу. 55 243★, push 11.11.2026, 98 issues. v6.12 стабильная, v7 alpha с «breaking changes» | Решения явные и переносятся между чатами; процесс масштабируется под размер задачи | Цель — рабочий софт, стратегия только как вход в PRD. Требует Node 20+, Python 3.10+, uv: тяжело для руководителя продукта [вывод] | Как образец организации, не как основа |
| **ChatPRD** | chatprd.ai | SaaS: генерация PRD, one-pager, user stories; коучинг по пробелам; Projects с сохранённым контекстом | PM, особенно соло и в стартапах | Free 0$ (3 чата), Pro $15/мес, Teams $29/место, Enterprise (MakerStack, 06.2026) | Порог входа низкий, интеграции с Notion, Slack, Linear, Drive | «Output reflects the input»: без реальных данных клиентов генерично. Веб-исследования со ссылками, журнала решений, разметки факт/гипотеза нет (в обзоре не упомянуты). Конкурирует с ChatGPT и Claude за $20 | Нет (закрытый SaaS) |
| **Productboard Spark** | productboard.com/pricing/spark | ИИ-агент PM внутри Productboard: от идеи до спецификации, анализы, правки как tracked changes | Команды на Productboard | Кредиты; по вторичному источнику Free 50, Plus $19, Business $59 на maker/мес [не проверено]; кредиты действуют с 08.09 и 01.10.2026 (FAQ) | Правки принимаются или отклоняются; живёт рядом с фидбеком клиентов | Beta, отдельное рабочее пространство; привязка к платформе; стоимость в непрозрачных кредитах | Нет |
| **Dovetail (AI, Agents)** | dovetail.com | Синтез клиентских исследований: транскрипция, темы, сигналы; агенты маршрутизируют выводы в Slack и Teams | UX-исследователи, продуктовые команды | Цена через продажи; ~$29/пользователь Professional по GetApp [не проверено] | Сильный синтез интервью и фидбека | AI Agents и Dashboards местами в beta (по каталогу); не про стратегию; закрытые данные клиента | Нет |
| **Deep research: ChatGPT, Gemini, Claude Research, Perplexity, «Алиса AI — Исследовать»** | chatgpt.com, gemini.google.com, claude.ai, perplexity.ai, alice.yandex.ru | План → поиск десятков источников → многостраничный отчёт со ссылками. У «Алисы» видно «Как исследовала» | Все | ChatGPT: Plus $20, ~10 запусков/мес, Pro $200, ~250/мес (вторичные источники, OpenAI цифр не публикует). «Алиса»: бесплатно с месячным лимитом (запуск 02.04.2026) | Широта: 41–113 URL на запрос против 3–24 у обычного поиска | Нерабочие ссылки 5–18%, галлюцинированные 3–13% (Gemini DR 13,3%). Ручной аудит: проверяемы 38–57% цитат [по сниппету]. «Confident but hollow», «misinformation by omission», низкокачественные источники. Нет вариантов, решений, продолжения по состоянию, стоимости одного отчёта | Нет. Open-source аналоги: gpt-researcher (30,6k★), open_deep_research (12,7k★) |

Ещё рядом:
- **affaan-m/ECC** (бывший everything-claude-code, 300 915★, MIT): общий харнесс для разработчиков с memory, instincts, token optimization. Не PM.
- **Synthetic Users** и похожие (модельные респонденты): обзоры 2026 сходятся, что синтетика годится для раннего исследования. Для цен и готовности платить не годится; доверие исследователей низкое (8% по опросу User Interviews [не проверено]). Большинство критиков — конкуренты с реальными интервью.
- Репозитории «decision log»: arnavgulati13/decision-log-agent, yusufpapurcu/decision-journal-claude-skill, research-harness-template, mandate-framework. У всех 0–1★, ниши как продукта нет.

## Анализ
### Что уже решено хорошо (не повторять в лоб)
| Возможность | Кто делает хорошо |
|---|---|
| Библиотека PM-фреймворков (Canvas, JTBD, OST, SWOT, позиционирование) | pm-skills (phuryn), Product-Manager-Skills (deanpeters) |
| Генерация PRD и user stories | ChatPRD, Productboard Spark, BMAD (PM-агент) |
| Широкий веб-поиск с длинным отчётом | ChatGPT, Gemini, Claude, Perplexity Deep Research, «Алиса AI» |
| Этапы оценки идеи с артефактами и вердиктом | spec-kit assess |
| Markdown-память с тегами происхождения и решениями | pm-brain |
| Синтез интервью | Dovetail |

### Пробелы (по требованиям кейса)
| Требование кейса | Покрытие у аналогов | Пробел |
|---|---|---|
| ≥3 содержательно разных варианта, включая «оставить как есть», с сильными возражениями | spec-kit shape сравнивает концепты, но «do nothing» не гарантирован; `/ideate` в pm-brain даёт 3–7 направлений с доказательствами, без возражений | Обязательный «статус-кво» и steelman-возражения не встроены нигде [вывод] |
| Факты отделены от гипотез и прогнозов | spec-kit: теги confidence; pm-brain: теги происхождения; product-on-purpose: маркировка выдуманных доказательств в примерах | Три статуса (факт / гипотеза / прогноз) на уровне утверждения плюс автопроверка, что у факта есть живая ссылка: ни у кого [вывод] |
| Ссылка на источник каждого существенного сведения, проверка ссылок | Deep research даёт ссылки, но 5–18% не открываются | Проверка ссылок (в стиле urlhealth: исправление снижает нерабочие до 0,1–0,8%) в PM-агентах не найдена |
| Коммуникационная стратегия, согласованная с продуктовой («обещания соответствуют продукту») | У PM-skills есть positioning и value proposition как отдельные skills | Проверки согласованности обещаний и возможностей продукта не найдено [вывод] |
| План проверки (ожидаемое изменение, контроль, срок, нежелательные последствия) | pm-skills: эксперименты в discovery; pm-brain `/plan`: эксперименты и точки решения | Как обязательная часть стратегии с guardrail-метриками — нет [вывод] |
| Продолжение после перерыва в новом чате | BMAD «Durable context», spec-kit артефакты по slug, pm-brain папка | Явный файл состояния задачи «где остановились, что дальше» есть частично; у deep research нет |
| Прозрачность стоимости («сколько это стоило») | Нет ни у кого на уровне задачи или артефакта | **Полностью свободно** |
| Память, которая не превращает прежний ответ агента в факт, и отзыв устаревшего | pm-brain (теги, `/review`, условия пересмотра решений) | Занято частично и одним проектом с <1k★ |
| Модельные респонденты, явно помеченные как синтетика | Synthetic Users и др. как SaaS | В PM-репозиториях для Claude Code и Cursor почти нет; рынок скептичен [вывод] |
| Защита от prompt injection из источников | Не найдено в PM-репозиториях | Свободно [не проверено глубоко] |
| Русский язык и российский контекст (открытые источники РФ, телеком) | Все PM-репо англоязычные; «Алиса» на русском, но без PM-процесса | Свободно |

### Где за 11 дней реально показать отличие [вывод]
- Не соревноваться числом фреймворков. Можно опираться на существующие (MIT и Apache: pm-skills, spec-kit, product-on-purpose) с атрибуцией и показать сквозной процесс, которого у них нет.
- Видимые и проверяемые отличия, которые легко показать в видео:
  1. журнал стоимости и времени по задаче;
  2. разметка «факт / гипотеза / прогноз» и автопроверка ссылок;
  3. обязательный вариант «оставить как есть» с возражениями;
  4. проверка, что коммуникационная стратегия согласована с продуктовой;
  5. продолжение в новом чате по файлу состояния.
- Сравнение с исходным способом: тот же запрос в обычном deep research и в нашем агенте (число неподтверждённых утверждений, нерабочих ссылок, стоимость). Аналоги этого не публикуют, кроме eval в pm-brain.

## Вне скоупа
- urlhealth (open-source классификатор ссылок из arXiv 2604.03173) и ccusage-подобные счётчики стоимости Claude Code пригодятся tech-scout.
- В Product-Manager-Skills есть skill `agent-orchestration-advisor` для проектирования мультиагентных workflow.
- Отчёт User Interviews «State of Synthetic Users» (05.2026) пригодится domain-researcher для темы модельных респондентов.

## Источники
- phuryn/pm-skills, README и `pm-product-strategy/commands/strategy.md` (2026): https://github.com/phuryn/pm-skills
- phuryn/pm-brain, README (2026): https://github.com/phuryn/pm-brain
- deanpeters/Product-Manager-Skills, README (2026): https://github.com/deanpeters/Product-Manager-Skills
- product-on-purpose/pm-skills, README (2026): https://github.com/product-on-purpose/pm-skills
- github/spec-kit, README (2026): https://github.com/github/spec-kit
- Spec Kit, Assessment guide (2026): https://github.github.io/spec-kit/guides/assessment.html
- BMAD Method, README (2026): https://github.com/bmad-code-org/BMAD-METHOD
- affaan-m/ECC (2026): https://github.com/affaan-m/ECC
- Звёзды, даты push, лицензии: GitHub API на 11.11.2026
- MakerStack, ChatPRD Review (06.2026): https://makerstack.co/reviews/chatprd-review/
- Productboard, Spark pricing and billing FAQ (2026, по сниппету): https://support.productboard.com/hc/en-us/articles/48438638045459
- PricingSaaS, Spark: 4-уровневая кредитная модель (2026, по сниппету): https://pricingsaas.com/news/article/productboard-turns-spark-from-a-15-beta-add-on-into-a-4-tier-credit-platform
- Dovetail (2026, по сниппету): https://dovetail.com/ ; GetApp: https://www.getapp.com/ux-software/a/dovetail-app
- Rao, Wong, Callison-Burch, «Detecting and Correcting Reference Hallucinations in Commercial LLMs and Deep Research Agents», arXiv 2604.03173 (04.2026): https://www.alphaxiv.org/abs/2604.03173
- Emergent, ручная проверка 1285 цитат (10.2026, по сниппету): https://emergent.sh/news/40-ai-cited-statistics-trace-original-source
- Лимиты ChatGPT Deep Research (вторичные, 2026, по сниппету): https://fast.io/resources/chatgpt-deep-research-limits.md , https://dupple.com/learn/chatgpt-plus-vs-pro
- Жалобы на deep research (Reddit и блоги, 2025–2026, по сниппету; возможно устарело): https://nonamevc.substack.com/p/whats-wrong-with-deep-research-for , https://futuresearch.ai/oaidr-feb-2025
- Т—Ж, «Алиса AI» режим «Исследовать» (04.2026, по сниппету): https://t-j.ru/news/alisa-deepresearch/
- Синтетические респонденты, критика (2026, по сниппету): https://www.userinterviews.com/state-of-synthetic-users-report , https://uxdesign.cc/are-synthetic-users-really-the-future-of-ux-research-fd76fcb479ec
