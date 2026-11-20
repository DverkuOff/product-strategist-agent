"""Общие функции агента-стратега: пути, состояние задачи, снимки, нормализация текста, цены.

Только стандартная библиотека Python 3.10+. Работает без LLM.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path

STAGES = ["intake", "research", "options", "strategy", "validation", "done"]
STAGE_TITLES = {
    "intake": "постановка задачи",
    "research": "материалы и исследование",
    "options": "варианты",
    "strategy": "продуктовая и коммуникационная стратегия",
    "validation": "план проверки",
    "done": "готово",
}
CLAIM_KINDS = {"fact", "hypothesis", "forecast", "synthetic"}
CLAIM_STATUSES = {"active", "superseded", "retracted"}
KIND_RU = {"fact": "факт", "hypothesis": "гипотеза", "forecast": "прогноз", "synthetic": "синтетика"}

# Прейскурант Claude API, $ за 1M токенов: вход, выход, чтение кэша.
# Запись кэша: 1,25× входа (TTL 5 мин) и 2× входа (TTL 1 час).
# Источник: справочник моделей Claude API, кэш 03.11.2026; сверять с
# https://platform.claude.com/docs/en/about-claude/pricing
PRICES = {
    "haiku": {"input": 0.10, "output": 0.50, "cache_read": 0.01},
    "sonnet": {"input": 2.00, "output": 10.00, "cache_read": 0.10},
    "opus": {"input": 4.00, "output": 20.00, "cache_read": 0.20},
    "fable": {"input": 8.00, "output": 40.00, "cache_read": 0.20},
}
WEB_SEARCH_USD = 10.0 / 1000  # $10 за 1000 поисков


def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def today() -> str:
    return _dt.date.today().isoformat()


# ---------- пути ----------

def repo_root(start: str | os.PathLike | None = None) -> Path:
    """Корень репозитория агента: $CLAUDE_PROJECT_DIR или папка с AGENTS.md выше start."""
    env = os.environ.get("STRATEGIST_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (Path(env) / "AGENTS.md").exists():
        return Path(env).resolve()
    p = Path(start or Path(__file__).resolve().parent).resolve()
    for cand in [p, *p.parents]:
        if (cand / "AGENTS.md").exists() and (cand / "projects").exists():
            return cand
    return Path(__file__).resolve().parent.parent


def projects_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "projects"


def active_slug(root: Path | None = None) -> str | None:
    f = projects_dir(root) / ".active"
    if f.exists():
        slug = f.read_text(encoding="utf-8").strip()
        if slug and (projects_dir(root) / slug).is_dir():
            return slug
    return None


def project_path(slug: str | None = None, root: Path | None = None) -> Path | None:
    """Папка задачи: явный slug или путь, иначе активная задача."""
    if slug:
        p = Path(slug)
        if p.is_dir() and (p / "state").is_dir():
            return p.resolve()
        cand = projects_dir(root) / slug
        return cand if cand.is_dir() else None
    s = active_slug(root)
    return projects_dir(root) / s if s else None


# ---------- файлы состояния ----------

def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return rows
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: строка {i} не JSON: {e}") from e
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def load_task(proj: Path) -> dict:
    return read_json(proj / "state" / "task.json", {}) or {}


def append_journal(proj: Path, text: str) -> None:
    f = proj / "state" / "journal.md"
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp} · {text}\n")


# ---------- обязательные результаты этапов ----------
# Этап считается пройденным, только если его результат есть: иначе ворота качества проверяли бы пустое место.
STAGE_ARTIFACTS = {
    "research": [("out/research.md", "отчёт исследования")],
    "options": [("out/options.md", "варианты"), ("state/decisions.md", "запись решения D-xxx")],
    "strategy": [("out/comms-strategy.md", "коммуникационная стратегия"), ("state/product-properties.json", "реестр свойств")],
    "validation": [("out/validation-plan.md", "план проверки")],
}


def stages_passed(stage: str | None) -> list[str]:
    return STAGES[: STAGES.index(stage)] if stage in STAGES else []


def missing_artifacts(proj: Path, stage: str | None = None, only: set[str] | None = None) -> list[str]:
    """Результаты пройденных этапов, которых нет или которые пусты (этап берётся из task.json)."""
    stage = stage if stage is not None else load_task(proj).get("stage")
    out = []
    for s in stages_passed(stage):
        if only and s not in only:
            continue
        for rel, what in STAGE_ARTIFACTS.get(s, []):
            f = proj / rel
            text = f.read_text(encoding="utf-8") if f.exists() else ""
            if rel.endswith("decisions.md"):
                ok = re.search(r"^##\s+D-\d+", text, re.M) is not None
            elif rel.endswith(".json"):
                try:
                    data = json.loads(text) if text.strip() else {}
                except json.JSONDecodeError:
                    data = {}
                ok = bool(data.get("properties") if isinstance(data, dict) else data)
            else:
                ok = bool(text.strip())
            if not ok:
                out.append(f"A0 этап {s} пройден (сейчас {stage}), но нет результата: {rel} ({what})")
    return out


# ---------- материалы (снимки) ----------

FRONT_RE = re.compile(r"^---\n(.*?)\n---\n?", re.S)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Простой frontmatter «ключ: значение» (без вложенности). Возвращает (поля, тело)."""
    m = FRONT_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            meta[k.strip()] = v
    return meta, text[m.end():]


