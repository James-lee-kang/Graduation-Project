"""weights_sensitivity.py 테스트 (2026-10-13).

확인하는 것
  - 총점·등급 계산이 run_all.calculate_total_score()와 같은가 (5:3:2, 모듈 하나가 빠진 가중치 포함)
  - 피어슨·켄달 tau-b·평균 순위가 알려진 값과 같은가 (scipy가 있으면 scipy와도 비교)
  - 손으로 계산한 3개 사이트 예제와 분석 결과(총점·순위·tau·등급·분산 기여율)가 같은가
  - 결과 파일 읽기: 폴더 탐색, 사이트 이름, 제외 이유, 같은 URL 중복, 경고, 공식 버전 감지
  - 보고서·CSV·JSON 출력과 종료 코드

이 파일의 점수는 전부 시험용 값이다. 실제 사이트의 측정 결과가 아니다.
"""

import contextlib
import csv
import io
import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

AI_MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_MODULE_DIR))

import run_all
import weights_sensitivity as ws

try:
    from scipy import stats as scipy_stats
except ImportError:          # requirements.txt에는 scipy가 없다. 있을 때만 교차 확인한다
    scipy_stats = None


# ── 시험용 입력 만들기 ───────────────────────────────────────────────────────

def make_result(url, rule, text, cv, formula=True, blocks=1, analyzed_at=None, recorded_total=None):
    """run_all.build_final_result()로 실제 형식의 result_final.json 내용을 만든다. cv=None이면 CV 실패."""
    rule_result = {"score": {"score": rule}, "metadata": {"url": url}}
    meta = {"page_score": text, "score_breakdown": {"scored_paragraphs": 1 if blocks else 0}}
    if formula:
        meta["page_score_formula"] = "100 - 문단 난이도 점수 평균 (시험용)"
    paragraph = {"text": "신청 방법을 안내합니다.", "category": "paragraph", "difficulty_score": 40.0,
                 "flags": [], "metrics": {}}
    difficulty = {"meta": meta, "results": [dict(paragraph) for _ in range(blocks)]}
    cv_result = None if cv is None else {"violations": [], "summary": {"total_texts_analyzed": 10, "pass_rate": cv}}
    total = run_all.calculate_total_score(rule_result, difficulty, cv_result)
    suggestions = {**difficulty, "meta": {**meta, "suggestion_stats": {}}}
    final = run_all.build_final_result(url, rule_result, difficulty, suggestions, cv_result, None, total, 1.0, 1)
    if analyzed_at:
        final["analyzed_at"] = analyzed_at
    if recorded_total is not None:
        final["total_score"] = recorded_total
    return final


def write_result(root, folder, final):
    directory = Path(root) / folder
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "result_final.json"
    path.write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
    return path


def site(name, rule, text, cv, formula="new", warnings=None):
    """analyze()에 넣는 레코드(load_site_result가 만드는 모양)."""
    return {"path": f"{name}/result_final.json", "url": f"https://{name}.example.test/", "name": name,
            "analyzed_at": None, "scores": {"rule_based": rule, "difficulty": text, "cv": cv},
            "recorded_total": None, "recorded_grade": None, "weights_applied": None,
            "warnings": warnings or [], "text_formula": formula, "error": None}


# 손으로 계산한 예제 (모듈 점수 → 5:3:2 총점)
#   A: 90,50,100 → 45+15+20 = 80.0   B: 80,90,100 → 40+27+20 = 87.0   C: 60,70,100 → 30+21+20 = 71.0
HAND_SITES = [site("A", 90.0, 50.0, 100.0), site("B", 80.0, 90.0, 100.0), site("C", 60.0, 70.0, 100.0)]


def hand_analysis(labels=("5:3:2", "1:1:1", "0:3:2"), **kwargs):
    schemes = ws.build_schemes(list(labels[1:]))
    return ws.analyze(HAND_SITES, schemes, **kwargs)


def scheme_by_label(analysis, label):
    return next(s for s in analysis["schemes"] if s["label"] == label)


# ── run_all.py와 같은 계산인가 ───────────────────────────────────────────────

def run_all_total(rule=None, text=None, cv=None):
    """run_all.calculate_total_score()에 모듈 점수를 넣는다. None이면 그 모듈이 실패한 것으로 취급."""
    rule_result = None if rule is None else {"score": {"score": rule}}
    difficulty = None if text is None else {"meta": {"page_score": text}}
    cv_result = None if cv is None else {"violations": [], "summary": {"total_texts_analyzed": 10, "pass_rate": cv}}
    return run_all.calculate_total_score(rule_result, difficulty, cv_result)


