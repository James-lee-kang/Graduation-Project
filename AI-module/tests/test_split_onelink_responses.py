"""split_onelink_responses.py 테스트: 한 링크 응답 → 묶음별 CSV → analyze_survey2.py가 그대로 읽는지."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analyze_survey2 as an  # noqa: E402
import select_survey_texts as sst  # noqa: E402
import split_onelink_responses as sp  # noqa: E402

# 묶음마다 글 3개 + 응답 확인 1개(2번)인 작은 폼
LAYOUT = {g: {1: {"role": "unique"}, 2: {"role": "attention"}, 3: {"role": "common"}, 4: {"role": "unique"}}
          for g in (1, 2, 3)}


def title(group, position, role):
    body = "응답 확인 문항입니다. 2를 선택해 주세요." if role == "attention" else "이 글을 이해하기 얼마나 어려웠나요?"
    return f"묶음 {group} · 글 {position}. {body}"


def onelink_header():
    header = ["타임스탬프", sst.ONELINK_CONSENT_QUESTION,
              "평소 공공기관 웹사이트(정부24, 건강보험공단 등)를 이용하는 빈도는 어느 정도인가요? (선택)",
              sst.ONELINK_GROUP_QUESTION]
    for group, layout in LAYOUT.items():
        header += [title(group, p, row["role"]) for p, row in layout.items()]
    return header


def response(group, ratings, frequency="가끔 이용(연 1~2회)", extra=None):
    row = ["2026/10/17 10:00:00", sst.ONELINK_CONSENT_YES, frequency, sst.ONELINK_GROUP_CHOICES[group - 1]]
    for g in LAYOUT:
        row += [str(ratings[i]) if g == group else (extra or {}).get((g, i + 1), "") for i in range(4)]
    return row


class SplitOneLinkTest(unittest.TestCase):
    def test_splits_by_birth_month_and_analysis_reads_each_group(self):
        rows = [response(1, [3, 2, 4, 5]), response(1, [1, 3, 2, 2]),        # 두 번째는 응답 확인 실패
                response(2, [2, 2, 2, 2], extra={(1, 1): "5"}),               # 다른 묶음 칸 값은 무시
                response(3, [4, 2, 1, 5]),
                ["2026/10/17 10:05:00", sst.ONELINK_CONSENT_YES] + [""] * 14,                    # 달 없음
                ["2026/10/17 10:06:00", sst.ONELINK_CONSENT_NO] + [""] * 14]                     # 동의 안 함
        groups, stats = sp.split(onelink_header(), rows)
        self.assertEqual({1: 2, 2: 1, 3: 1}, stats["per_group"])
        self.assertEqual(1, stats["no_group"])
        self.assertEqual(1, stats["not_consented"])
        self.assertEqual(1, stats["other_group_values_ignored"])
        self.assertTrue(all(not t.startswith("묶음") for t in groups[2][0]))

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        out = Path(directory.name)
        source = out / "응답.csv"
        with source.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows([onelink_header(), *rows])
        self.assertEqual(0, sp.main([str(source), "--out", str(out / "split")]))
        files = an.assign_response_files([str(p) for p in sorted((out / "split").glob("*.csv"))], 3)
        self.assertEqual([1, 2, 3], sorted(files))
        first = an.read_form_responses(files[1], 1, LAYOUT[1])
        self.assertEqual([True, False], [r["passed"] for r in first["respondents"]])
        self.assertEqual({1: 3.0, 2: 2.0, 3: 4.0, 4: 5.0}, first["respondents"][0]["ratings"])
        self.assertEqual("가끔 이용(연 1~2회)", first["respondents"][0]["frequency"])
        second = an.read_form_responses(files[2], 2, LAYOUT[2])
        self.assertEqual({1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0}, second["respondents"][0]["ratings"])

    def test_rejects_three_form_csv(self):
        header = ["타임스탬프", "글 1. 이 글을 이해하기 얼마나 어려웠나요?"]
        with self.assertRaises(ValueError):
            sp.split(header, [["t", "3"]])


if __name__ == "__main__":
    unittest.main()