def list_materials(proj: Path) -> dict[str, dict]:
    """M-id → {path, meta, body}. Id берётся из frontmatter или префикса имени файла."""
    out: dict[str, dict] = {}
    mdir = proj / "materials"
    if not mdir.is_dir():
        return out
    for f in sorted(mdir.rglob("*")):
        if not f.is_file() or f.name.startswith(".") or f.name.lower() == "readme.md":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        meta, body = parse_frontmatter(text)
        mid = meta.get("id")
        if not mid:
            m = re.match(r"(M-\d+)", f.name)
            mid = m.group(1) if m else None
        if mid:
            out[mid] = {"path": f, "meta": meta, "body": body}
    return out


def duplicate_material_ids(proj: Path) -> dict[str, list[str]]:
    """M-id, которые встречаются в нескольких файлах снимков (гонка или ручное копирование)."""
    seen: dict[str, list[str]] = {}
    mdir = proj / "materials"
    for f in sorted(mdir.glob("M-*.md")) if mdir.is_dir() else []:
        meta, _ = parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        m = re.match(r"(M-\d+)", f.name)
        mid = meta.get("id") or (m.group(1) if m else None)
        if mid:
            seen.setdefault(mid, []).append(f.name)
    return {k: v for k, v in seen.items() if len(v) > 1}


def material_is_agent_file(mat: dict) -> bool:
    """Снимок локального файла, сохранённого не из inbox/ РП (старые снимки без origin считаются веб/РП)."""
    meta = mat.get("meta", {})
    return str(meta.get("url", "")).startswith("file:") and meta.get("origin") not in (None, "", "inbox", "synthetic")


def material_is_synthetic(mat: dict) -> bool:
    meta = mat.get("meta", {})
    return str(meta.get("kind", "")).lower() == "synthetic" or str(meta.get("synthetic", "")).lower() in {"true", "yes", "1"}


# ---------- нормализация и извлечение ----------

NBSP = "   "


def norm_text(s: str) -> str:
    s = s.lower().replace("ё", "е")
    for ch in NBSP:
        s = s.replace(ch, " ")
    s = re.sub(r"[«»“”„\"']", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


NUM_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[    ]\d{3})+|\d+)(?:[.,](\d+))?(?![\d])")


def extract_numbers(s: str) -> list[str]:
    """Числа в каноническом виде: «1 000» → «1000», «79,37» → «79.37», «10%» → «10»."""
    out = []
    for m in NUM_RE.finditer(s):
        whole = re.sub(r"[    ]", "", m.group(1))
        frac = m.group(2)
        out.append(f"{int(whole)}.{frac}" if frac else str(int(whole)))
    return out


SENT_START_RE = re.compile(r"(?:^|[.!?…]\s+|\n\s*[-*•]?\s*)$")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9]*")


