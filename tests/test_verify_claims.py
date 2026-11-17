import unittest

from helpers import TempRepoCase
import verify_claims


class VerifyClaims(TempRepoCase):
    def test_fixture_is_clean(self):
        rep = verify_claims.check(self.proj)
        self.assertEqual(rep["downgrade"], [])
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["stats"]["fact"], 15)

    def test_wrong_number_downgrades_and_breaks_doc_label(self):
        # Модель «округлила» 10% до 15% — числа нет в снимке
        c = next(x for x in self.claims() if x["id"] == "C-002")
        self.edit_claim("C-002", text=c["text"].replace("10%", "15%"))
        rep = verify_claims.check(self.proj)
        self.assertEqual([d[0] for d in rep["downgrade"]], ["C-002"])
        self.assertIn("15", rep["downgrade"][0][2])
        self.assertTrue(any("research.md: C-002 помечено как факт" in e for e in rep["errors"]))
        n = verify_claims.apply_fix(self.proj, rep)
        self.assertEqual(n, 1)
        c2 = next(x for x in self.claims() if x["id"] == "C-002")
        self.assertEqual(c2["kind"], "hypothesis")
        self.assertEqual(c2["downgraded"]["from"], "fact")
        # после исправления повторная проверка не понижает, но метка в документе всё ещё неверна
        rep2 = verify_claims.check(self.proj)
        self.assertEqual(rep2["downgrade"], [])
        self.assertTrue(rep2["errors"])

    def test_unknown_proper_noun_downgrades(self):
        self.edit_claim("C-015", text="Билайн предлагает подписку «Защитник+ для семьи»")
        rep = verify_claims.check(self.proj)
        self.assertIn("C-015", [d[0] for d in rep["downgrade"]])

    def test_agent_memory_is_not_fact(self):
        rows = self.claims()
        rows.append({"id": "C-099", "text": "Подключения растут на 5% в месяц", "kind": "fact", "sources": [], "origin": "agent", "status": "active"})
        self.write_claims(rows)
        rep = verify_claims.check(self.proj)
        d = [x for x in rep["downgrade"] if x[0] == "C-099"][0]
        self.assertEqual(d[1], "no_source")
        self.assertIn("прежний вывод агента", d[2])

    def test_missing_snapshot(self):
        self.edit_claim("C-005", sources=[{"material": "M-77"}])
        rep = verify_claims.check(self.proj)
        self.assertIn(("C-005", "no_snapshot"), [(d[0], d[1]) for d in rep["downgrade"]])

    def test_url_without_snapshot_is_not_fact(self):
        self.edit_claim("C-005", sources=[{"url": "https://example.ru"}])
        rep = verify_claims.check(self.proj)
        self.assertIn("C-005", [d[0] for d in rep["downgrade"]])

    def test_synthetic_material_cannot_support_fact(self):
        (self.proj / "materials" / "M-50-synthetic.md").write_text(
            "---\nid: M-50\nkind: synthetic\n---\n\n[СИНТЕТИКА] Я бы подключил защиту маме за 99 рублей\n", encoding="utf-8")
        rows = self.claims()
        rows.append({"id": "C-090", "text": "Пользователи готовы платить 99 рублей", "kind": "fact",
                     "sources": [{"material": "M-50"}], "origin": "source", "status": "active"})
        rows.append({"id": "C-091", "text": "Персона готова платить 99 рублей", "kind": "synthetic",
                     "sources": [{"material": "M-50"}], "origin": "synthetic", "status": "active"})
        self.write_claims(rows)
        rep = verify_claims.check(self.proj)
        reasons = {d[0]: d[1] for d in rep["downgrade"]}
        self.assertEqual(reasons.get("C-090"), "synthetic")
        self.assertNotIn("C-091", reasons)  # синтетика остаётся синтетикой

    def test_human_verified_skips_auto_check(self):
        import claims as claims_cli
        import io
        from contextlib import redirect_stdout
        self.edit_claim("C-005", text="Через Еву можно защитить до 77 номеров")
        with redirect_stdout(io.StringIO()):
            claims_cli.main(["human-verified", "C-005", "--note", "сверил в приложении"])
        rep = verify_claims.check(self.proj)
        self.assertIn("C-005", rep["human"])
        self.assertNotIn("C-005", [d[0] for d in rep["downgrade"]])

    def test_retracted_claim_in_doc_is_error(self):
        self.edit_claim("C-004", status="retracted")
        rep = verify_claims.check(self.proj)
        self.assertTrue(any("C-004 отозвано" in e for e in rep["errors"]))

    def test_unknown_reference_in_doc(self):
        self.replace_in("out/research.md", "[факт C-001]", "[факт C-404]")
        rep = verify_claims.check(self.proj)
        self.assertTrue(any("C-404" in e for e in rep["errors"]))

    def test_duplicate_ids(self):
        rows = self.claims()
        rows.append(dict(rows[0]))
        self.write_claims(rows)
        rep = verify_claims.check(self.proj)
        self.assertTrue(any("повторяется" in e for e in rep["errors"]))

    def test_cli_exit_codes(self):
        self.assertEqual(verify_claims.main(["--project", str(self.proj)]), 0)
        self.edit_claim("C-009", text="Ева помогает более 12 млн клиентов")
        self.assertEqual(verify_claims.main(["--project", str(self.proj), "--fix"]), 1)


if __name__ == "__main__":
    unittest.main()


class ImmutableSnapshots(TempRepoCase):
    def test_manifest_clean(self):
        import core
        self.assertEqual(core.manifest_check(self.proj), ({}, []))

    def test_edited_snapshot_is_error_and_downgrades_facts(self):
        snap = sorted((self.proj / "materials").glob("M-03-*.md"))[0]
        snap.write_text(snap.read_text(encoding="utf-8").replace("порядка 10%", "порядка 50%"), encoding="utf-8")
        rep = verify_claims.check(self.proj)
        self.assertTrue(any("M-03: снимок изменён" in e for e in rep["errors"]))
        reasons = {d[0]: d[1] for d in rep["downgrade"]}
        self.assertEqual(reasons.get("C-002"), "snapshot_changed")
        self.assertEqual(reasons.get("C-004"), "snapshot_changed")

    def test_deleted_snapshot(self):
        sorted((self.proj / "materials").glob("M-05-*.md"))[0].unlink()
        rep = verify_claims.check(self.proj)
        self.assertTrue(any("M-05: снимок удалён" in e for e in rep["errors"]))

    def test_snapshot_outside_manifest_is_warning(self):
        (self.proj / "materials" / "M-30-manual.md").write_text("---\nid: M-30\n---\n\nтекст\n", encoding="utf-8")
        rep = verify_claims.check(self.proj)
        self.assertTrue(any("M-30" in w and "MANIFEST" in w for w in rep["warnings"]))

    def test_fetch_source_adds_to_manifest(self):
        import io
        from contextlib import redirect_stdout
        import core
        import fetch_source
        src = self.inbox_file("x.md", "новый материал " * 30)
        with redirect_stdout(io.StringIO()):
            fetch_source.main([str(src)])
        data = core.read_json(self.proj / "materials" / core.MANIFEST, {})
        self.assertIn("M-12", data)
        self.assertEqual(core.manifest_check(self.proj), ({}, []))
