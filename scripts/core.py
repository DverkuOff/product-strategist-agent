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
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-]*")


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

def model_family(model: str) -> str | None:
    m = (model or "").lower()
    for fam in PRICES:
        if fam in m:
            return fam
    return None


def usage_cost(model: str, usage: dict) -> float:
    fam = model_family(model)
    if not fam:
        return 0.0
    p = PRICES[fam]
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


def manifest_add(proj: Path, mid: str, path: Path) -> None:
    f = proj / "materials" / MANIFEST
    data = read_json(f, {}) or {}
    data[mid] = {"file": Path(path).name, "sha256": file_sha256(path), "saved_at": now_iso()}
    write_json(f, dict(sorted(data.items())))


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