class RunAllEquivalenceTests(unittest.TestCase):
    def test_baseline_ratio_is_the_one_run_all_uses(self):
        normalized = ws.normalize(ws.parse_scheme(ws.BASELINE_LABEL))
        self.assertAlmostEqual(run_all.WEIGHT_RULE_BASED, normalized[0], places=12)
        self.assertAlmostEqual(run_all.WEIGHT_DIFFICULTY, normalized[1], places=12)
        self.assertAlmostEqual(run_all.WEIGHT_CV, normalized[2], places=12)
        self.assertEqual(ws.BASELINE_LABEL, ws.DEFAULT_SCHEMES[0][0])

    def test_grade_matches_run_all_for_every_tenth_of_a_point(self):
        for tenth in range(0, 1001):
            total = tenth / 10
            expected = run_all_total(rule=total)
            self.assertEqual(total, expected["total_score"])
            self.assertEqual(expected["grade"], ws.grade_for(round(total, 1)), total)

    def test_baseline_total_is_identical_to_run_all(self):
        rng = random.Random(20261013)
        for _ in range(500):
            rule, text, cv = (round(rng.uniform(0, 100), 1) for _ in range(3))
            expected = run_all_total(rule, text, cv)
            total = round(ws.weighted_total({"rule_based": rule, "difficulty": text, "cv": cv},
                                            ws.parse_scheme("5:3:2")), 1)
            self.assertEqual(expected["total_score"], total, (rule, text, cv))
            self.assertEqual(expected["grade"], ws.grade_for(total))

    def test_dropping_a_module_matches_the_weight_redistribution_in_run_all(self):
        # CV가 실패한 사이트의 실제 합산 = 5:3:0, 텍스트 실패 = 5:0:2, 규칙 실패 = 0:3:2
        cases = [("5:3:0", dict(cv=None)), ("5:0:2", dict(text=None)), ("0:3:2", dict(rule=None))]
        rng = random.Random(7)
        for label, missing in cases:
            for _ in range(200):
                values = {"rule": round(rng.uniform(0, 100), 1), "text": round(rng.uniform(0, 100), 1),
                          "cv": round(rng.uniform(0, 100), 1)}
                values.update(missing)
                expected = run_all_total(values["rule"], values["text"], values["cv"])["total_score"]
                scores = {"rule_based": values["rule"] or 0, "difficulty": values["text"] or 0, "cv": values["cv"] or 0}
                total = ws.weighted_total(scores, ws.parse_scheme(label))
                # 정규화 방식이 달라(0.5/0.8 대 5/8) 반올림 경계에서 부동소수점 한 단계 차이로 0.1 갈릴 수 있다
                self.assertAlmostEqual(expected, round(total, 1), delta=0.1 + 1e-9, msg=(label, values))


# ── 통계 함수 ────────────────────────────────────────────────────────────────

