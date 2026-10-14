"""select_survey_texts.py (2차 설문 글 선정) 테스트. MeCab 없이 엔진 결과 JSON만으로 돈다."""

import csv
import json
import tempfile
import unittest
from collections import Counter
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import select_survey_texts as sst  # noqa: E402

GL_VALUES = {"GL<5": [2.0, 3.0, 3.5, 4.0, 4.5, 4.9, 2.5, 3.2],
             "GL5-7": [5.1, 5.5, 6.0, 6.5, 6.9, 5.8, 6.2, 5.3],
             "GL7-9": [7.1, 7.5, 8.0, 8.5, 8.9, 7.8, 8.2, 7.3],
             "GL9-12": [9.1, 9.5, 10.0, 11.0, 11.9, 10.5, 9.8, 11.2],
             "GL12+": [12.0, 13.0, 14.5, 16.0, 20.0, 12.5, 15.0, 18.0]}


def paragraph(text, gl, **extra):
    block = {"text": text, "category": "paragraph", "selector": f"p#{abs(hash(text)) % 10**8}",
             "difficulty_score": min(100.0, max(0.0, (gl - 1) / 11 * 100)), "difficulty_score_v2": 50.0,
             "metrics": {"gl_score": gl, "avg_sentence_length": 10.0, "easy_word_ratio": 0.5,
                         "noun_eojeol_run": 1, "hard_noun_count": 3}, "flags": []}
    block.update(extra)
    return block


def make_sites(root: Path):
    sites = {f"0{i}_site{i}.go.kr": [] for i in range(1, 5)}
    names = list(sites)
    n = 0
    for bin_name, values in GL_VALUES.items():
        for j, gl in enumerate(values):
            n += 1
            # 짧은 글과 긴 글을 섞는다 (120자 기준)
            body = f"{bin_name} 시험 문장 {n}번입니다. 공공기관 안내 글을 흉내 낸 내용입니다."
            if j % 2:
                body += " 신청 방법과 제출 서류, 처리 기간을 자세히 설명하는 문장을 덧붙여 길이를 늘립니다." * 1
            sites[names[n % 4]].append(paragraph(body, gl))
    # 제외되어야 할 것들
    sites[names[0]] += [
        paragraph("너무 짧은 글입니다.", 3.0),                                   # 40자 미만
        paragraph("가" * 260 + ".", 8.0),                                          # 250자 초과
        {"text": "메뉴 목록 덩어리", "category": "paragraph", "difficulty_score": None, "metrics": {}, "flags": []},
        paragraph("링크 글입니다. 공식이 적용되지 않은 종류라서 빠져야 합니다.", 6.0, category="link"),
        paragraph("팝업 안의 글입니다. 점수 제외 영역이라 설문 후보가 아닙니다.", 6.0, exclusion_reason="POPUP"),
    ]
    inner = "겹친 글 확인용 문단입니다. 제목과 함께 바깥 블록에도 그대로 들어 있는 문단입니다."
    sites[names[1]] += [paragraph(inner, 6.3), paragraph("겹친 제목 " + inner, 6.4)]
    for name, blocks in sites.items():
        site = root / "sites" / name
        site.mkdir(parents=True)
        (site / "url.txt").write_text(f"https://{name.split('_', 1)[1]}/page", encoding="utf-8")
        (site / "result_text_difficulty.json").write_text(json.dumps({"results": blocks}, ensure_ascii=False),
                                                         encoding="utf-8")


class SelectSurveyTextsTest(unittest.TestCase):
    def run_selection(self, *extra):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        make_sites(root)
        code = sst.main(["--skip-run", "--out", str(root), *extra])
        rows = list(csv.DictReader((root / "selected.csv").open(encoding="utf-8-sig")))
        candidates = list(csv.DictReader((root / "candidates.csv").open(encoding="utf-8-sig")))
        return code, rows, candidates, root

    def test_selects_six_per_bin_and_two_common_texts(self):
        code, rows, _, _ = self.run_selection()
        self.assertEqual(0, code)
        unique = [r for r in rows if r["role"] == "unique"]
        self.assertEqual({name: 6 for name, _, _ in sst.GL_BINS}, dict(Counter(r["gl_bin"] for r in unique)))
        common_ids = {r["candidate_id"] for r in rows if r["role"] == "common"}
        self.assertEqual(2, len(common_ids))
        self.assertTrue(common_ids.isdisjoint({r["candidate_id"] for r in unique}))

    def test_each_form_has_twelve_texts_two_per_bin_and_one_attention_check(self):
        _, rows, _, _ = self.run_selection()
        for form in ("1", "2", "3"):
            entries = [r for r in rows if r["form"] == form]
            self.assertEqual(13, len(entries))
            self.assertEqual([str(i) for i in range(1, 14)], [r["position"] for r in entries])
            self.assertEqual(1, sum(r["role"] == "attention" for r in entries))
            self.assertEqual(2, sum(r["role"] == "common" for r in entries))
            bins = Counter(r["gl_bin"] for r in entries if r["role"] == "unique")
            self.assertEqual({name: 2 for name, _, _ in sst.GL_BINS}, dict(bins))

    def test_filters_length_category_exclusions_and_nested_duplicates(self):
        _, _, candidates, _ = self.run_selection()
        texts = [c["text"] for c in candidates]
        self.assertTrue(all(sst.MIN_CHARS <= len(t) <= sst.MAX_CHARS for t in texts))
        self.assertFalse(any("링크 글" in t or "팝업 안의 글" in t or "메뉴 목록" in t for t in texts))
        self.assertIn("겹친 글 확인용 문단입니다. 제목과 함께 바깥 블록에도 그대로 들어 있는 문단입니다.", texts)
        self.assertFalse(any(t.startswith("겹친 제목") for t in texts))

    def test_same_seed_gives_same_forms_and_writes_apps_script(self):
        _, first, _, root = self.run_selection()
        _, second, _, _ = self.run_selection()
        self.assertEqual([(r["form"], r["position"], r["text"]) for r in first],
                         [(r["form"], r["position"], r["text"]) for r in second])
        script = (root / "create_survey_forms_v2.gs").read_text(encoding="utf-8")
        self.assertIn("function createForms()", script)
        self.assertNotIn("candidate_id", script.split("const TEXT_DATA")[1].split("function")[0])
        self.assertIn('"form3"', script)

    def test_warns_and_exits_3_when_a_bin_is_short(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        site = root / "sites" / "01_only"
        site.mkdir(parents=True)
        blocks = [paragraph(f"쉬운 시험 문장 {i}번입니다. 공공기관 안내 글을 흉내 냈습니다.", 3.0 + i / 10) for i in range(8)]
        (site / "result_text_difficulty.json").write_text(json.dumps({"results": blocks}, ensure_ascii=False),
                                                         encoding="utf-8")
        self.assertEqual(3, sst.main(["--skip-run", "--out", str(root)]))
        log = json.loads((root / "selection_log.json").read_text(encoding="utf-8"))
        self.assertTrue(any("GL12+" in w for w in log["warnings"]))

    def test_sentence_count_ignores_decimal_points(self):
        self.assertEqual(1, sst.sentence_count("수수료는 3.5%이고 2026.06.22부터 적용합니다."))
        self.assertEqual(2, sst.sentence_count("최근 메뉴를 보여줍니다.메뉴가 바뀌었습니다."))


if __name__ == "__main__":
    unittest.main()
