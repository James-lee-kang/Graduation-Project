"""record_result.py 테스트 (2026-10-09 개정분).

run_all.py의 build_final_result()로 만든 실제 형식의 result_final.json을 쓴다.
"""

import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

AI_MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_MODULE_DIR))

import record_result
import run_all

URL = "https://www.example.test"
HEADER = ["사이트", "url", "site_type", "test_date", "step1_rule_based", "step2_text_extract",
          "step3_difficulty", "step4_suggestion", "step5_cv", "total_score", "grade",
          "data_quality_warning", "warning_detail", "notes"]


def paragraph(text="신청 방법을 안내합니다. 필요한 서류를 준비하세요.", score=40.0):
    return {"text": text, "category": "paragraph", "difficulty_score": score, "flags": [], "metrics": {}}


def difficulty(results=None, scored=None):
    results = [paragraph()] if results is None else results
    breakdown = {} if scored is None else {"scored_paragraphs": scored}
    return {"meta": {"page_score": 80.0, "score_breakdown": breakdown}, "results": results}


def suggestions(diff):
    return {**diff, "meta": {**diff["meta"], "suggestion_stats": {}}}


def cv(measured=True):
    count = 10 if measured else 0
    return {"violations": [], "summary": {"total_texts_analyzed": count,
                                          "pass_rate": 90.0 if measured else None}}


def rule(**metadata):
    return {"score": {"score": 90}, "metadata": {"url": URL, **metadata}}


def final_result(url=URL, rule_result="default", diff="default", cv_result="default"):
    rule_result = rule() if rule_result == "default" else rule_result
    diff = difficulty() if diff == "default" else diff
    cv_result = cv() if cv_result == "default" else cv_result
    total = run_all.calculate_total_score(rule_result, diff, cv_result)
    return run_all.build_final_result(url, rule_result, diff, suggestions(diff) if diff else None,
                                      cv_result, None, total, 1.0, 1)


class RecordResultTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.root = Path(self._directory.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.tracker = self.root / "tracker.csv"
        self.write_tracker([{"사이트": "예시", "url": URL, "notes": "직접 쓴 메모 / [자동] 예전 항목"}])

    def write_tracker(self, rows):
        with open(self.tracker, "w", encoding="cp949", newline="") as f:   # 윈도우 엑셀 기본
            writer = csv.DictWriter(f, fieldnames=HEADER)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in HEADER})

    def write_output(self, name, data):
        (self.output / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def write_complete_run(self, final=None, files=("result_api.json", "result_text.json",
                                                   "result_text_difficulty.json",
                                                   "result_text_suggestions.json", "result_cv.json")):
        self.write_output("result_final.json", final or final_result())
        for name in files:
            self.write_output(name, rule() if name == "result_api.json" else {})

    def record(self, *extra, url=URL):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = record_result.main([url, "--output-dir", str(self.output), "--tracker", str(self.tracker),
                                       "--date", "2026-10-09", *extra])
        return code, out.getvalue()

    def row(self, index=0):
        with open(self.tracker, encoding="cp949", newline="") as f:
            return list(csv.DictReader(f))[index]

    def test_complete_run_fills_the_row_and_keeps_the_manual_note(self):
        self.write_output("result.json", {"meta": {"replaySource": "RENDERED_DOM"}})
        popups = [{"index": 0, "x": 0, "y": 0, "width": 10, "height": 10}]
        regions = [{"reason": "AD"}, {"reason": "AD"}, {"reason": "DYNAMIC"}]
        self.write_complete_run(final_result(rule_result=rule(popup_layers=popups, excluded_regions=regions)))
        code, _ = self.record("--note", "정상")
        row = self.row()
        self.assertEqual(code, 0)
        self.assertEqual([row[k] for k in HEADER[4:9]], ["O"] * 5)
        self.assertEqual((row["total_score"], row["grade"]), ("87.0", "B+"))
        self.assertEqual((row["data_quality_warning"], row["warning_detail"]), ("N", ""))
        notes = row["notes"].split(" / ")
        self.assertEqual(notes[:2], ["직접 쓴 메모", "정상"])
        self.assertNotIn("[자동] 예전 항목", notes)
        self.assertIn("[자동] 레이어 팝업 1개(점수 제외)", notes)
        self.assertIn("[자동] 제외 영역 3개(AD 2개, DYNAMIC 1개, 점수 제외)", notes)
        self.assertTrue((self.output / "_archive" / "www_example_test" / "result_final.json").exists())
        self.tracker.read_bytes().decode("cp949")   # 기존 인코딩(cp949)을 그대로 유지한다

    def test_blocked_page_records_the_reason_instead_of_a_bare_x(self):
        # run_all.py는 차단·빈 문서면 result_final.json을 만들지 않고 이 표식만 남긴 채 멈춘다.
        # 리다이렉트된 주소(metadata.url)는 요청한 주소와 달라도 정상이다.
        self.write_output("result_api.json", {"metadata": {"url": "https://plus.gov.kr/mbuster",
                                                           "document_health": {"status": "BLOCKED"}}})
        code, _ = self.record()
        row = self.row()
        self.assertEqual(code, 0)
        self.assertEqual([row[k] for k in HEADER[4:9]], ["X"] * 5)
        self.assertEqual((row["total_score"], row["grade"]), ("", ""))
        self.assertEqual(row["data_quality_warning"], "Y")
        self.assertIn("보안 확인·자동 접근 차단 화면", row["warning_detail"])
        self.assertIn("BLOCKED", row["warning_detail"])
        self.assertIn("[자동] 분석 중단: 보안 확인·자동 접근 차단 화면이 표시되었습니다", row["notes"])
        self.assertNotIn("result_final.json 없음", row["notes"])

    def test_scan_of_another_site_is_not_counted_as_a_rule_success(self):
        # 10/14 실측: gov.kr → plus.gov.kr, 홍익대 → 봇 확인 화면. run.js는 점수까지 낸 결과를 남기지만
        # run_all.py는 종료 코드 2로 멈춘다. 예전에는 step1 O, 경고 N으로 적혔다.
        for moved_to in ("https://plus.gov.kr/", "https://cdn-botmanager.stclab.com/sample/challenge/index.html"):
            with self.subTest(moved_to=moved_to):
                for name in list(self.output.iterdir()):
                    if name.is_file():
                        name.unlink()
                self.write_output("result_api.json", {"score": {"score": 93}, "metadata": {"url": moved_to}})
                self.write_output("result_artifact.json", {"requestedUrl": URL})
                code, _ = self.record()
                row = self.row()
                self.assertEqual(code, 0)
                self.assertEqual([row[k] for k in HEADER[4:9]], ["X"] * 5)
                self.assertEqual(row["data_quality_warning"], "Y")
                self.assertIn("요청한 사이트가 아닌 주소로 이동", row["warning_detail"])
                self.assertIn(moved_to, row["warning_detail"])
                self.assertIn("[자동] 분석 중단: 다른 주소로 이동", row["notes"])

    def test_same_site_redirect_still_counts(self):
        self.assertIsNone(record_result.redirected_elsewhere(
            "https://www.example.test", {"metadata": {"url": "https://example.test/main/index.do"}}))
        self.assertEqual("https://other.test/", record_result.redirected_elsewhere(
            "https://www.example.test", {"metadata": {"url": "https://other.test/"}}))
        # 같은 사이트 안의 차단 관문 (10/14 plus.gov.kr 95.6점 오판정)
        self.assertEqual("https://plus.gov.kr/mbuster/Mbuster_T", record_result.redirected_elsewhere(
            "https://plus.gov.kr", {"metadata": {"url": "https://plus.gov.kr/mbuster/Mbuster_T"}}))
        self.assertIsNone(record_result.redirected_elsewhere(
            "https://plus.gov.kr", {"metadata": {"url": "https://plus.gov.kr/mbusterguide"}}))

    def test_unmeasured_cv_is_x_with_a_warning_and_no_null_mismatch_note(self):
        self.write_complete_run(final_result(cv_result=cv(measured=False)))
        self.record()
        row = self.row()
        self.assertEqual(row["step5_cv"], "X")
        self.assertEqual([row[k] for k in HEADER[4:8]], ["O"] * 4)
        self.assertEqual(row["data_quality_warning"], "Y")
        self.assertIn("CV 측정 불가", row["warning_detail"])
        self.assertIn("NO_TEXT_DETECTED", row["warning_detail"])
        self.assertNotIn("[자동경고]", row["notes"], "result_cv.json은 있어도 측정 불가는 불일치가 아니다")

    def test_failed_cv_or_text_module_is_warned_but_the_score_is_kept(self):
        # 10/17 건보·복지부: CV 캡처 시간 초과 → 규칙·텍스트만으로 총점(62.5:37.5). 점수는 그대로
        # 기록하되, 다른 사이트와 바로 비교할 수 없다는 경고를 붙인다.
        cases = (
            (dict(cv_result=None), "step5_cv", "CV 측정 실패", "텍스트 난이도 결과 없음"),
            (dict(diff=None), "step3_difficulty", "텍스트 난이도 결과 없음", "CV 측정 실패"),
        )
        for kwargs, step, expected, other in cases:
            with self.subTest(expected=expected):
                final = final_result(**kwargs)
                self.write_complete_run(final)
                self.record()
                row = self.row()
                self.assertEqual(row[step], "X")
                self.assertEqual(row["step1_rule_based"], "O")
                self.assertEqual(row["total_score"], str(final["total_score"]))
                self.assertNotEqual(row["total_score"], "")
                self.assertEqual(row["data_quality_warning"], "Y")
                self.assertIn(expected, row["warning_detail"])
                self.assertNotIn(other, row["warning_detail"])
                self.assertNotIn("규칙 결과 없음", row["warning_detail"])

    def test_empty_text_and_no_formula_paragraphs_are_warned_separately(self):
        button = {"text": "로그인", "category": "button", "difficulty_score": None, "flags": [], "metrics": {}}
        cases = (
            (difficulty(results=[]), "텍스트 블록 0개", "난이도 공식을 적용한 문단 0개"),
            (difficulty(results=[button], scored=0), "난이도 공식을 적용한 문단 0개", "텍스트 블록 0개"),
            (difficulty(results=[button]), "난이도 공식을 적용한 문단 0개", "텍스트 블록 0개"),   # 10/9 이전 결과
        )
        for diff, expected, other in cases:
            with self.subTest(expected=expected, scored=diff["meta"]["score_breakdown"]):
                self.write_complete_run(final_result(diff=diff))
                self.record()
                row = self.row()
                self.assertEqual(row["data_quality_warning"], "Y")
                self.assertIn(expected, row["warning_detail"])
                self.assertNotIn(other, row["warning_detail"])
        self.write_complete_run(final_result(diff=difficulty(scored=1)))
        self.record()
        self.assertEqual(self.row()["data_quality_warning"], "N")

    def test_static_fallback_is_flagged_from_result_json(self):
        self.write_output("result.json", {"meta": {"replaySource": "INITIAL_RESPONSE_STATIC"}})
        self.write_complete_run()
        self.record()
        row = self.row()
        self.assertEqual(row["data_quality_warning"], "Y")
        self.assertIn("정적 fallback", row["warning_detail"])

    def test_result_of_another_url_stops_without_changing_anything(self):
        self.write_complete_run(final_result(url="https://other.test/"))
        before = self.tracker.read_bytes()
        code, text = self.record()
        self.assertEqual(code, record_result.EXIT_URL_MISMATCH)
        self.assertIn("다른 URL", text)
        self.assertEqual(self.tracker.read_bytes(), before)
        self.assertFalse((self.output / "_archive").exists())
        self.assertFalse(self.tracker.with_suffix(".csv.bak").exists())
        # 경로 끝 '/'나 대소문자 차이는 같은 주소다.
        self.write_complete_run(final_result(url="HTTPS://WWW.Example.test/"))
        self.assertEqual(self.record()[0], 0)
        # 일부러 다른 결과를 기록하려면 --force
        self.write_complete_run(final_result(url="https://other.test/"))
        self.assertEqual(self.record("--force")[0], 0)

    def test_missing_rule_result_is_reported_and_unknown_urls_are_refused(self):
        self.write_complete_run(final_result(rule_result=None))
        self.record()
        row = self.row()
        self.assertEqual(row["step1_rule_based"], "X")
        self.assertEqual(row["data_quality_warning"], "Y")
        self.assertIn("규칙 결과 없음", row["warning_detail"])
        # 10/17 홍익대: run_all은 이때 total_score 0인 진단용 결과를 남기고 종료 코드 3으로 멈춘다.
        # 그 0점을 기록표에 옮기면 "0점 F"로 보이므로 비워 둔다.
        self.assertEqual((row["total_score"], row["grade"]), ("", ""))
        self.assertIn("[자동] 점수 없음", row["notes"])
        # 트래커에 없는 주소는 --allow-new 없이는 아무것도 하지 않는다.
        before = self.tracker.read_bytes()
        self.assertEqual(self.record(url="https://typo.test")[0], 1)
        self.assertEqual(self.tracker.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
