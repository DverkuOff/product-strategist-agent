"""Регрессия по аудиту (В3) и жюри (п.4): fetch_source — SSRF, размер, кодировки, капча, пустые снимки,
повторы, гонки. Сценарии — из скрипта аудитора review-agent-tech/tools/fetchtest.py (локальный HTTP-сервер)."""
import http.server
import io
import json
import os
import subprocess
import sys
import threading
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

from helpers import SCRIPTS, TempRepoCase
import core
import fetch_source
import verify_claims

LONG = "<p>" + "Выручка оператора выросла на 11 процентов, абонентская база растёт. " * 20 + "</p>"


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body: bytes, ctype="text/html; charset=utf-8", code=200, headers=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path
        if p == "/redir":
            return self.send(b"", code=302, headers=[("Location", "http://169.254.169.254/latest/meta-data")])
        if p == "/cp1251":
            return self.send(("<html><body>" + LONG + "</body></html>").encode("cp1251"), ctype="text/html")
        if p == "/captcha":
            body = ("<html><title>Вы не робот?</title><body><p>" + "Подтвердите, что запросы отправляли вы, а не робот. "
                    "Нам очень жаль, но запросы с вашего устройства похожи на автоматические. " * 3 + "</p></body></html>")
            return self.send(body.encode())
        if p == "/empty":
            return self.send(b"<html><body><div id='root'></div><script>app()</script></body></html>")
        if p == "/big":
            return self.send(b"<p>" + b"A" * 6_000_000 + b"</p>")
        return self.send(("<html><title>Новость</title><body>" + LONG + "</body></html>").encode())


class FetchAudit(TempRepoCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def fetch(self, *argv, allow_private=False):
        old = fetch_source.ALLOW_PRIVATE
        fetch_source.ALLOW_PRIVATE = allow_private
        try:
            with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                rc = fetch_source.main(list(argv))
        finally:
            fetch_source.ALLOW_PRIVATE = old
        return rc, out.getvalue() + err.getvalue()

    def snapshots(self):
        return sorted(p.name for p in (self.proj / "materials").glob("M-*.md"))

    def test_ssrf_private_and_metadata_refused(self):
        before = self.snapshots()
        for url in (f"{self.base}/admin", "http://169.254.169.254/latest/meta-data", "http://localhost/", "http://10.0.0.1/",
                    "file:///etc/passwd", "ftp://example.com/x"):
            rc, out = self.fetch(url)
            self.assertNotEqual(rc, 0, url)
        self.assertEqual(self.snapshots(), before)

    def test_redirect_to_private_refused(self):
        rc, out = self.fetch(f"{self.base}/redir", allow_private=True)  # первый шаг разрешён тестом, редирект — нет
        self.assertNotEqual(rc, 0)
        self.assertIn("169.254.169.254", out)

    def test_cp1251_without_charset(self):
        rc, out = self.fetch(f"{self.base}/cp1251", "--title", "cp1251", allow_private=True)
        self.assertEqual(rc, 0, out)
        snap = (self.proj / "materials" / self.snapshots()[-1]).read_text(encoding="utf-8")
        self.assertIn("Выручка оператора", snap)
        self.assertNotIn("�", snap)

    def test_captcha_and_empty_are_failures(self):
        before = self.snapshots()
        for path in ("/captcha", "/empty"):
            rc, out = self.fetch(f"{self.base}{path}", allow_private=True)
            self.assertEqual(rc, 1, path)
        self.assertEqual(self.snapshots(), before)
        log = (self.proj / "out" / "research-log.md").read_text(encoding="utf-8")
        self.assertIn("не открылся", log)
        self.assertNotIn("| открыт |", log)

    def test_size_limit(self):
        rc, out = self.fetch(f"{self.base}/big", "--title", "big", allow_private=True)
        snap = self.proj / "materials" / self.snapshots()[-1]
        self.assertLess(snap.stat().st_size, 5_500_000)
        self.assertIn("обрезан", snap.read_text(encoding="utf-8")[:600])

    def test_final_url_and_dedup(self):
        rc, out = self.fetch(f"{self.base}/news", allow_private=True)
        self.assertEqual(rc, 0, out)
        n = len(self.snapshots())
        rc, out = self.fetch(f"{self.base}/news", allow_private=True)
        self.assertEqual(rc, 0)
        self.assertIn("уже есть", out)
        self.assertEqual(len(self.snapshots()), n)
        f = self.inbox_file("same.html", "x")  # другой файл
        f.write_bytes(urllib.request.urlopen(f"{self.base}/news").read())  # те же байты → тот же sha256
        rc, out = self.fetch(str(f))
        self.assertIn("уже есть", out)
        self.assertEqual(len(self.snapshots()), n)
        mf = core.read_json(self.proj / "materials" / core.MANIFEST)
        last = sorted(mf)[-1]
        self.assertTrue(mf[last].get("final_url", "").startswith(self.base))

    def test_parallel_runs_get_distinct_ids(self):
        files = [self.inbox_file(f"r{i}.md", f"Материал номер {i}. " * 40) for i in range(6)]
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.tmp))
        procs = [subprocess.Popen([sys.executable, str(SCRIPTS / "fetch_source.py"), str(f)], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for f in files]
        outs = [p.communicate()[0] for p in procs]
        self.assertTrue(all(p.returncode == 0 for p in procs), outs)
        ids = [n[:4] for n in self.snapshots()]
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertEqual(core.manifest_check(self.proj), ({}, []))

    def test_duplicate_material_id_is_error(self):
        src = sorted((self.proj / "materials").glob("M-03-*.md"))[0]
        (self.proj / "materials" / "M-03-copy.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        rep = verify_claims.check(self.proj)
        self.assertTrue(any("M-03" in e and "повтор" in e for e in rep["errors"]), rep["errors"])
