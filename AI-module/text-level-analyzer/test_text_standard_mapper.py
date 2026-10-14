import unittest

from text_standard_mapper import classify_text_flag
from standard_mapping import kwcag_items_for_wcag


class TextStandardMapperTest(unittest.TestCase):
    def test_sensory_instruction_maps_through_kwcag_table(self):
        # 2026-10-13: 예전 '위치 참조'를 이름 없이 위치·색·모양·소리로만 가리키는 안내로 좁혀 대체했다.
        for kind in ('위치', '색', '모양', '소리'):
            finding = classify_text_flag(f'감각 의존 지시({kind}): "..." — ...', 'paragraph')
            self.assertEqual(('sensory_instruction', '1.3.3', 'high'),
                             (finding['type'], finding['wcag']['id'], finding['priority']), kind)
            self.assertEqual(['5.3.3'], [item['id'] for item in finding['kwcag_items']])
            self.assertEqual('명확한 지시사항 제공', finding['kwcag_items'][0]['name'])

    def test_sensory_priority_is_lower_only_for_screen_wide_up_and_down(self):
        for flag in ('감각 의존 지시(위치): "오른쪽 상단의 버튼" — 이름 없이 위치로만 가리킴',
                     '감각 의존 지시(위치): "왼쪽에서 두 번째 버튼" — 이름 없이 위치로만 가리킴',
                     '감각 의존 지시(위치): "옆의 아이콘" — 이름 없이 위치로만 가리킴',
                     '감각 의존 지시(색): "빨간색 버튼" — 이름 없이 색으로만 가리킴'):
            self.assertEqual('high', classify_text_flag(flag, 'paragraph')['priority'], flag)
        for flag in ('감각 의존 지시(위치): "화면 아래의 버튼" — 이름 없이 위치로만 가리킴',
                     '감각 의존 지시(위치): "페이지 하단 버튼" — 이름 없이 위치로만 가리킴'):
            self.assertEqual('medium', classify_text_flag(flag, 'paragraph')['priority'], flag)

    def test_old_location_flags_from_archived_results_still_map(self):
        # 2026-10-13 이전 엔진이 만든 결과 파일을 다시 처리하는 경우
        finding = classify_text_flag('위치 참조: "위" 사용', 'paragraph')

        self.assertEqual(('location_dependency', '1.3.3'), (finding['type'], finding['wcag']['id']))
        self.assertEqual(['5.3.3'], [item['id'] for item in finding['kwcag_items']])
        self.assertEqual('명확한 지시사항 제공', finding['kwcag_items'][0]['name'])

    def test_old_location_flag_severity_depends_on_direction(self):
        # 2026-10-03: 좌우·옆은 화면을 못 보면 단서가 없어 high, 위·아래는 읽는 순서와
        # 맞으면 어느 정도 통해서 medium
        for flag in ('위치 참조: "오른쪽(의)" 사용', '위치 참조: "우측(의)" 사용', '위치 참조: "옆(의)" 사용'):
            self.assertEqual('high', classify_text_flag(flag, 'paragraph')['priority'], flag)
        for flag in ('위치 참조: "위(의)" 사용', '위치 참조: "아래(의)" 사용'):
            finding = classify_text_flag(flag, 'paragraph')
            self.assertEqual(('location_dependency', '1.3.3', 'medium'),
                             (finding['type'], finding['wcag']['id'], finding['priority']), flag)

    def test_ambiguous_reference_maps_to_link_purpose(self):
        finding = classify_text_flag('모호한 참조: "여기/이곳 클릭" 사용', 'paragraph')
        self.assertEqual(('ambiguous_reference', '2.4.4', 'medium'),
                         (finding['type'], finding['wcag']['id'], finding['priority']))
        self.assertEqual(['6.4.3'], [item['id'] for item in finding['kwcag_items']])

    def test_link_length_maps_to_appropriate_link_text(self):
        finding = classify_text_flag('link 텍스트 길이 과다: 40글자', 'link')

        self.assertEqual('2.4.4', finding['wcag']['id'])
        self.assertEqual(['6.4.3'], [item['id'] for item in finding['kwcag_items']])

    def test_reading_level_remains_wcag_when_kwcag_has_no_equivalent(self):
        finding = classify_text_flag('어려운 어휘 과다', 'paragraph')

        self.assertEqual('3.1.5', finding['wcag']['id'])
        self.assertEqual([], finding['kwcag_items'])

    def test_cv_contrast_uses_the_same_mapping_source(self):
        self.assertEqual(
            [('5.4.3', '텍스트 콘텐츠의 명도 대비')],
            [(item['id'], item['name']) for item in kwcag_items_for_wcag('1.4.3')],
        )


if __name__ == '__main__':
    unittest.main()
