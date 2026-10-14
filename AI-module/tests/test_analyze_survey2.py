"""analyze_survey2.py 테스트 (2026-10-09).

실제 select_survey_texts.py의 폼 배치(assign_forms)로 selected.csv를 만들고, 구글폼 응답 CSV와 같은
모양의 가짜 응답을 합성해서 분석 전체를 돌려 본다. 통계 함수는 손으로 계산한 값과 비교한다.
"""

import contextlib
import io
import json
import math
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path

AI_MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_MODULE_DIR))

import analyze_survey2 as az
import select_survey_texts as sst

RESAMPLES = 400   # 테스트는 빠르게. 같은 seed면 횟수가 같아도 결과는 같다.
FREQUENCY = "평소 공공기관 웹사이트(정부24, 건강보험공단 등)를 이용하는 빈도는 어느 정도인가요?"


def candidate(number, bin_name, latent, role_pool):
    """latent(0~1)이 클수록 어려운 글. 엔진 지표는 latent에 단조롭게 이어 둔다."""
    gl = 3 + latent * 11
    score = max(0.0, min(100.0, (gl - 1) / 11 * 100))
    run = round(latent * 6)
    return {
        "candidate_id": f"C{number:03d}", "gl_bin": bin_name, "length_group": "short" if number % 2 else "long",
        "gl_raw": round(gl, 3), "difficulty_score": round(score, 1),
        "difficulty_score_v2": round((score + max(0, min(100, (run + 1 - 1) / 6 * 100))) / 2, 1),
        "avg_sentence_length": round(8 + latent * 20, 1), "easy_word_ratio": round(0.9 - latent * 0.5, 3),
        "noun_eojeol_run": run, "hard_noun_count": round(latent * 8), "chars": 60 + (number * 37) % 170,
        "eojeols": 20, "sentences": 1, "site": f"site{number % 4}", "url": "https://example.test",
        "selector": "p", "flags": "", "text": f"글 {number}의 본문입니다.", "_latent": latent,
    }


def make_selected(directory, seed=3):
    """5개 구간 × 6개 = 고유 30개 + 공통 2개. 구간 안 latent는 고르게 퍼뜨린다."""
    bins = [name for name, _, _ in sst.GL_BINS]
    rng = random.Random(seed)
    unique, number = [], 1
    for index, name in enumerate(bins):
        for k in range(sst.PER_BIN):
            latent = (index + (k + rng.random()) / sst.PER_BIN) / len(bins)
            unique.append(candidate(number, name, latent, "unique"))
            number += 1
    common = [candidate(number, "GL5-7", 0.30, "common"), candidate(number + 1, "GL9-12", 0.70, "common")]
    rows = sst.assign_forms(common, unique, seed)
    path = Path(directory) / "selected.csv"
    sst.write_csv(path, rows, sst.SELECTED_FIELDS)
    return path, rows, {c["candidate_id"]: c for c in unique + common}


def response_header(rows_of_form):
    header = ["타임스탬프", FREQUENCY]
    for row in sorted(rows_of_form, key=lambda r: r["position"]):
        title = (f"글 {row['position']}. 응답 확인 문항입니다. 2를 선택해 주세요." if row["role"] == "attention"
                 else f"글 {row['position']}. 이 글을 이해하기 얼마나 어려웠나요?")
        header.append(title)
    return header


def write_responses(directory, rows, texts, *, per_form=20, slope=1.0, noise=0.4, seed=5,
                    bad_attention=(), name_template="[Uniaccess 2차 설문 {form}_3] 공공기관 웹 글 난이도 평가 (응답).csv"):
    """폼마다 응답자 per_form명. 체감 = 3 + slope×(latent−0.5)×4 + 응답자 편향 + 잡음, 1~5로 자름.
    bad_attention: (폼, 응답자 번호) 쌍은 응답 확인 문항에 2가 아닌 값을 넣는다."""
    rng = random.Random(seed)
    paths = {}
    for form in sorted({r["form"] for r in rows}):
        form_rows = [r for r in rows if r["form"] == form]
        lines = [response_header(form_rows)]
        for person in range(per_form):
            bias = rng.gauss(0, 0.3)
            values = [f"2026/10/10 오후 {person % 12 + 1}:00:00",
                      ["거의 이용 안 함", "가끔 이용(연 1~2회)", "종종 이용(분기 1회 이상)"][person % 3]]
            for row in sorted(form_rows, key=lambda r: r["position"]):
                if row["role"] == "attention":
                    values.append("3" if (form, person) in bad_attention else "2")
                    continue
                latent = texts[row["candidate_id"]]["_latent"]
                score = 3 + slope * (latent - 0.5) * 4 + bias + rng.gauss(0, noise)
                values.append(str(int(max(1, min(5, round(score))))))
            lines.append(values)
        path = Path(directory) / name_template.format(form=form)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            import csv
            csv.writer(f).writerows(lines)
        paths[form] = path
    return paths