# Служебные слова, с которых часто начинается предложение: их не считаем именами.
SENT_STOP = {
    "по", "для", "это", "как", "если", "что", "при", "после", "около", "более", "менее", "примерно",
    "почти", "среди", "также", "однако", "кроме", "из", "на", "от", "до", "за", "под", "над", "все", "всего",
    "его", "её", "их", "она", "оно", "они", "он", "мы", "вы", "так", "там", "здесь", "уже", "ещё", "еще",
    "через", "между", "свыше", "порядка", "каждый", "каждая", "каждое", "большинство", "часть", "доля",
    "этот", "эта", "эти", "тот", "та", "те", "который", "которая", "которые", "где", "когда", "чтобы",
}


def extract_proper_nouns(s: str) -> list[str]:
    """Слова с заглавной буквы (имена, бренды, организации), длиной от 3 символов.

    Первое слово предложения тоже проверяем (утверждение часто начинается с субъекта: «Билайн предлагает…»),
    кроме служебных слов из SENT_STOP. Обычное слово в начале («Подключения выросли…») обычно есть в
    снимке, из которого взято утверждение, поэтому ложных понижений это почти не даёт.
    """
    out = []
    for m in WORD_RE.finditer(s):
        w = m.group(0)
        if not w[0].isupper() or (len(w) < 3 and not (len(w) == 2 and w.isupper())):
            continue
        if w.lower() in SENT_STOP:
            continue
        out.append(w)
    return out


def sentence_initial_words(s: str) -> set[str]:
    """Слова, стоящие в начале предложения или пункта списка."""
    out = set()
    for m in WORD_RE.finditer(s):
        prefix = s[: m.start()]
        if prefix.strip() == "" or SENT_START_RE.search(prefix):
            out.add(m.group(0))
    return out


def stem(word: str) -> str:
    """Грубая основа для поиска с учётом падежей: отрезаем до 2 последних букв, минимум 3 символа."""
    w = norm_text(word)
    if len(w) <= 4:
        return w
    return w[: max(3, len(w) - 2)]


def numbers_in(text: str) -> set[str]:
    return set(extract_numbers(text))


# ---------- стоимость ----------

# Цены по точному id модели, $ за 1M токенов: вход, выход, чтение кэша (справочник Claude API, кэш 03.11.2026).
# У Haiku 5.5 промпт длиннее 100K стоит дороже ($0,50 / $2,50; чтение кэша по той же пропорции — допущение).
def _p(i, o, cr, **kw):
    return {"input": i, "output": o, "cache_read": cr, **kw}


MODEL_PRICES = {
    "claude-haiku-5-5": _p(0.10, 0.50, 0.01, long=_p(0.50, 2.50, 0.05, threshold=100_000)),
    "claude-sonnet-5-5": _p(2.00, 10.00, 0.10),
    "claude-opus-5-5": _p(4.00, 20.00, 0.20),
    "claude-fable-5-2": _p(8.00, 40.00, 0.20), "claude-mythos-5-2": _p(8.00, 40.00, 0.20),
    "claude-fable-5-1": _p(10.00, 50.00, 0.25), "claude-mythos-5-1": _p(10.00, 50.00, 0.25),
    "claude-fable-5": _p(10.00, 50.00, 1.00), "claude-mythos-5": _p(10.00, 50.00, 1.00),
    "claude-opus-5": _p(5.00, 25.00, 0.50), "claude-opus-4-8": _p(5.00, 25.00, 0.50),
    "claude-opus-4-7": _p(5.00, 25.00, 0.50), "claude-opus-4-6": _p(5.00, 25.00, 0.50),
    "claude-sonnet-5": _p(2.00, 10.00, 0.20), "claude-sonnet-4-6": _p(3.00, 15.00, 0.30),
    "claude-haiku-4-5": _p(1.00, 5.00, 0.10),
}


def canonical_model(model: str) -> str:
    m = (model or "").strip().lower()
    m = re.sub(r"\[.*?\]$", "", m)                 # claude-opus-5-5[1m]
    m = re.sub(r"^(us\.|eu\.|apac\.|global\.)?anthropic\.", "", m)  # префиксы облачных платформ
    m = re.sub(r"[-@]\d{8}(-v\d+(:\d+)?)?$", "", m)  # даты снимков
    return m


def model_family(model: str) -> str | None:
    m = (model or "").lower()
    for fam in PRICES:
        if fam in m:
            return fam
    return None