class StatisticsTests(unittest.TestCase):
    def test_pearson_known_values(self):
        self.assertAlmostEqual(1.0, ws.pearson([1, 2, 3, 4], [10, 20, 30, 40]))
        self.assertAlmostEqual(-1.0, ws.pearson([1, 2, 3, 4], [4, 3, 2, 1]))
        self.assertAlmostEqual(0.8, ws.pearson([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]))

    def test_pearson_is_undefined_without_variance_or_enough_values(self):
        self.assertIsNone(ws.pearson([5, 5, 5], [1, 2, 3]))
        self.assertIsNone(ws.pearson([1, 2, 3], [7, 7, 7]))
        self.assertIsNone(ws.pearson([1], [1]))

    def test_kendall_tau_b_hand_cases(self):
        self.assertAlmostEqual(1.0, ws.kendall_tau_b([1, 2, 3, 4], [10, 20, 30, 40]))
        self.assertAlmostEqual(-1.0, ws.kendall_tau_b([1, 2, 3, 4], [4, 3, 2, 1]))
        # 쌍 6개: 일치 5, 불일치 0, y에서만 동점 1 → 5 / sqrt((6-0)*(6-1))
        self.assertAlmostEqual(5 / math.sqrt(30), ws.kendall_tau_b([1, 2, 3, 4], [1, 2, 2, 4]))
        self.assertIsNone(ws.kendall_tau_b([1, 2, 3], [5, 5, 5]))
        self.assertIsNone(ws.kendall_tau_b([1], [1]))

    @unittest.skipIf(scipy_stats is None, "scipy가 없으면 교차 확인을 건너뜀")
    def test_against_scipy_on_random_vectors_with_ties(self):
        rng = random.Random(11)
        for _ in range(60):
            n = rng.randint(4, 14)
            xs = [float(rng.randint(0, 6)) for _ in range(n)]
            ys = [float(rng.randint(0, 6)) for _ in range(n)]
            expected = scipy_stats.kendalltau(xs, ys).statistic
            ours = ws.kendall_tau_b(xs, ys)
            if math.isnan(expected):
                self.assertIsNone(ours)
            else:
                self.assertAlmostEqual(expected, ours, places=10)
            expected_r = scipy_stats.pearsonr(xs, ys).statistic if len(set(xs)) > 1 and len(set(ys)) > 1 else None
            if expected_r is None:
                self.assertIsNone(ws.pearson(xs, ys))
            else:
                self.assertAlmostEqual(expected_r, ws.pearson(xs, ys), places=10)

    @unittest.skipIf(scipy_stats is None, "scipy가 없으면 교차 확인을 건너뜀")
    def test_average_ranks_against_scipy(self):
        rng = random.Random(5)
        for _ in range(40):
            values = [float(rng.randint(0, 5)) for _ in range(rng.randint(2, 12))]
            expected = list(scipy_stats.rankdata([-v for v in values], method="average"))
            self.assertEqual(expected, ws.average_ranks(values))

    def test_average_ranks_gives_ties_the_mean_rank(self):
        self.assertEqual([1.0, 2.5, 2.5, 4.0], ws.average_ranks([90, 80, 80, 70]))
        self.assertEqual([2.0, 2.0, 2.0], ws.average_ranks([5, 5, 5]))
        self.assertEqual([3.0, 1.0, 2.0], ws.average_ranks([60, 90, 70]))

    def test_sample_sd_and_describe(self):
        self.assertAlmostEqual(math.sqrt(2.5), ws.sample_sd([1, 2, 3, 4, 5]))
        self.assertIsNone(ws.sample_sd([1]))
        described = ws.describe([4, 8, 6])
        self.assertEqual((3, 6, 4, 6, 8), (described["n"], described["mean"], described["min"],
                                             described["median"], described["max"]))
        self.assertAlmostEqual(2.0, described["sd"])

    def test_percentile_uses_nearest_rank(self):
        values = list(range(1, 101))
        self.assertEqual(5, ws.percentile(values, 5))
        self.assertEqual(95, ws.percentile(values, 95))
        self.assertEqual(100, ws.percentile(values, 100))
        self.assertEqual(1, ws.percentile(values, 0.5))


# ── 가중치 지정 ──────────────────────────────────────────────────────────────

class SchemeTests(unittest.TestCase):
    def test_parse_scheme(self):
        self.assertEqual((5.0, 3.0, 2.0), ws.parse_scheme("5:3:2"))
        self.assertEqual((50.0, 30.0, 20.0), ws.parse_scheme(" 50:30:20 "))
        self.assertEqual((0.0, 3.0, 2.0), ws.parse_scheme("0:3:2"))
        self.assertAlmostEqual(1.0, sum(ws.normalize(ws.parse_scheme("6:2:2"))))

    def test_parse_scheme_rejects_bad_input(self):
        for bad in ("5:3", "5:3:2:1", "a:b:c", "-1:3:2", "0:0:0", "nan:1:1", "inf:1:1", ""):
            with self.assertRaises(ValueError, msg=bad):
                ws.parse_scheme(bad)

    def test_default_schemes_start_with_the_current_weights(self):
        labels = [scheme["label"] for scheme in ws.build_schemes()]
        self.assertEqual("5:3:2", labels[0])
        self.assertEqual(len(ws.DEFAULT_SCHEMES), len(labels))
        self.assertEqual(len(set(labels)), len(labels))

    def test_custom_schemes_replace_the_default_list_and_skip_duplicates(self):
        schemes = ws.build_schemes(["6:2:2", "50:30:20", "3:1:1", "6:2:2"])
        # 50:30:20은 기준과, 3:1:1은 6:2:2와 비율이 같다
        self.assertEqual(["5:3:2", "6:2:2"], [scheme["label"] for scheme in schemes])

    def test_zero_weight_module_is_ignored(self):
        scores = {"rule_based": 10.0, "difficulty": 70.0, "cv": 90.0}
        self.assertAlmostEqual(80.0, ws.weighted_total(scores, (0, 1, 1)))
        self.assertAlmostEqual(40.0, ws.weighted_total(scores, (1, 1, 0)))


# ── 손으로 계산한 예제 ───────────────────────────────────────────────────────

