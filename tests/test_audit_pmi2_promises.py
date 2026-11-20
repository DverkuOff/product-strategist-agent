"""Регрессия по второму кругу ПМИ: Л-1, Л-2 (ложные E8/E5), Н-10 (таблица «Роль каналов»), Н-14 (новые формулировки),
Н-12 (compare показывает совпадение и не считает обычные обороты)."""
from helpers import TempRepoCase
import compare
import promise_lint
from test_audit_pmi_gates import VARIANTS

NORMAL_PHRASES = [  # Л-2: из копии эталона в отчёте второго круга
    "…получает владелец списка, а не самому близкому приходится разбираться",
    "…тем самым родители меньше рискуют",
    "Всё просто: номера близких добавляются в настройках Евы",
    "Ева не гарантирует блокировку всех звонков, но сообщит о попытке",
    "…больше всего их получают родители",
    "…для родителей любого возраста…",
    "Каждый раз владелец списка получает уведомление",
    "лучше, чем оставлять родителей без защиты", "сама разрывает", "самостоятельно блокирует",
    "Первый шаг — добавьте номер", "до пятидесяти номеров", "в отличие от аналогов других операторов",
]
NEW_RISKY = [  # Н-14
    "надёжнее не бывает", "как никто другой", "без единого пропуска", "первая такая услуга в стране", "на 100 процентов",
    "не пропустит ни одного звонка",
]


def issues(rep, pid):
    return [code for p in rep["promises"] if p["id"] == pid for code, _ in p["issues"]]


class Pmi2Promises(TempRepoCase):
    def add_promise(self, text, prop="P-02"):
        self.replace_in("out/comms-strategy.md", "| MSG-06 | Родителям не нужен смартфон | P-07 | тест сообщения |",
                        f"| MSG-06 | Родителям не нужен смартфон | P-07 | тест сообщения |\n| MSG-09 | {text} | {prop} | обещание |")
        return issues(promise_lint.lint(self.proj), "MSG-09")

    def test_fixture_with_moore_channels_and_matrix_is_clean(self):  # Л-1: разделы 3, 6 и 8 шаблона в эталоне
        md = (self.proj / "out" / "comms-strategy.md").read_text(encoding="utf-8")
        for sec in ("## 3. Позиционное утверждение", "## 6. Роль каналов", "## 8. Матрица"):
            self.assertIn(sec, md)
        self.assertIn("в отличие от аналогов", md)
        rep = promise_lint.lint(self.proj)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(rep["warnings"], [])
        self.assertEqual(rep["stats"]["promises"], 6)  # матрица не считается второй таблицей обещаний

    def test_l1_competitor_comparison_still_caught(self):
        self.replace_in("out/comms-strategy.md", "в отличие от аналогов других операторов",
                        "в отличие от аналогов других операторов и надёжнее, чем у конкурентов")
        self.assertTrue(any(e.startswith("E8") for e in promise_lint.lint(self.proj)["errors"]))
        self.assertIn("E5", self.add_promise("В отличие от конкурентов, Ева уведомляет о попытке мошенничества против близкого"))

    def test_l2_normal_phrases_not_risky(self):
        for t in NORMAL_PHRASES:
            self.assertEqual(promise_lint.risky_phrases(t, affirmative_only=True), [], t)
        self.assertEqual(self.add_promise("Владелец списка получает уведомление о попытке мошенничества: всё просто, тем самым "
                                          "родители меньше рискуют"), [])

    def test_l2_first_round_variants_still_caught(self):
        for t in VARIANTS + NEW_RISKY:
            self.assertTrue(promise_lint.risky_phrases(t, affirmative_only=True), t)

    def test_n10_channel_table_checked(self):
        self.replace_in("out/comms-strategy.md", "| там настройки, всё просто: два шага |",
                        "| там настройки |\n| Приложение | подключить | Ева гарантированно защитит маму от всех мошенников — 100% | там настройки |")
        errs = [e for e in promise_lint.lint(self.proj)["errors"] if e.startswith("E9")]
        self.assertTrue(errs)
        self.assertIn("Роль каналов", errs[0])

    def test_n12_compare_shows_fragment_and_skips_quotes(self):
        text = ("## Ответ\n- Ева поможет самому защищаемому человеку.\n- Клиенты говорят: «Всё равно прорвутся».\n"
                "- Все сегментации через данные требуют согласия.\n- конкурент берёт плату [факт C-015]\n"
                "- Сделать подключение максимально лёгким.\n- Ева гарантированно защитит маму.")
        found = compare.risky(text)
        self.assertEqual(len(found), 1, found)
        self.assertIn("«гарантированно»", found[0])
        self.assertIn("защитит маму", found[0])
