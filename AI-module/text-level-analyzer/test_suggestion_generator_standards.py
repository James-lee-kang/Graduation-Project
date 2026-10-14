import json
import tempfile
import unittest
from pathlib import Path

import suggestion_generator


class SuggestionGeneratorStandardsTest(unittest.TestCase):
    def test_sensory_instruction_suggestion_carries_canonical_metadata(self):
        # 2026-10-13: 이름 없이 위치·색·모양·소리로만 가리키는 안내 (예전 '위치 참조'를 대체)
        suggestion_generator.OFFLINE_MODE = True
        flags = ['감각 의존 지시(위치): "오른쪽 상단의 버튼" — 이름 없이 위치로만 가리킴',
                 '감각 의존 지시(색): "빨간색 버튼" — 이름 없이 색으로만 가리킴']
        block = {"text": "오른쪽 상단의 빨간색 버튼을 누르세요", "category": "paragraph", "flags": flags,
                 "metrics": {}, "difficulty_score": None, "needs_suggestion": True}
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "result_text_difficulty.json"
            input_path.write_text(json.dumps({"meta": {}, "results": [block]}, ensure_ascii=False),
                                  encoding="utf-8")
            result = suggestion_generator.generate_suggestions(
                str(input_path), str(Path(directory) / "out.json"))

        suggestions = result["results"][0]["suggestions"]
        self.assertEqual(["sensory_instruction", "sensory_instruction"], [s["type"] for s in suggestions])
        self.assertEqual(["high", "high"], [s["priority"] for s in suggestions])
        for item in suggestions:
            self.assertEqual("1.3.3", item["wcag_ref"]["id"])
            self.assertEqual("5.3.3", item["kwcag_items"][0]["id"])
        self.assertIn("제출", suggestions[0]["guide"])      # 위치: 이름을 함께 쓰는 예
        self.assertIn("삭제", suggestions[1]["guide"])      # 색: 이름을 함께 쓰는 예

    def test_each_sensory_kind_has_its_own_guide_and_screen_wide_position_is_medium(self):
        guides = {}
        for kind, quote in (("위치", "오른쪽 버튼"), ("색", "빨간색 버튼"), ("모양", "동그란 아이콘"),
                            ("소리", "삐 소리가 나면")):
            flag = f'감각 의존 지시({kind}): "{quote}" — ...'
            [item] = suggestion_generator.generate_rule_based_suggestion(
                {"text": "", "category": "paragraph", "flags": [flag], "metrics": {}})
            guides[kind] = item["guide"]
        self.assertEqual(4, len(set(guides.values())))
        [medium] = suggestion_generator.generate_rule_based_suggestion(
            {"text": "", "category": "paragraph", "metrics": {},
             "flags": ['감각 의존 지시(위치): "화면 아래의 버튼" — 이름 없이 위치로만 가리킴']})
        self.assertEqual("medium", medium["priority"])

    def test_old_location_flag_from_archived_results_still_gets_a_suggestion(self):
        # 2026-10-13 이전 엔진이 만든 결과 파일에 이 스크립트를 다시 돌리는 경우
        [item] = suggestion_generator.generate_rule_based_suggestion(
            {"text": "", "category": "paragraph", "flags": ['위치 참조: "오른쪽(의)" 사용'], "metrics": {}})
        self.assertEqual(("location_dependency", "high"), (item["type"], item["priority"]))

    def test_link_length_suggestion_does_not_ask_to_shorten_titles(self):
        # 2026-10-13: 기사·공지 제목이 그대로 링크 글인 경우까지 줄이라고 하지 않는다 (점수에서도 뺐다)
        [item] = suggestion_generator.generate_rule_based_suggestion(
            {"text": "가" * 40, "category": "link", "flags": ["link 텍스트 길이 과다: 40글자 (기준: 30글자)"],
             "metrics": {}})
        self.assertEqual(("link_length", "low"), (item["type"], item["priority"]))
        self.assertIn("참고 기준", item["issue"])
        self.assertIn("제목이 그대로", item["guide"])

    def test_output_carries_canonical_standard_metadata(self):
        suggestion_generator.OFFLINE_MODE = True
        payload = {
            "meta": {},
            "results": [{
                "text": "위의 복잡한 안내를 확인하세요",
                "category": "paragraph",
                "flags": ["어려운 어휘 과다", "위치 참조"],
                "metrics": {"easy_word_ratio": 0.2, "grade_detail": {}},
                "difficulty_score": 50,
                "needs_suggestion": True,
            }],
        }

        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "result_text_difficulty.json"
            output_path = Path(directory) / "result_text_suggestions.json"
            input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            result = suggestion_generator.generate_suggestions(str(input_path), str(output_path))

        block = result["results"][0]
        self.assertEqual(
            ["WCAG 3.1.5", "KWCAG 5.3.3"],
            [
                (
                    f"KWCAG {item['kwcag_items'][0]['id']}"
                    if item["kwcag_items"]
                    else f"WCAG {item['wcag']['id']}"
                )
                for item in block["standard_issues"]
            ],
        )
        self.assertEqual({"id": "3.1.5", "name": "읽기 수준", "standard": "WCAG", "version": "2.2"},
                         block["suggestions"][0]["wcag_ref"])
        self.assertEqual("5.3.3", block["suggestions"][1]["kwcag_items"][0]["id"])

    def test_ambiguous_reference_suggestion_uses_link_purpose(self):
        # 2026-10-03: "여기 클릭"·"해당 ~"은 위치 참조와 분리돼 WCAG 2.4.4(KWCAG 6.4.3)로 간다.
        suggestion_generator.OFFLINE_MODE = True
        block = {
            "text": "자세한 내용은 여기를 클릭하세요",
            "category": "paragraph",
            "flags": ['모호한 참조: "여기/이곳 클릭" 사용', '위치 참조: "아래(의)" 사용'],
            "metrics": {"grade_detail": {}},
            "difficulty_score": 10,
            "needs_suggestion": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "result_text_difficulty.json"
            input_path.write_text(json.dumps({"meta": {}, "results": [block]}, ensure_ascii=False),
                                  encoding="utf-8")
            result = suggestion_generator.generate_suggestions(
                str(input_path), str(Path(directory) / "out.json"))

        suggestions = {item["type"]: item for item in result["results"][0]["suggestions"]}
        self.assertEqual("6.4.3", suggestions["ambiguous_reference"]["kwcag_items"][0]["id"])
        self.assertEqual("medium", suggestions["ambiguous_reference"]["priority"])
        self.assertEqual("medium", suggestions["location_dependency"]["priority"])
        self.assertEqual("5.3.3", suggestions["location_dependency"]["kwcag_items"][0]["id"])


if __name__ == "__main__":
    unittest.main()