class HandCalculatedAnalysisTests(unittest.TestCase):
    def test_totals_grades_and_ranks(self):
        analysis = hand_analysis()
        base = scheme_by_label(analysis, "5:3:2")
        self.assertEqual([80.0, 87.0, 71.0], base["totals"])
        self.assertEqual(["B", "B+", "C"], base["grades"])
        self.assertEqual([2.0, 1.0, 3.0], base["ranks"])

        equal = scheme_by_label(analysis, "1:1:1")
        self.assertEqual([80.0, 90.0, 76.7], equal["totals"])       # C = 230/3 = 76.67
        self.assertEqual(["B", "A", "C"], equal["grades"])

        no_rule = scheme_by_label(analysis, "0:3:2")
        self.assertEqual([70.0, 94.0, 82.0], no_rule["totals"])
        self.assertEqual(["C", "A", "B"], no_rule["grades"])
        self.assertEqual([3.0, 1.0, 2.0], no_rule["ranks"])

    def test_change_against_the_baseline(self):
        analysis = hand_analysis()
        baseline = scheme_by_label(analysis, "5:3:2")
        self.assertEqual((1.0, 0.0, 0, 0.0),
                         (baseline["tau_vs_baseline"], baseline["max_rank_change"],
                          baseline["grade_changes"], baseline["max_abs_total_change"]))

        equal = scheme_by_label(analysis, "1:1:1")
        self.assertAlmostEqual(1.0, equal["tau_vs_baseline"])
        self.assertEqual(0.0, equal["max_rank_change"])
        self.assertEqual(1, equal["grade_changes"])                   # B가 B+ → A
        self.assertAlmostEqual(5.7, equal["max_abs_total_change"])

        no_rule = scheme_by_label(analysis, "0:3:2")
        # 쌍 (A,B) 일치, (A,C) 불일치, (B,C) 일치 → (2-1)/3
        self.assertAlmostEqual(1 / 3, no_rule["tau_vs_baseline"])
        self.assertEqual(1.0, no_rule["max_rank_change"])             # A 2→3위, C 3→2위
        self.assertEqual(3, no_rule["grade_changes"])
        self.assertAlmostEqual(11.0, no_rule["max_abs_total_change"])  # C: 71 → 82

    def test_variance_decomposition_matches_hand_calculation(self):
        # 규칙 [90,80,60], 텍스트 [50,90,70], CV는 모두 100(분산 0)
        # Var(규칙)=233.33, Var(텍스트)=400, Cov=-100 → Var(총점)=0.25*233.33+0.09*400+2*0.15*(-100)=64.33
        base = scheme_by_label(hand_analysis(), "5:3:2")
        var_rule, var_text, cov = 700 / 3, 400.0, -100.0
        var_total = 0.25 * var_rule + 0.09 * var_text + 2 * 0.5 * 0.3 * cov
        self.assertAlmostEqual(var_total, base["total_variance"])
        self.assertAlmostEqual(0.5 * (0.5 * var_rule + 0.3 * cov) / var_total, base["variance_share"]["rule_based"])
        self.assertAlmostEqual(0.3 * (0.5 * cov + 0.3 * var_text) / var_total, base["variance_share"]["difficulty"])
        self.assertAlmostEqual(0.0, base["variance_share"]["cv"])
        self.assertAlmostEqual(1.0, sum(base["variance_share"].values()))
        self.assertAlmostEqual(0.673575, base["variance_share"]["rule_based"], places=5)

        sd_rule, sd_text = math.sqrt(var_rule), 20.0
        self.assertAlmostEqual(0.5 * sd_rule / (0.5 * sd_rule + 0.3 * sd_text), base["w_sd_share"]["rule_based"])
        self.assertAlmostEqual(0.0, base["w_sd_share"]["cv"])

        sd_total = math.sqrt(var_total)
        self.assertAlmostEqual((0.5 * var_rule + 0.3 * cov) / (math.sqrt(var_rule) * sd_total),
                               base["pearson_with_total"]["rule_based"])
        self.assertIsNone(base["pearson_with_total"]["cv"])      # CV가 모두 같으면 상관을 정할 수 없다

    def test_variance_shares_always_sum_to_one_and_a_dropped_module_gets_zero(self):
        rng = random.Random(3)
        sites = [site(f"s{i}", *(round(rng.uniform(20, 100), 1) for _ in range(3))) for i in range(12)]
        analysis = ws.analyze(sites, ws.build_schemes(), random_draws=0)
        for scheme in analysis["schemes"]:
            self.assertAlmostEqual(1.0, sum(scheme["variance_share"].values()), msg=scheme["label"])
        for label, module in (("5:3:0", "cv"), ("5:0:2", "difficulty"), ("0:3:2", "rule_based")):
            self.assertEqual(0.0, scheme_by_label(analysis, label)["variance_share"][module], label)

    def test_module_stats_and_correlations(self):
        analysis = hand_analysis()
        stats = analysis["module_stats"]
        self.assertEqual(3, stats["rule_based"]["n"])
        self.assertAlmostEqual(230 / 3, stats["rule_based"]["mean"])
        self.assertEqual(0.0, stats["cv"]["sd"])
        self.assertAlmostEqual(-100 / math.sqrt(700 / 3 * 400), analysis["module_correlations"]["rule_based~difficulty"])
        self.assertIsNone(analysis["module_correlations"]["rule_based~cv"])

    def test_needs_at_least_two_sites(self):
        with self.assertRaises(ValueError):
            ws.analyze([HAND_SITES[0]], ws.build_schemes())