def usage_cost(model: str, usage: dict) -> float | None:
    """Стоимость ответа по прейскуранту API; None — цена модели неизвестна (а не $0)."""
    inp = usage.get("input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    cc = usage.get("cache_creation_input_tokens", 0) or 0
    det = usage.get("cache_creation") or {}
    c1h = det.get("ephemeral_1h_input_tokens", 0) or 0
    c5m = det.get("ephemeral_5m_input_tokens", 0) or 0
    if c1h + c5m == 0:
        c5m = cc
    ws = ((usage.get("server_tool_use") or {}).get("web_search_requests", 0)) or 0
    p = MODEL_PRICES.get(canonical_model(model))
    if p is None:
        return None if (inp or out or cr or cc) else ws * WEB_SEARCH_USD
    if p.get("long") and inp + cr + cc > p["long"]["threshold"]:
        p = p["long"]
    cost = (
        inp * p["input"]
        + out * p["output"]
        + cr * p["cache_read"]
        + c5m * p["input"] * 1.25
        + c1h * p["input"] * 2.0
    ) / 1_000_000
    return cost + ws * WEB_SEARCH_USD


LEDGER_FIELDS = [
    "ts", "session_id", "agent", "model", "stage",
    "input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens",
    "web_searches", "cost_usd",
]


def read_ledger(proj: Path) -> list[dict]:
    import csv

    f = proj / "state" / "cost-ledger.csv"
    if not f.exists():
        return []
    with f.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def ledger_total(proj: Path) -> float:
    total = 0.0
    for r in read_ledger(proj):
        try:
            total += float(r.get("cost_usd") or 0)
        except ValueError:
            pass
    return total


# ---------- журнал исследования (out/research-log.md) ----------

RESEARCH_LOG_HEAD = (
    "# Как проводилось исследование\n\n"
    "Какие запросы делал агент, что открыл, что отбросил и почему. Строки про снимки пишет `scripts/fetch_source.py`, "
    "запросы и отбрасывания — агент командой `scripts/research_log.py`.\n\n"
    "| Время | Действие | Что | Результат / почему |\n|---|---|---|---|\n"
)
RESEARCH_ACTIONS = {"query": "поиск", "open": "открыт", "fail": "не открылся", "discard": "отброшен", "note": "заметка", "plan": "план"}


def log_research(proj: Path, action: str, what: str, result: str = "") -> None:
    f = proj / "out" / "research-log.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        f.write_text(RESEARCH_LOG_HEAD, encoding="utf-8")
    clean = lambda x: str(x).replace("|", "/").replace("\n", " ").strip()  # noqa: E731
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"| {stamp} | {RESEARCH_ACTIONS.get(action, action)} | {clean(what)} | {clean(result)} |\n")


# ---------- неизменяемые снимки (materials/MANIFEST.json) ----------

MANIFEST = "MANIFEST.json"


def file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest_add(proj: Path, mid: str, path: Path, final_url: str = "", source_type: str = "") -> None:
    """Записать sha256 снимка; final_url и source_type прежней записи сохраняются, если новых не передали."""
    f = proj / "materials" / MANIFEST
    data = read_json(f, {}) or {}
    old = data.get(mid) or {}
    data[mid] = {"file": Path(path).name, "sha256": file_sha256(path), "saved_at": now_iso()}
    if final_url or old.get("final_url"):
        data[mid]["final_url"] = final_url or old["final_url"]
    if source_type or old.get("source_type"):
        data[mid]["source_type"] = source_type or old["source_type"]
    write_json(f, dict(sorted(data.items())))


# ---------- тип источника (надёжность) ----------
# Задаётся при сохранении снимка (fetch_source.py --source-type, иначе — по адресу и названию) и хранится в
# materials/MANIFEST.json, который агент изменить не может. verify_claims не даёт стать фактом утверждению,
# у которого все источники — форум, блог, отзывы, соцсети (ugc) или реклама продавца (advertising).
SOURCE_TYPES = {
    "official": "официальный: компания о себе, регулятор, госстатистика, отчётность",
    "media": "СМИ, отраслевое издание",
    "research": "исследование, аналитика с методикой",
    "ugc": "форум, блог, отзывы, соцсети",
    "advertising": "реклама, промо-материал продавца",
    "rp": "материал РП (выгрузка, документ)",
    "synthetic": "синтетика",
    "unknown": "не указан",
}
WEAK_SOURCE_TYPES = {"ugc", "advertising"}
UGC_HINT = re.compile(r"forum|форум|otzyv|отзыв|otzovik|irecommend|pikabu|reddit|livejournal|dzen\.ru|zen\.yandex|"
                      r"t\.me/|vk\.com|ok\.ru|youtube|tiktok|\bblog|блог|/comments?/|комментари", re.I)