def run_main(*arguments):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = az.main([str(a) for a in arguments])
    return code, out.getvalue()


class StatisticsTests(unittest.TestCase):
    def test_ranks_and_spearman_handle_ties_and_degenerate_input(self):
        self.assertEqual(az.average_ranks([10, 20, 20, 30]), [1.0, 2.5, 2.5, 4.0])
        self.assertEqual(az.average_ranks([3, 1, 2]), [3.0, 1.0, 2.0])
        self.assertAlmostEqual(az.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 1.0)
        self.assertAlmostEqual(az.spearman([1, 2, 3, 4, 5], [9, 7, 5, 3, 1]), -1.0)
        # 손 계산: 순위 [1, 2.5, 2.5, 4]와 [1, 3, 2, 4] → 4.5 / √(4.5 × 5.0)
        self.assertAlmostEqual(az.spearman([1, 2, 2, 3], [1, 3, 2, 4]), 4.5 / math.sqrt(22.5), places=9)
        self.assertIsNone(az.spearman([1, 2, 3], [7, 7, 7]), "한쪽이 모두 같으면 정의할 수 없다")

    def test_fisher_interval_uses_the_spearman_variance_not_the_pearson_one(self):
        low, high = az.fisher_ci(0.5, 32)
        # z = atanh(0.5), 표준오차 √(1.06/29) → tanh(z ± 1.96×SE)
        self.assertAlmostEqual(low, 0.1728, delta=0.001)
        self.assertAlmostEqual(high, 0.7281, delta=0.001)
        pearson_margin = az.Z95 * math.sqrt(1 / 29)
        pearson_low = math.tanh(math.atanh(0.5) - pearson_margin)
        self.assertLess(low, pearson_low, "Spearman 분산(1.06)이 더 커서 구간이 더 넓다")
        self.assertIsNone(az.fisher_ci(0.5, 3))
        self.assertIsNone(az.fisher_ci(None, 30))
        self.assertTrue(all(abs(v) < 1 for v in az.fisher_ci(1.0, 10)), "ρ=1이어도 계산이 터지지 않는다")

    def test_resampling_is_seeded_and_sensible(self):
        x = list(range(24))
        rng = random.Random(9)
        related = [v + rng.gauss(0, 3) for v in x]
        unrelated = [rng.random() for _ in x]
        rho = az.spearman(x, related)
        boot_a = az.bootstrap_ci(x, related, random.Random(1), 500)
        boot_b = az.bootstrap_ci(x, related, random.Random(1), 500)
        self.assertEqual(boot_a, boot_b)
        self.assertLess(boot_a["low"], rho)
        self.assertGreater(boot_a["high"], rho)
        self.assertLess(az.permutation_p(x, related, random.Random(2), 500), 0.01)
        self.assertGreater(az.permutation_p(x, unrelated, random.Random(2), 500), 0.05)
        self.assertEqual(az.permutation_p(x, related, random.Random(2), 500),
                         az.permutation_p(x, related, random.Random(2), 500))
        self.assertIsNone(az.permutation_p(x, [1] * len(x), random.Random(2), 50))

    def test_reliability_spearman_brown_and_form_difference(self):
        self.assertAlmostEqual(az.spearman_brown(0.6), 0.75)
        self.assertIsNone(az.spearman_brown(None))
        consistent = [[v] * 10 for v in (1, 2, 3, 4, 5, 2, 4)]   # 응답자가 모두 같은 답이면 반으로 나눠도 같다
        self.assertAlmostEqual(az.split_half_reliability(consistent, random.Random(1), 20)["mean"], 1.0)
        rng = random.Random(4)
        shaky = [[rng.randint(1, 5) for _ in range(12)] for _ in range(20)]   # 글과 무관한 응답
        self.assertLess(az.split_half_reliability(shaky, random.Random(1), 100)["mean"], 0.5)
        same = az.kruskal_wallis_permutation([[1, 2, 3, 4, 5] * 4] * 3, random.Random(1), 300)
        apart = az.kruskal_wallis_permutation([[1, 1, 2, 2] * 3, [3, 3, 4, 4] * 3, [5, 5, 5, 4] * 3],
                                              random.Random(1), 300)
        self.assertGreater(same["p"], 0.5)
        self.assertLess(apart["p"], 0.01)
        self.assertIsNone(az.kruskal_wallis_permutation([[3, 3, 3], [3, 3]], random.Random(1), 20))

    def test_verdict_rules_and_boundaries(self):
        def verdict(rho, low, baseline):
            primary = {"rho": rho, "fisher_ci": None if low is None else [low, 0.9]}
            return az.classify(primary, None if baseline is None else {"rho": baseline})

        cases = [
            ((0.62, 0.30, 0.20), "success"),
            ((0.50, 0.01, 0.20), "success"),      # 경계값 포함
            ((0.62, 0.30, None), "success"),
            ((0.62, 0.30, 0.70), "partial"),      # 글자 수보다 높지 않다
            ((0.62, 0.30, 0.62), "partial"),      # 같으면 "높음"이 아니다
            ((0.62, -0.05, 0.20), "partial"),     # 신뢰구간이 0을 포함
            ((0.40, 0.10, 0.20), "partial"),
            ((0.30, 0.01, 0.20), "partial"),      # 경계값 포함
            ((0.29, 0.01, 0.20), "failure"),
            ((-0.40, -0.70, 0.20), "failure"),
            ((None, None, None), "undetermined"),
        ]
        for arguments, status in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(verdict(*arguments)["status"], status)
        self.assertIn("글자 수", " ".join(verdict(0.62, 0.30, 0.70)["reasons"]))
        self.assertIn("신뢰구간", " ".join(verdict(0.62, -0.05, 0.20)["reasons"]))

    def test_precision_recall_and_the_threshold_matches_the_engine(self):
        c = az.confusion([True, True, False, False, True], [True, False, True, False, True])
        self.assertEqual((c["tp"], c["fp"], c["fn"], c["tn"]), (2, 1, 1, 1))
        self.assertAlmostEqual(c["precision"], 2 / 3)
        self.assertAlmostEqual(c["recall"], 2 / 3)
        none = az.confusion([False, False], [False, False])
        self.assertIsNone(none["precision"])
        self.assertIsNone(none["recall"])
        # 난이도 엔진의 기준(GL 9)과 같은 값인지, MeCab 없이 소스에서 읽어 확인한다.
        source = (AI_MODULE_DIR / "text-level-analyzer" / "difficulty_engine.py").read_text(encoding="utf-8")
        gl = float(re.search(r"^THRESHOLD_GL\s*=\s*([0-9.]+)", source, re.M).group(1))
        self.assertEqual(az.THRESHOLD_DIFFICULTY_SCORE, round((gl - 1) / 11 * 100, 1))


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.dir = Path(self._directory.name)
        self.selected, self.rows, self.texts = make_selected(self.dir)

    def analyze(self, paths, out_name="out", *extra):
        out = self.dir / out_name
        code, text = run_main("--selected", self.selected, "--responses", *paths.values(),
                              "--out", out, "--resamples", RESAMPLES, *extra)
        return code, text, out

    def test_strong_signal_is_a_success_and_writes_the_three_files(self):
        paths = write_responses(self.dir, self.rows, self.texts)
        code, text, out = self.analyze(paths)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["per_text.csv", "report.md", "summary.json"])
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["verdict"]["status"], "success")
        self.assertEqual(summary["texts"]["analyzed"], 32)
        primary = next(m for m in summary["metrics"] if m["metric"] == "difficulty_score_v2")
        self.assertGreater(primary["rho"], 0.8)
        self.assertGreater(primary["fisher_ci"][0], 0)
        self.assertLess(primary["permutation_p"], 0.01)
        self.assertGreater(summary["reliability"]["mean"], 0.8)
        report = (out / "report.md").read_text(encoding="utf-8")
        self.assertIn("**성공**", report)
        self.assertIn("엔진을 고치면", report)
        self.assertNotIn("중간 결과입니다", report, "글마다 응답이 20개면 중간 결과가 아니다")
        self.assertIn("판정: 성공", text)

    def test_reversed_relation_is_a_failure_and_few_responses_are_interim(self):
        paths = write_responses(self.dir, self.rows, self.texts, slope=-1.0, per_form=6)
        code, _, out = self.analyze(paths)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual((code, summary["verdict"]["status"]), (0, "failure"))
        self.assertTrue(summary["interim"])
        report = (out / "report.md").read_text(encoding="utf-8")
        self.assertIn("중간 결과입니다", report)
        self.assertIn("엔진을 고치지 마세요", report)

    def test_attention_check_drops_respondents_before_averaging(self):
        bad = {(1, 0), (1, 1), (2, 0)}
        paths = write_responses(self.dir, self.rows, self.texts, bad_attention=bad)
        # 응답 확인 칸을 비운 응답자도 탈락한다.
        blank = paths[3]
        text = blank.read_text(encoding="utf-8-sig").splitlines()
        cells = text[1].split(",")
        cells[2 + 6] = ""
        text[1] = ",".join(cells)
        blank.write_text("\n".join(text) + "\n", encoding="utf-8-sig")
        _, _, out = self.analyze(paths)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["respondents"]["total"], 60)
        self.assertEqual(summary["respondents"]["dropped"], 4)
        self.assertEqual(summary["respondents"]["per_form"]["1"], {"responses": 20, "passed": 18, "dropped": 2})
        per_text = {r["candidate_id"]: r for r in self._read_per_text(out)}
        form_of = {r["candidate_id"]: r["form"] for r in self.rows if r["role"] == "unique"}
        for candidate_id, form in form_of.items():
            expected = {1: 18, 2: 19, 3: 19}[form]
            self.assertEqual(int(per_text[candidate_id]["n_ratings"]), expected, candidate_id)

    def test_common_texts_collect_the_answers_of_all_three_forms(self):
        paths = write_responses(self.dir, self.rows, self.texts)
        _, _, out = self.analyze(paths)
        per_text = self._read_per_text(out)
        self.assertEqual(len(per_text), 32)
        common = [r for r in per_text if r["role"] == "common"]
        self.assertEqual(len(common), 2)
        for row in common:
            self.assertEqual((row["forms"], int(row["n_ratings"])), ("1,2,3", 60))
        for row in per_text:
            if row["role"] == "unique":
                self.assertEqual(int(row["n_ratings"]), 20)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual({c["candidate_id"] for c in summary["common_texts"]}, {r["candidate_id"] for r in common})
        self.assertEqual(set(summary["common_texts"][0]["forms"]), {"1", "2", "3"})

    def test_wrong_or_swapped_files_stop_with_code_2_and_write_nothing(self):
        paths = write_responses(self.dir, self.rows, self.texts)
        names = {f: p.name for f, p in paths.items()}

        def expect_stop(responses, message):
            out = self.dir / "stopped"
            code, text = run_main("--selected", self.selected, "--responses", *responses,
                                  "--out", out, "--resamples", RESAMPLES)
            self.assertEqual(code, az.EXIT_MISMATCH, message)
            self.assertFalse(out.exists(), "멈출 때는 아무것도 저장하지 않는다")
            self.assertIn("[중단]", text)
            return text

        # 폼 번호가 같은 파일이 둘
        copy = self.dir / names[1].replace("1_3", "1_3 (복사)")
        copy.write_bytes(paths[1].read_bytes())
        self.assertIn("폼 1", expect_stop([paths[1], copy, paths[2], paths[3]], "같은 폼 두 번"))
        # 파일 이름에서 폼 번호를 못 찾음 → "N=파일" 안내
        renamed = self.dir / "응답.csv"
        renamed.write_bytes(paths[2].read_bytes())
        self.assertIn("폼번호=파일", expect_stop([paths[1], renamed, paths[3]], "이름에 폼 번호 없음"))
        # 다른 설문(폼 4개짜리)의 파일
        other = self.dir / names[3].replace("3_3", "3_4")
        other.write_bytes(paths[3].read_bytes())
        expect_stop([paths[1], paths[2], other], "폼 개수가 다름")
        # 폼 번호가 범위 밖
        expect_stop([f"9={paths[1]}", paths[2], paths[3]], "폼 9")
        # 문항 구성이 selected.csv와 다름: 마지막 문항(글 13)이 없는 파일, 응답 확인 문항 위치가 다른 파일
        lines = paths[2].read_text(encoding="utf-8-sig").splitlines()
        short = self.dir / "짧음.csv"
        short.write_text("\n".join(",".join(l.split(",")[:-1]) for l in lines) + "\n", encoding="utf-8-sig")
        self.assertIn("글 문항", expect_stop([paths[1], f"2={short}", paths[3]], "문항 수 다름"))
        moved = self.dir / "위치.csv"
        moved.write_text(paths[2].read_text(encoding="utf-8-sig").replace("글 7. 응답 확인 문항입니다. 2를 선택해 주세요.", "글 7. 이 글을 이해하기 얼마나 어려웠나요?").replace("글 8. 이 글을", "글 8. 응답 확인 문항입니다. 2를 선택해 주세요. 이 글을"), encoding="utf-8-sig")
        self.assertIn("응답 확인 문항", expect_stop([paths[1], f"2={moved}", paths[3]], "응답 확인 위치 다름"))
        # 폼 번호를 직접 붙이면 이름이 달라도 받아들인다.
        code, _, _ = self.analyze({1: paths[1], 2: f"2={renamed}", 3: paths[3]}, "explicit")
        self.assertEqual(code, 0)

    def test_missing_form_and_sparse_texts_are_reported_not_hidden(self):
        paths = write_responses(self.dir, self.rows, self.texts)
        code, text, out = self.analyze({1: paths[1], 2: paths[2]})
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertTrue(any("폼 3의 응답 파일이 없어" in w for w in summary["warnings"]))
        self.assertEqual(summary["texts"]["analyzed"], 22, "폼 1·2의 고유 글 20개 + 공통 2개")
        self.assertIn("[경고]", text)
        # 글 하나에 응답이 최소 개수보다 적으면 그 글을 뺀다.
        thin_dir = self.dir / "thin"
        thin_dir.mkdir()
        thin = write_responses(thin_dir, self.rows, self.texts, per_form=3)
        _, _, out2 = self.analyze(thin, "thin_out", "--min-ratings", "5")
        summary2 = json.loads((out2 / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary2["texts"]["analyzed"], 2, "공통 글만 응답이 9개라 남는다")
        self.assertEqual(len(summary2["texts"]["excluded"]), 30)
        self.assertEqual(summary2["verdict"]["status"], "undetermined")

    def test_same_input_and_seed_give_byte_identical_files(self):
        paths = write_responses(self.dir, self.rows, self.texts)
        _, _, first = self.analyze(paths, "first")
        _, _, second = self.analyze(paths, "second")
        _, _, other_seed = self.analyze(paths, "other", "--seed", "7")
        for name in ("per_text.csv", "summary.json", "report.md"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)
        self.assertNotEqual((first / "summary.json").read_bytes(), (other_seed / "summary.json").read_bytes())

    def test_threshold_table_and_perceived_high_in_the_report(self):
        paths = write_responses(self.dir, self.rows, self.texts)
        _, _, out = self.analyze(paths)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        threshold = summary["threshold"]
        self.assertEqual(threshold["difficulty_score"], 72.7)
        per_text = self._read_per_text(out)
        engine_high = sum(float(r["difficulty_score"]) >= 72.7 for r in per_text)
        self.assertEqual(threshold["engine_high"], engine_high)
        c = threshold["perceived_high_median"]
        self.assertEqual(c["tp"] + c["fp"], engine_high)
        self.assertEqual(c["tp"] + c["fp"] + c["fn"] + c["tn"], 32)
        self.assertEqual(sum(r["perceived_high_median"] == "Y" for r in per_text), c["tp"] + c["fn"])
        self.assertEqual(sum(r["engine_high"] == "Y" for r in per_text), engine_high)

    @staticmethod
    def _read_per_text(out):
        import csv
        with (out / "per_text.csv").open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))


if __name__ == "__main__":
    unittest.main()