class IdenticalModuleTests(unittest.TestCase):
    def test_if_all_three_modules_agree_no_weight_changes_anything(self):
        sites = [site(f"s{i}", v, v, v) for i, v in enumerate([91.2, 84.0, 77.7, 77.7, 52.3, 40.0])]
        analysis = ws.analyze(sites, ws.build_schemes(), random_draws=300, seed=1)
        for scheme in analysis["schemes"]:
            self.assertEqual(sites_ranks(analysis), scheme["ranks"], scheme["label"])
            self.assertEqual(0, scheme["grade_changes"], scheme["label"])
            self.assertAlmostEqual(1.0, scheme["tau_vs_baseline"])
        simulation = analysis["random"]
        self.assertEqual(1.0, simulation["identical_ranking_rate"])
        self.assertEqual(0.0, simulation["grade_change_rate"])
        self.assertAlmostEqual(1.0, simulation["tau"]["min"])
        self.assertEqual(0.0, simulation["max_rank_change"]["max"])


def sites_ranks(analysis):
    return scheme_by_label(analysis, "5:3:2")["ranks"]


# ── 무작위 가중치 ────────────────────────────────────────────────────────────

class RandomSimulationTests(unittest.TestCase):
    def test_same_seed_gives_the_same_result(self):
        first = hand_analysis(random_draws=500, seed=4)["random"]
        again = hand_analysis(random_draws=500, seed=4)["random"]
        self.assertEqual(first, again)

    def test_single_draw_matches_a_manual_calculation(self):
        simulation = hand_analysis(random_draws=1, spread=0.5, seed=3)["random"]
        rng = random.Random(3)
        raw = [b * rng.uniform(0.5, 1.5) for b in (5.0, 3.0, 2.0)]
        weights = [w / sum(raw) for w in raw]
        rows = [(90.0, 50.0, 100.0), (80.0, 90.0, 100.0), (60.0, 70.0, 100.0)]
        totals = [round(sum(w * x for w, x in zip(weights, row)), 1) for row in rows]
        ranks = ws.average_ranks(totals)
        self.assertEqual([[r, r] for r in ranks], simulation["rank_range"])
        self.assertEqual(1, simulation["draws"])
        self.assertEqual(1.0 if ranks == [2.0, 1.0, 3.0] else 0.0, simulation["identical_ranking_rate"])

    def test_tiny_spread_keeps_the_baseline_ranking(self):
        simulation = hand_analysis(random_draws=200, spread=0.0001, seed=2)["random"]
        self.assertEqual(1.0, simulation["identical_ranking_rate"])
        self.assertEqual(0.0, simulation["grade_change_rate"])
        self.assertEqual([[2.0, 2.0], [1.0, 1.0], [3.0, 3.0]], simulation["rank_range"])

    def test_summary_values_are_consistent(self):
        simulation = hand_analysis(random_draws=800, spread=1.0, seed=9)["random"]
        tau = simulation["tau"]
        self.assertLessEqual(tau["min"], tau["p5"])
        self.assertLessEqual(tau["p5"], tau["median"])
        self.assertLessEqual(tau["median"], 1.0)
        move = simulation["max_rank_change"]
        self.assertLessEqual(move["median"], move["p95"])
        self.assertLessEqual(move["p95"], move["max"])
        self.assertTrue(0.0 <= simulation["identical_ranking_rate"] <= 1.0)
        self.assertTrue(0.0 <= simulation["grade_change_rate"] <= 1.0)
        for low, high in simulation["rank_range"]:
            self.assertLessEqual(low, high)

    def test_zero_draws_skips_the_simulation(self):
        self.assertIsNone(hand_analysis(random_draws=0)["random"])


# ── 결과 파일 읽기 ───────────────────────────────────────────────────────────

class ResultFileTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)

    def url(self, name):
        return f"https://{name}.example.test/"

    def test_discovery_walks_folders_and_accepts_explicit_files(self):
        first = write_result(self.root, "archive/a", make_result(self.url("a"), 90, 80, 70))
        second = write_result(self.root, "archive/nested/b", make_result(self.url("b"), 90, 80, 70))
        other = self.root / "elsewhere" / "custom_name.json"
        other.parent.mkdir()
        other.write_text("{}", encoding="utf-8")
        (self.root / "archive" / "a" / "result_api.json").write_text("{}", encoding="utf-8")

        found = ws.discover_result_files([self.root / "archive", other, self.root / "missing", first])
        self.assertEqual({first.resolve(), second.resolve(), other.resolve()}, {p.resolve() for p in found})
        self.assertEqual(len(found), len({p.resolve() for p in found}))      # 같은 파일을 두 번 세지 않는다

    def test_load_reads_scores_total_and_formula(self):
        path = write_result(self.root, "a", make_result(self.url("a"), 90.04, 80.0, 70.0))
        record = ws.load_site_result(path)
        self.assertIsNone(record["error"])
        self.assertEqual(self.url("a"), record["url"])
        self.assertEqual({"rule_based": 90.0, "difficulty": 80.0, "cv": 70.0}, record["scores"])
        self.assertEqual(round(0.5 * 90.0 + 0.3 * 80.0 + 0.2 * 70.0, 1), record["recorded_total"])
        self.assertEqual("new", record["text_formula"])
        self.assertEqual("a.example.test", record["name"])       # 트래커가 없으면 주소로 표시
        self.assertEqual([], record["warnings"])

    def test_old_text_formula_is_detected(self):
        path = write_result(self.root, "old", make_result(self.url("old"), 90, 80, 70, formula=False))
        self.assertEqual("old", ws.load_site_result(path)["text_formula"])

    def test_unreadable_file_is_reported(self):
        bad = self.root / "bad" / "result_final.json"
        bad.parent.mkdir()
        bad.write_text("{not json", encoding="utf-8")
        record = ws.load_site_result(bad)
        self.assertIn("읽을 수 없는", record["error"])
        self.assertEqual("bad", record["name"])
        kept, excluded = ws.select_sites([record])
        self.assertEqual([], kept)
        self.assertEqual(1, len(excluded))

    def test_tracker_names_are_used_when_the_file_is_cp949(self):
        tracker = self.root / "site_test_tracker.csv"
        with open(tracker, "w", encoding="cp949", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["사이트", "url", "total_score"])
            writer.writerow(["정선군청", "https://a.example.test", "95"])      # 끝의 '/'가 달라도 같은 주소
        names = ws.load_tracker_names(tracker)
        path = write_result(self.root, "a", make_result(self.url("a"), 90, 80, 70))
        self.assertEqual("정선군청", ws.load_site_result(path, names)["name"])
        self.assertEqual({}, ws.load_tracker_names(self.root / "nope.csv"))
        self.assertEqual({}, ws.load_tracker_names(None))

    def test_modules_without_a_score_exclude_the_site_with_a_reason(self):
        records = [
            ws.load_site_result(write_result(self.root, "ok", make_result(self.url("ok"), 90, 80, 70))),
            ws.load_site_result(write_result(self.root, "nocv", make_result(self.url("nocv"), 90, 80, None))),
        ]
        kept, excluded = ws.select_sites(records)
        self.assertEqual(["ok"], [r["path"].split("/")[-2] for r in kept])
        self.assertEqual(1, len(excluded))
        self.assertIn("CV", excluded[0]["reason"])
        self.assertIn("점수가 없음", excluded[0]["reason"])

    def test_same_url_keeps_only_the_latest_result(self):
        old = make_result(self.url("dup"), 50, 50, 50, analyzed_at="2026-10-04T10:00:00")
        new = make_result(self.url("dup"), 90, 80, 70, analyzed_at="2026-10-13T09:30:00")
        records = [ws.load_site_result(write_result(self.root, "dup_new", new)),
                   ws.load_site_result(write_result(self.root, "dup_old", old))]
        kept, excluded = ws.select_sites(records)
        self.assertEqual(1, len(kept))
        self.assertEqual(90.0, kept[0]["scores"]["rule_based"])
        self.assertEqual(1, len(excluded))
        self.assertIn("더 최근", excluded[0]["reason"])
        self.assertTrue(excluded[0]["record"]["path"].endswith("dup_old/result_final.json"))

    def test_exclude_warned_drops_sites_with_data_quality_warnings(self):
        empty = ws.load_site_result(write_result(self.root, "empty", make_result(self.url("empty"), 90, 100, 70, blocks=0)))
        fine = ws.load_site_result(write_result(self.root, "fine", make_result(self.url("fine"), 90, 80, 70)))
        self.assertTrue(any("텍스트 블록 0개" in w for w in empty["warnings"]))
        self.assertEqual([], fine["warnings"])

        kept, _ = ws.select_sites([empty, fine])
        self.assertEqual(2, len(kept))
        kept, excluded = ws.select_sites([empty, fine], exclude_warned=True)
        self.assertEqual(["fine"], [r["name"].split(".")[0] for r in kept])
        self.assertIn("데이터 품질 경고", excluded[0]["reason"])

    def test_recorded_total_that_does_not_match_is_flagged(self):
        consistent = write_result(self.root, "ok", make_result(self.url("ok"), 90, 80, 70))
        odd = write_result(self.root, "odd", make_result(self.url("odd"), 90, 80, 70, recorded_total=60.0))
        records = [ws.load_site_result(consistent), ws.load_site_result(odd), ws.load_site_result(
            write_result(self.root, "third", make_result(self.url("third"), 70, 60, 50)))]
        analysis = ws.analyze(records, ws.build_schemes(), random_draws=0)
        notes = {s["name"].split(".")[0]: s["reconcile_note"] for s in analysis["sites"]}
        self.assertIsNone(notes["ok"])
        self.assertIsNone(notes["third"])
        self.assertIn("차이", notes["odd"])

    def test_rounding_of_module_scores_never_triggers_the_reconcile_note(self):
        rng = random.Random(21)
        for index in range(60):
            rule, text, cv = (rng.uniform(0, 100) for _ in range(3))
            final = make_result(self.url(f"r{index}"), rule, text, cv)
            record = ws.load_site_result(write_result(self.root, f"r{index}", final))
            sites = [record, ws.load_site_result(write_result(self.root, f"x{index}", make_result(self.url(f"x{index}"), 50, 50, 50))),
                     ws.load_site_result(write_result(self.root, f"y{index}", make_result(self.url(f"y{index}"), 60, 40, 30)))]
            analysis = ws.analyze(sites, ws.build_schemes(), random_draws=0)
            self.assertIsNone(analysis["sites"][0]["reconcile_note"], (rule, text, cv))

    def test_formula_counts_are_reported(self):
        records = [ws.load_site_result(write_result(self.root, name, make_result(self.url(name), 90 - i, 80, 70, formula=i % 2 == 0)))
                   for i, name in enumerate(["a", "b", "c", "d", "e"])]
        analysis = ws.analyze(records, ws.build_schemes(), random_draws=0)
        self.assertEqual({"new": 3, "old": 2}, analysis["text_formula_counts"])
        self.assertIn("섞여 있습니다", ws.render_report(analysis))