AD_HINT = re.compile(r"\bпромо|реклам|/promo|/advert|utm_source=", re.I)


def guess_source_type(url: str = "", title: str = "", origin: str = "web") -> str:
    """Тип источника по адресу и названию, если агент его не указал."""
    if origin == "synthetic":
        return "synthetic"
    hay = f"{url} {title}"
    if UGC_HINT.search(hay):
        return "ugc"
    if AD_HINT.search(hay):
        return "advertising"
    if origin in ("inbox",) and not str(url).startswith("http"):
        return "rp"
    return "unknown"


def material_source_type(proj: Path, mid: str, mat: dict | None = None, manifest: dict | None = None) -> str:
    """Тип источника снимка: из MANIFEST.json (его агент не меняет), иначе из frontmatter, иначе unknown."""
    if manifest is None:
        manifest = read_json(proj / "materials" / MANIFEST, {}) or {}
    t = (manifest.get(mid) or {}).get("source_type")
    if not t and mat:
        t = (mat.get("meta") or {}).get("source_type")
    return t if t in SOURCE_TYPES else "unknown"


def manifest_check(proj: Path) -> tuple[dict[str, str], list[str]]:
    """({M-id: что не так} для изменённых или пропавших снимков, [M-id снимков вне манифеста])."""
    data = read_json(proj / "materials" / MANIFEST, None)
    if data is None:
        return {}, []
    bad = {}
    for mid, e in data.items():
        p = proj / "materials" / e["file"]
        if not p.exists():
            bad[mid] = "снимок удалён"
        elif file_sha256(p) != e["sha256"]:
            bad[mid] = "снимок изменён после сохранения (sha256 не совпадает с манифестом)"
    unlisted = [mid for mid in list_materials(proj) if mid not in data]
    return bad, unlisted


# ---------- журнал человека (state/human.jsonl) ----------
# Подтверждения, которые даёт только РП: «факт проверен человеком» и «план исследования утверждён».
# Файл защищён PreToolUse-хуком от записи агентом; пишут его только команды claims.py human-verified
# и project.py approve-plan, которые Claude Code выполняет после запроса разрешения у РП (permissions.ask).
# Флаги verified/approved в claims.jsonl и research-plan.json — только для показа, проверки им не верят.

HUMAN_LEDGER = "human.jsonl"


def text_sha(s: str) -> str:
    import hashlib

    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()[:16]


def human_records(proj: Path) -> list[dict]:
    try:
        return read_jsonl(proj / "state" / HUMAN_LEDGER)
    except ValueError:
        return []


def human_add(proj: Path, rec: dict) -> None:
    rec = {"at": now_iso(), **rec}
    with (proj / "state" / HUMAN_LEDGER).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def human_verified_ids(proj: Path, claims: list[dict]) -> set[str]:
    """ID утверждений, подтверждённых РП, у которых текст не менялся после подтверждения."""
    ok = {(r.get("claim"), r.get("text_sha")) for r in human_records(proj) if r.get("type") == "claim_verified"}
    return {c["id"] for c in claims if (c.get("id"), text_sha(c.get("text", ""))) in ok}


def plan_sha(plan: dict) -> str:
    return text_sha(json.dumps({"estimate": plan.get("estimate"), "created_at": plan.get("created_at")},
                               ensure_ascii=False, sort_keys=True))


def plan_approved(proj: Path) -> bool:
    plan = read_json(proj / "state" / "research-plan.json", None)
    if not plan:
        return False
    sha = plan_sha(plan)
    return any(r.get("type") == "plan_approved" and r.get("plan_sha") == sha for r in human_records(proj))


# ---------- величины: масштаб, проценты, даты (для verify_claims) ----------

MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
          "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
