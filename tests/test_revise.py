import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from helpers import TempRepoCase
import revise


def run(argv):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
        rc = revise.main(argv)
    return rc, err.getvalue()


class Revise(TempRepoCase):
    def test_only_target_section_changed(self):
        self.assertEqual(run(["start", "out/comms-strategy.md", "--section", "Барьер"])[0], 0)
        self.replace_in("out/comms-strategy.md", "Не знают о функции", "Не знают о функции и боятся сложной настройки")
        self.assertEqual(run(["finish", "--reason", "РП: добавить страх настройки"])[0], 0)
        j = (self.proj / "state" / "journal.md").read_text(encoding="utf-8")
        self.assertIn("Правка out/comms-strategy.md, раздел «2. Барьер»", j)
        self.assertIn("РП: добавить страх настройки", j)
        log = (self.proj / "state" / "revisions" / "log.md").read_text(encoding="utf-8")
        self.assertIn("+Не знают о функции и боятся сложной настройки", log)
        self.assertFalse((self.proj / "state" / "revisions" / "pending.json").exists())

    def test_change_outside_section_rejected(self):
        run(["start", "out/comms-strategy.md", "--section", "Барьер"])
        self.replace_in("out/comms-strategy.md", "Не знают о функции", "Не знают о ней")
        self.replace_in("out/comms-strategy.md", "до 50 номеров близких", "до 49 номеров близких")
        rc, err = run(["finish", "--reason", "x"])
        self.assertEqual(rc, 1)
        self.assertIn("5. Ключевые обещания", err)
        self.assertEqual(run(["finish", "--reason", "осознанно", "--allow-other"])[0], 0)

    def test_unknown_section(self):
        self.assertEqual(run(["start", "out/comms-strategy.md", "--section", "Нет такого"])[0], 2)

    def test_sections_split(self):
        s = revise.sections("intro\n# A\nx\n## B\ny\n## B\nz\n")
        self.assertEqual(list(s), ["(начало)", "A", "B", "B #2"])