# ── 보고서와 명령줄 ──────────────────────────────────────────────────────────

class ReportTests(unittest.TestCase):
    def test_report_has_every_section_and_the_hand_calculated_numbers(self):
        report = ws.render_report(hand_analysis(random_draws=50, seed=1))
        for heading in ("[1] 사이트별 모듈 점수와 분포", "[2] 현재 가중치(5:3:2)의 실제 영향", "[3] 가중치 방식별 총점(등급)",
                        "[4] 5:3:2 대비 변화", "[5] 무작위 가중치 50개", "[해석 주의]"):
            self.assertIn(heading, report)
        self.assertIn("87.0(B+)", report)
        self.assertIn("94.0(A)", report)
        self.assertIn("0.33", report)            # 0:3:2의 켄달 tau
        self.assertIn("67/33/0%", report)         # 5:3:2의 분산 기여율
        self.assertIn("Paruolo", report)

    def test_report_without_random_has_no_section_5(self):
        self.assertNotIn("[5]", ws.render_report(hand_analysis(random_draws=0)))

    def test_warned_sites_are_marked(self):
        sites = [site("A", 90.0, 50.0, 100.0, warnings=["텍스트 블록 0개: 시험"]), HAND_SITES[1], HAND_SITES[2]]
        report = ws.render_report(ws.analyze(sites, ws.build_schemes(), random_draws=0))
        self.assertIn("A *", report)
        self.assertIn("텍스트 블록 0개: 시험", report)
        self.assertIn("--exclude-warned", report)

    def test_old_formula_only_is_called_out(self):
        sites = [site(n, r, t, c, formula="old") for n, r, t, c in
                 (("A", 90.0, 50.0, 100.0), ("B", 80.0, 90.0, 100.0), ("C", 60.0, 70.0, 100.0))]
        report = ws.render_report(ws.analyze(sites, ws.build_schemes(), random_draws=0))
        self.assertIn("10/13 이전 텍스트 점수 공식", report)

    def test_display_width_counts_hangul_as_two_columns(self):
        self.assertEqual(4, ws.display_width("가나"))
        self.assertEqual(3, ws.display_width("a가"))
        self.assertEqual("가나  ", ws.pad("가나", 6))
        self.assertEqual("  가나", ws.pad("가나", 6, "right"))
        self.assertEqual("abcde...", ws.shorten("abcdefghijklmnop", 8))
        self.assertEqual("short", ws.shorten("short", 8))

    def test_safe_print_survives_an_encoding_that_cannot_show_hangul(self):
        stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        original = sys.stdout
        sys.stdout = stream
        try:
            ws.safe_print("가나다 abc")
            stream.flush()
        finally:
            sys.stdout = original
        self.assertIn(b"abc", stream.buffer.getvalue())


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)

    def populate(self, count=5, with_empty_text=False):
        rng = random.Random(8)
        for i in range(count):
            blocks = 0 if (with_empty_text and i == 0) else 1
            write_result(self.root / "archive", f"s{i}",
                         make_result(f"https://s{i}.example.test/", round(rng.uniform(50, 95), 1),
                                     round(rng.uniform(10, 100), 1), round(rng.uniform(40, 100), 1), blocks=blocks))

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ws.main([str(a) for a in args])
        return code, out.getvalue()

    def test_runs_on_a_folder_and_writes_csv_and_json(self):
        self.populate(5)
        csv_path, json_path = self.root / "out.csv", self.root / "out.json"
        code, output = self.run_main(self.root / "archive", "--tracker", self.root / "none.csv", "--random", "100",
                                     "--csv", csv_path, "--json", json_path)
        self.assertEqual(0, code)
        self.assertIn("분석 대상 5곳", output)
        self.assertIn("[해석 주의]", output)

        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(5 * len(ws.DEFAULT_SCHEMES), len(rows))
        self.assertEqual(ws.CSV_FIELDS, list(rows[0].keys()))
        baseline_rows = [r for r in rows if r["scheme"] == "5:3:2"]
        self.assertTrue(all(r["delta_total"] == "0.0" and r["grade_changed"] == "N" for r in baseline_rows))

        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual("5:3:2", data["baseline"])
        self.assertEqual(5, len(data["sites"]))
        self.assertEqual(len(ws.DEFAULT_SCHEMES), len(data["schemes"]))
        self.assertEqual(100, data["random"]["draws"])
        for scheme in data["schemes"]:
            self.assertEqual(5, len(scheme["totals"]))

    def test_custom_schemes_and_no_simulation(self):
        self.populate(4)
        code, output = self.run_main(self.root / "archive", "--tracker", self.root / "none.csv",
                                     "--scheme", "6:2:2", "--scheme", "45:35:20", "--random", "0")
        self.assertEqual(0, code)
        self.assertIn("6:2:2", output)
        self.assertIn("45:35:20", output)
        self.assertNotIn("1:1:1", output)
        self.assertNotIn("[5]", output)

    def test_exclude_warned_flag(self):
        self.populate(5, with_empty_text=True)
        _, output = self.run_main(self.root / "archive", "--tracker", self.root / "none.csv", "--random", "0")
        self.assertIn("분석 대상 5곳", output)
        self.assertIn("*", output)
        code, output = self.run_main(self.root / "archive", "--tracker", self.root / "none.csv", "--random", "0",
                                     "--exclude-warned")
        self.assertEqual(0, code)
        self.assertIn("분석 대상 4곳", output)
        self.assertIn("제외: s0.example.test", output)

    def test_too_few_sites_stops_with_exit_code_1(self):
        self.populate(2)
        code, output = self.run_main(self.root / "archive", "--tracker", self.root / "none.csv")
        self.assertEqual(1, code)
        self.assertIn("최소 3곳", output)

    def test_no_files_stops_with_exit_code_1(self):
        code, output = self.run_main(self.root / "empty")
        self.assertEqual(1, code)
        self.assertIn("찾지 못했습니다", output)
        self.assertIn("경로를 찾을 수 없습니다", output)

    def test_bad_arguments_exit_through_argparse(self):
        for args in (["--scheme", "5:3"], ["--random", "-1"], ["--spread", "0"], ["--spread", "101"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                ws.main(args)
            self.assertEqual(2, raised.exception.code, args)

    def test_csv_columns_are_in_the_documented_order(self):
        self.assertEqual(["site", "url", "scheme", "weights_percent"], ws.CSV_FIELDS[:4])
        self.assertEqual("grade_changed", ws.CSV_FIELDS[-1])


if __name__ == "__main__":
    unittest.main()
