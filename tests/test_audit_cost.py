"""Регрессия по аудиту (В4): стоимость без двойного счёта при смене задачи и fork, цены по точному id модели."""
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

from helpers import SCRIPTS, TempRepoCase
import core
import project


def msg(mid, model, inp=0, out=0, cr=0):
    return {"type": "assistant", "message": {"id": mid, "model": model,
                                             "usage": {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cr}}}


class CostAudit(TempRepoCase):
    def hook(self, payload):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.tmp))
        payload.setdefault("_no_wait", True)
        subprocess.run([sys.executable, str(SCRIPTS / "hooks" / "cost_ledger.py")], input=json.dumps(payload),
                       capture_output=True, text=True, env=e, timeout=30)

    def transcript(self, name, lines):
        p = self.tmp / name
        p.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
        return str(p)

    def test_switching_task_does_not_recount_session(self):
        tp = self.transcript("t.jsonl", [msg("m1", "claude-sonnet-5-5", 1_000_000)])
        self.hook({"hook_event_name": "Stop", "session_id": "s1", "transcript_path": tp})
        with redirect_stdout(io.StringIO()):
            project.main(["new", "other-task", "Другая задача"])
        self.hook({"hook_event_name": "Stop", "session_id": "s1", "transcript_path": tp})
        self.assertAlmostEqual(core.ledger_total(self.proj), 2.0)
        self.assertAlmostEqual(core.ledger_total(self.tmp / "projects" / "other-task"), 0.0)
        with open(tp, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(msg("m2", "claude-sonnet-5-5", 0, 100_000)) + "\n")
        self.hook({"hook_event_name": "Stop", "session_id": "s1", "transcript_path": tp})
        self.assertAlmostEqual(core.ledger_total(self.tmp / "projects" / "other-task"), 1.0)  # только новое сообщение
        self.assertAlmostEqual(core.ledger_total(self.proj), 2.0)

    def test_fork_with_copied_history_not_recounted(self):
        tp1 = self.transcript("a.jsonl", [msg("m1", "claude-opus-5-5", 1_000_000)])
        self.hook({"hook_event_name": "Stop", "session_id": "s1", "transcript_path": tp1})
        tp2 = self.transcript("b.jsonl", [msg("m1", "claude-opus-5-5", 1_000_000), msg("m9", "claude-opus-5-5", 0, 10_000)])
        self.hook({"hook_event_name": "Stop", "session_id": "s2-fork", "transcript_path": tp2})
        self.assertAlmostEqual(core.ledger_total(self.proj), 4.0 + 0.2)

    def test_prices_by_exact_model(self):
        u = {"input_tokens": 1_000_000}
        self.assertAlmostEqual(core.usage_cost("claude-haiku-4-5", u), 1.0)
        self.assertAlmostEqual(core.usage_cost("claude-opus-5", u), 5.0)
        self.assertAlmostEqual(core.usage_cost("claude-opus-4-8", u), 5.0)
        self.assertAlmostEqual(core.usage_cost("claude-sonnet-4-6", u), 3.0)
        self.assertAlmostEqual(core.usage_cost("claude-fable-5-1", u), 10.0)
        self.assertAlmostEqual(core.usage_cost("claude-mythos-5-2", u), 8.0)
        self.assertAlmostEqual(core.usage_cost("claude-opus-5-5[1m]", u), 4.0)
        self.assertIsNone(core.usage_cost("claude-unknown-9", u))

    def test_haiku_long_prompt_tier(self):
        self.assertAlmostEqual(core.usage_cost("claude-haiku-5-5", {"input_tokens": 50_000, "output_tokens": 1_000_000}), 0.005 + 0.5)
        self.assertAlmostEqual(core.usage_cost("claude-haiku-5-5", {"input_tokens": 150_000, "output_tokens": 1_000_000}), 0.075 + 2.5)

    def test_unknown_model_marked_not_zero(self):
        tp = self.transcript("u.jsonl", [msg("m1", "claude-unknown-9", 1_000_000)])
        self.hook({"hook_event_name": "Stop", "session_id": "s1", "transcript_path": tp})
        rows = core.read_ledger(self.proj)
        self.assertEqual(rows[-1]["cost_usd"], "")
        import cost_report
        with redirect_stdout(io.StringIO()) as out:
            cost_report.main(["--project", str(self.proj)])
        self.assertIn("цена неизвестна", out.getvalue())


class WebSearchCount(TempRepoCase):
    """WebSearch в Claude Code — клиентский инструмент: поиск виден только как tool_use в стенограмме."""

    def test_websearch_tool_use_counted_once_per_call(self):
        sys.path.insert(0, str(SCRIPTS / "hooks"))
        import cost_ledger
        u = {"input_tokens": 10, "output_tokens": 5}
        lines = [  # один ответ (один message.id) разбит на две строки, в каждой свой вызов WebSearch
            {"type": "assistant", "message": {"id": "m1", "model": "claude-sonnet-5-5", "usage": u,
                                              "content": [{"type": "tool_use", "name": "WebSearch"}]}},
            {"type": "assistant", "message": {"id": "m1", "model": "claude-sonnet-5-5", "usage": u,
                                              "content": [{"type": "tool_use", "name": "WebSearch"}]}},
            {"type": "assistant", "message": {"id": "m2", "model": "claude-sonnet-5-5", "usage": dict(u, server_tool_use={"web_search_requests": 1}),
                                              "content": [{"type": "tool_use", "name": "WebSearch"}]}},
        ]
        t = self.tmp / "t.jsonl"
        t.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
        msgs = cost_ledger.messages_from_transcript(t, main_only=True)
        ws = [m["usage"]["server_tool_use"]["web_search_requests"] for m in msgs]
        self.assertEqual(ws, [2, 1])  # без двойного счёта, если сервер уже сообщил поиск
        self.assertGreater(core.usage_cost("claude-sonnet-5-5", msgs[0]["usage"]), core.usage_cost("claude-sonnet-5-5", u))