_MONTH_RX = r"(январ[яь]|феврал[яь]|марта?|апрел[яь]|ма[яй]|июн[яь]|июл[яь]|августа?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])"
DATE_NUM_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
DATE_WORD_RE = re.compile(rf"(?<!\d)(\d{{1,2}})\s+{_MONTH_RX}\s+(\d{{4}})", re.I)
SCALE = {"тыс": 1e3, "тысяч": 1e3, "млн": 1e6, "миллион": 1e6, "млрд": 1e9, "миллиард": 1e9, "трлн": 1e12, "триллион": 1e12}
QTY_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[    ]\d{3})+|\d+)(?:[.,](\d+))?(?![\d])"
    r"(?:\s*(%|процент\w*)|\s*(тыс\w*|млн|миллион\w*|млрд|миллиард\w*|трлн|триллион\w*)\.?)?", re.I)


def _month_num(word: str) -> int:
    w = word.lower()
    for stem_, n in sorted(MONTHS.items(), key=lambda x: -len(x[0])):
        if w.startswith(stem_):
            return n
    return 0


def extract_dates(text: str) -> list[str]:
    out = []
    for m in DATE_NUM_RE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            out.append(f"{y:04d}-{mo:02d}-{d:02d}")
    for m in DATE_WORD_RE.finditer(text):
        out.append(f"{int(m.group(3)):04d}-{_month_num(m.group(2)):02d}-{int(m.group(1)):02d}")
    return sorted(set(out), key=out.index)


def _strip_dates(text: str) -> str:
    text = DATE_NUM_RE.sub(lambda m: " " + m.group(3) + " ", text)  # год из даты остаётся числом
    return DATE_WORD_RE.sub(lambda m: " " + m.group(3) + " ", text)


def quantities(text: str) -> list[dict]:
    """Числа с единицей: {"v": значение, "abs": с учётом масштаба или None, "pct": bool, "raw": текст}."""
    out = []
    for m in QTY_RE.finditer(_strip_dates(text)):
        whole = re.sub(r"[    ]", "", m.group(1))
        v = float(f"{whole}.{m.group(2)}" if m.group(2) else whole)
        pct = bool(m.group(3))
        scale = None
        if m.group(4):
            key = next((k for k in sorted(SCALE, key=len, reverse=True) if m.group(4).lower().startswith(k)), None)
            scale = SCALE.get(key)
        out.append({"v": v, "abs": v * scale if scale else None, "pct": pct, "raw": m.group(0).strip()})
    return out


def _qty_match(q: dict, s: dict) -> bool:
    if q["pct"] != s["pct"]:
        return False
    qa, sa = q["abs"] or q["v"], s["abs"] or s["v"]
    if q["abs"] is not None or s["abs"] is not None:
        return abs(qa - sa) <= 1e-9 * max(1.0, abs(qa)) or (q["abs"] is None and abs(q["v"] - s["v"]) < 1e-9)
    return abs(q["v"] - s["v"]) < 1e-9


def missing_quantities(claim: str, evidence: str) -> list[str]:
    """Числа и даты утверждения, которых нет в тексте-основании (с учётом масштаба, % и формата дат)."""
    miss = []
    ev_dates = set(extract_dates(evidence))
    for d in extract_dates(claim):
        if d not in ev_dates:
            miss.append(d)
    ev = quantities(evidence)
    for q in quantities(claim):
        if not any(_qty_match(q, s) for s in ev):
            miss.append(q["raw"])
    return miss


def same_quantity(a: str, b: str) -> bool:
    qa, qb = quantities(a), quantities(b)
    return bool(qa) and all(any(_qty_match(x, y) for y in qb) for x in qa)


def name_found(word: str, text_norm: str) -> bool:
    """Имя в тексте целым словом: основа не короче 4 букв и окончание не длиннее 2 букв сверх отрезанного."""
    w = norm_text(word)
    if re.search(r"\d", w):
        return re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", text_norm) is not None
    if len(w) <= 4:  # короткие имена склоняются целиком: Ева/Еву/Евы, Иван/Ивана
        st = w[:-1] if len(w) >= 3 else w
    else:
        st = w[: max(4, len(w) - 2)]
    extra = len(w) - len(st) + 2
    return re.search(rf"(?<![^\W\d_]){re.escape(st)}[^\W\d_]{{0,{extra}}}(?![^\W\d_])", text_norm) is not None
