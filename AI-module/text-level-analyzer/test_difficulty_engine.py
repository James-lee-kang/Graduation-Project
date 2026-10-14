"""difficulty_engine.py의 위반 기준 테스트 (2026-10-02 기준 조정분).

MeCab과 mecab-ko-dic이 필요하다(엔진 실행 환경과 같음).
"""

import unittest

import difficulty_engine as de
from text_extractor import extract_texts


def block(text, category='paragraph', **attributes):
    return {'text': text, 'category': category, 'tag': '', 'selector': '', 'attributes': attributes}


def flags_of(text, category='paragraph', **attributes):
    return de.analyze_block(block(text, category, **attributes))['flags']


class SensoryInstructionTest(unittest.TestCase):
    """2026-10-13: 위치 의존 표현 검사를 WCAG 1.3.3에 맞춰 '감각 의존 지시'로 좁혔다."""

    @staticmethod
    def kinds(text):
        return [flag.split('(')[1].split(')')[0] for flag in de.detect_sensory_instructions(text)]

    def test_generic_target_pointed_to_by_position_is_flagged(self):
        for text in ('오른쪽 버튼을 누르세요', '오른쪽 메뉴에서 선택하세요', '화면 좌측 메뉴를 이용하세요',
                     '우측 표를 참고하세요', '오른쪽상단 검색창에 입력하세요', '옆의 아이콘을 눌러 주세요',
                     '왼쪽에서 두 번째 버튼을 누르세요', '오른쪽 상단의 버튼을 클릭하세요'):
            self.assertEqual(['위치'], self.kinds(text), text)

    def test_position_written_together_with_the_name_is_not_a_violation(self):
        # WCAG 1.3.3은 "감각 정보만으로" 가리키는 것을 문제 삼는다. 이름이 같이 있으면 지킨 것이다.
        for text in ("오른쪽 상단의 '로그인' 버튼을 클릭하세요", '우측 상단의 로그인 버튼을 누르세요',
                     '오른쪽 버튼(저장)을 누르세요', '화면 오른쪽 위의 "검색" 버튼을 누르세요',
                     '페이지 하단의 이전/다음 버튼을 누르세요', '위의 신청서를 작성한 뒤 오른쪽의 제출 버튼을 누르세요'):
            self.assertEqual([], de.detect_sensory_instructions(text), text)

    def test_reading_order_references_are_not_violations(self):
        # 읽는 순서상 앞뒤를 가리키는 참조는 스크린리더도 같은 순서로 읽는다.
        for text in ('위의 표를 참고하세요', '아래 버튼을 눌러 신청하세요', '아래 표를 참고하세요',
                     '다음 링크 중 하나를 선택하세요'):
            self.assertEqual([], de.detect_sensory_instructions(text), text)

    def test_screen_edge_position_is_flagged(self):
        self.assertEqual(['위치'], self.kinds('화면 아래의 버튼을 눌러 주세요'))
        self.assertEqual(['위치'], self.kinds('페이지 하단 버튼을 클릭하세요'))

    def test_color_shape_and_sound_instructions_are_flagged(self):
        self.assertEqual(['색'], self.kinds('빨간색 버튼을 누르세요'))
        self.assertEqual(['색'], self.kinds('파란 글씨로 표시된 링크를 클릭하세요'))
        self.assertEqual(['모양'], self.kinds('동그란 아이콘을 눌러 주세요'))
        self.assertEqual(['모양'], self.kinds('화살표 모양의 버튼을 클릭하세요'))
        self.assertEqual(['소리'], self.kinds('삐 소리가 나면 말씀해 주세요'))
        self.assertEqual(['소리'], self.kinds('신호음이 들리면 번호를 입력하세요'))

    def test_one_flag_per_kind_in_a_fixed_order(self):
        flags = de.detect_sensory_instructions('오른쪽 빨간 버튼을 누르세요. 왼쪽 메뉴도 선택하세요.')
        self.assertEqual(['위치', '색'], self.kinds('오른쪽 빨간 버튼을 누르세요. 왼쪽 메뉴도 선택하세요.'))
        self.assertEqual('오른쪽 빨간 버튼', flags[0].split('"')[1])

    def test_flag_text_names_the_kind_and_quotes_the_phrase(self):
        self.assertEqual(['감각 의존 지시(위치): "오른쪽 상단의 버튼" — 이름 없이 위치로만 가리킴'],
                         de.detect_sensory_instructions('오른쪽 상단의 버튼을 클릭하세요'))
        self.assertEqual(['감각 의존 지시(소리): "삐 소리가 나면" — 소리 신호에만 의존'],
                         de.detect_sensory_instructions('삐 소리가 나면 말씀해 주세요'))

    def test_mouse_and_keyboard_names_are_not_screen_positions(self):
        for text in ('마우스 오른쪽 버튼을 클릭하세요', '오른쪽 마우스 버튼을 클릭하세요',
                     '오른쪽 방향키를 누르면 다음 장으로 이동합니다'):
            self.assertEqual([], de.detect_sensory_instructions(text), text)

    def test_other_meanings_of_the_same_words_are_not_flagged(self):
        for text in ('박스오피스 2위 하락', '만족도 조사 1위 기관', '좌측통행을 지켜 주세요', '페이지 상단으로 이동',
                     '오른쪽 창문을 여세요', '노란우산공제 링크를 클릭하세요', '빨간불이 켜지면 멈추세요',
                     '소리가 나면 고장입니다', '위원회 버튼을 누르세요'):
            self.assertEqual([], de.detect_sensory_instructions(text), text)

    def test_descriptions_and_control_names_are_not_instructions(self):
        # 조작을 시키는 말이 없으면 안내가 아니라 설명이거나 버튼 이름이다.
        for text in ('왼쪽 메뉴는 부서별 안내입니다', '오른쪽 메뉴 닫기', '왼쪽 화살표 이동',
                     '신청서는 오른쪽 하단 신청 버튼으로 제출합니다'):
            self.assertEqual([], de.detect_sensory_instructions(text), text)

    def test_ambiguous_reference_is_kept_and_stays_separate(self):
        self.assertEqual([], de.detect_sensory_instructions('해당 버튼을 눌러 주세요'))
        self.assertEqual(['모호한 참조: "해당 ~" 사용'], de.detect_ambiguous_references('해당 버튼을 눌러 주세요'))
        self.assertEqual(['모호한 참조: "여기/이곳 클릭" 사용'], de.detect_ambiguous_references('여기를 클릭하세요'))
        # 한꺼번에 부르는 함수는 감각 의존 지시가 앞, 모호한 참조가 뒤
        both = de.detect_reference_flags('오른쪽 버튼을 누르세요. 해당 메뉴를 확인하세요.')
        self.assertTrue(both[0].startswith(de.SENSORY_FLAG_PREFIX))
        self.assertTrue(both[1].startswith('모호한 참조'))

    def test_old_function_name_still_works_for_old_scripts(self):
        self.assertIs(de.detect_location_dependency, de.detect_reference_flags)

    def test_real_survey_texts_get_no_false_positive(self):
        import csv, os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'study_pairs_scored.csv')
        if not os.path.exists(path):
            self.skipTest('study_pairs_scored.csv 없음')
        with open(path, encoding='utf-8-sig', newline='') as f:
            texts = [row[key] for row in csv.DictReader(f) for key in ('original_text', 'revised_text') if row.get(key)]
        self.assertGreaterEqual(len(texts), 100)
        for text in texts:
            self.assertEqual([], de.detect_sensory_instructions(text), text[:40])

    def test_every_category_checks_sensory_instructions(self):
        for category in ('paragraph', 'link', 'button', 'table', 'list', 'alert', 'other'):
            result = de.analyze_block(block('오른쪽 버튼을 누르세요', category))
            self.assertTrue(any(f.startswith(de.SENSORY_FLAG_PREFIX) for f in result['flags']), category)
            self.assertTrue(result['needs_suggestion'], category)
            self.assertEqual(['sensory_instruction'], [i['type'] for i in result['standard_issues']], category)

    def test_reading_order_reference_makes_no_flag_in_any_category(self):
        for category in ('paragraph', 'link', 'button', 'table', 'list', 'alert', 'other'):
            result = de.analyze_block(block('위의 표를 참고하세요', category))
            self.assertEqual([], result['flags'], category)


class SensoryCountTest(unittest.TestCase):
    """같은 글이 여러 블록에 겹쳐도 한 번만 센다(2026-10-03). 2026-10-13부터는 점수가 아니라 참고 건수."""

    @staticmethod
    def flagged(text, flag='감각 의존 지시(위치): "오른쪽 버튼" — 이름 없이 위치로만 가리킴'):
        return {'text': text, 'flags': [flag]}

    def test_nested_blocks_with_the_same_sentence_count_once(self):
        sentence = '오른쪽 버튼을 누르면 신청서가 열립니다'
        results = [
            self.flagged(sentence),                       # paragraph
            self.flagged(sentence + ' 바로가기'),          # 그 문장을 품은 link
            self.flagged('안내 ' + sentence + ' 바로가기'),  # 그 link를 품은 list
            self.flagged(sentence),                       # other (같은 글)
        ]
        self.assertEqual(1, de.count_flagged_texts(results, de.SENSORY_FLAG_PREFIX))

    def test_two_different_sentences_inside_one_list_count_twice(self):
        first, second = '오른쪽 버튼을 누르세요', '왼쪽 메뉴에서 고르세요'
        results = [self.flagged(first), self.flagged(second), self.flagged(f'{first} {second}')]
        self.assertEqual(2, de.count_flagged_texts(results, de.SENSORY_FLAG_PREFIX))

    def test_ambiguous_reference_is_not_counted_as_sensory(self):
        results = [self.flagged('여기를 클릭하세요', '모호한 참조: "여기/이곳 클릭" 사용'),
                   {'text': '평범한 글', 'flags': []}]
        self.assertEqual(0, de.count_flagged_texts(results, de.SENSORY_FLAG_PREFIX))


class ShortTextVocabularyTest(unittest.TestCase):
    def test_ui_text_gets_no_vocabulary_violation(self):
        # UI 문구 어휘 검사는 오탐이 많아 넣지 않았다. 개수만 기록한다.
        result = de.analyze_block(block('보험료 납부 확인서 발급', 'link'))
        self.assertGreaterEqual(result['metrics']['hard_noun_count'], 2)
        self.assertFalse(any('어려운 어휘' in f for f in result['flags']))
        self.assertFalse(result['needs_suggestion'])

    def test_short_paragraph_vocab_flag_carries_standard_metadata(self):
        from text_standard_mapper import classify_text_flag
        finding = classify_text_flag('어려운 어휘 포함(표본 부족): 명사 2개 중 어려운 단어 2개', 'paragraph')
        self.assertEqual(('short_text_hard_vocab', '3.1.5'), (finding['type'], finding['wcag']['id']))


class SentenceLengthTest(unittest.TestCase):
    NAME_LIST = ' '.join(['강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구',
                          '금천구', '노원구', '도봉구', '동대문구', '동작구', '마포구', '서대문구',
                          '서초구', '성동구', '성북구', '송파구', '양천구', '영등포구', '용산구',
                          '은평구', '종로구', '중구', '중랑구', '자치구'])
    LONG_SENTENCE = ('소득에 대하여 보험료 조정과 정산을 신청한 경우 다음 해 11월에 국세청 등에서 '
                     '확인한 소득으로 조정한 연도의 보험료를 다시 산정하여 그 차액을 부과하거나 '
                     '돌려주는 제도로서 신청한 사람에게만 적용되며 신청하지 않으면 적용되지 않습니다.')

    def test_list_of_names_without_punctuation_is_not_a_long_sentence(self):
        for category in ('list', 'paragraph'):
            flags = flags_of(self.NAME_LIST, category)
            self.assertFalse(any('문장 길이 과다' in f for f in flags), category)

    def test_real_long_sentence_is_flagged(self):
        self.assertGreaterEqual(len(self.LONG_SENTENCE.split()), de.THRESHOLD_SENTENCE_LENGTH)
        for category in ('list', 'paragraph'):
            flags = flags_of(self.LONG_SENTENCE, category)
            self.assertTrue(any('문장 길이 과다' in f for f in flags), category)

    def test_decimal_point_alone_is_not_a_sentence_end(self):
        self.assertFalse(de.has_sentence_terminator('수수료 3.5% 2026.06.22'))
        self.assertTrue(de.has_sentence_terminator('수수료는 3.5%입니다.'))


class VocabularyTest(unittest.TestCase):
    def test_proper_nouns_are_not_counted(self):
        self.assertNotIn('서울', de.extract_common_nouns('서울 시민을 위한 안내'))
        _, _, nouns, _ = de.calc_easy_word_ratio('서울 시민을 위한 안내')
        self.assertNotIn('서울', nouns)

    def test_one_hard_word_in_short_text_is_not_flagged(self):
        flags = flags_of('검색')
        self.assertFalse(any('표본 부족' in f for f in flags))

    def test_two_hard_words_in_short_text_are_flagged(self):
        result = de.analyze_block(block('보험료 납부 확인'))
        self.assertTrue(any('표본 부족' in f for f in result['flags']))
        self.assertTrue(result['needs_suggestion'])

    def test_difficulty_threshold_is_lower_secondary_level(self):
        # WCAG 3.1.5: 중학교 수준(초등 입학 후 9년)을 넘는 글
        self.assertEqual(9.0, de.THRESHOLD_GL)
        self.assertAlmostEqual(72.7, de.THRESHOLD_DIFFICULTY_SCORE)
        self.assertEqual(de.THRESHOLD_DIFFICULTY_SCORE, de.gl_to_difficulty_score(de.THRESHOLD_GL))

    def test_vocab_ratio_alone_does_not_make_an_easy_paragraph_a_violation(self):
        # 쉬운 단어 비율은 60% 미만이지만 난이도 점수는 기준 아래인 글
        result = de.analyze_block(block('학교 급식 식단과 영양 정보를 안내합니다. 가정 통신문을 확인하세요.'))
        self.assertLess(result['metrics']['easy_word_ratio'], de.EASY_WORD_RATIO_MIN)
        self.assertLess(result['difficulty_score'], de.THRESHOLD_DIFFICULTY_SCORE)
        self.assertFalse(any('어려운 어휘 과다' in f for f in result['flags']))
        self.assertFalse(result['needs_suggestion'])

    def test_vocab_ratio_explains_a_paragraph_over_the_threshold(self):
        result = de.analyze_block(block('어려운 행정 용어와 법령 조항 해석에 관한 질의 회신 사례집 발간 및 '
                                        '배포 계획 공고 통지 처분 집행을 알립니다.'))
        self.assertGreaterEqual(result['difficulty_score'], de.THRESHOLD_DIFFICULTY_SCORE)
        self.assertTrue(any('어려운 어휘 과다' in f for f in result['flags']))
        self.assertTrue(result['needs_suggestion'])

    def test_paragraph_over_the_threshold_always_has_a_flag(self):
        # 쉬운 단어 비율이 60% 이상이라 어휘 플래그가 없고, 평균 문장이 25어절 미만이라
        # 문장 길이 플래그도 없는데 점수는 기준을 넘는 글(10개 사이트 실측 사례)
        result = de.analyze_block(block('누각과 정자문화를 이해하고 체험할 수 있는 문화공간, '
                                        '사랑하는 사람들과 함께 아름다운 추억을 만들어보세요.'))
        self.assertGreaterEqual(result['difficulty_score'], de.THRESHOLD_DIFFICULTY_SCORE)
        self.assertGreaterEqual(result['metrics']['easy_word_ratio'], de.EASY_WORD_RATIO_MIN)
        self.assertTrue(any('읽기 수준 초과' in f for f in result['flags']))
        self.assertTrue(result['needs_suggestion'])
        self.assertEqual(['reading_level'], [i['type'] for i in result['standard_issues']])
        from suggestion_generator import generate_rule_based_suggestion
        self.assertEqual(['reading_level'],
                         [s['type'] for s in generate_rule_based_suggestion(result)])

    def test_reading_level_flag_is_not_added_when_a_cause_is_flagged(self):
        result = de.analyze_block(block('어려운 행정 용어와 법령 조항 해석에 관한 질의 회신 사례집 발간 및 '
                                        '배포 계획 공고 통지 처분 집행을 알립니다.'))
        self.assertFalse(any('읽기 수준 초과' in f for f in result['flags']))


class SentenceGateTest(unittest.TestCase):
    """2026-10-04: Jo 공식은 문장 끝 부호가 있는 문단에만 쓴다."""

    MENU = '상단영역 바로가기 서비스 메뉴 바로가기 새소식 블록 바로가기 쇼핑 블록 바로가기 관심사 블록 바로가기'
    BOARD = '공지사항 학생생활규정 개정 안내 2026-09-14 학교도서관 희망도서 신청 안내 2026-09-07 방과후 프로그램 지도계획'

    def test_menu_or_board_list_without_terminator_gets_no_formula(self):
        for text in (self.MENU, self.BOARD):
            result = de.analyze_block(block(text))
            self.assertIsNone(result['difficulty_score'], text)
            self.assertEqual('no_sentence_terminator', result['metrics']['jo_skipped'])
            self.assertGreaterEqual(result['metrics']['total_noun_count'], 5)
            self.assertEqual([], result['flags'], text)
            self.assertFalse(result['needs_suggestion'])

    def test_same_words_written_as_a_sentence_get_the_formula(self):
        result = de.analyze_block(block('학생생활규정 개정 안내와 학교도서관 희망도서 신청 안내, '
                                        '방과후 프로그램 지도계획을 공지합니다.'))
        self.assertIsNotNone(result['difficulty_score'])
        self.assertNotIn('jo_skipped', result['metrics'])

    def test_decimal_point_is_not_a_sentence_terminator(self):
        result = de.analyze_block(block('수수료 3.5% 인상 시행 일정 2026.06.22 관련 부서 담당자 연락처 목록'))
        self.assertIsNone(result['difficulty_score'])

    def test_page_score_ignores_lists_without_terminator(self):
        import json, os, tempfile
        blocks = [block(self.MENU), block('학교 급식 식단과 영양 정보를 안내합니다. 가정 통신문을 확인하세요.')]
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'result_text.json')
            with open(source, 'w', encoding='utf-8') as f:
                json.dump({'blocks': blocks}, f, ensure_ascii=False)
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                output = de.analyze(source, os.path.join(directory, 'out.json'))
        self.assertEqual(1, sum(1 for r in output['results'] if r['difficulty_score'] is not None))


class PageAverageNestingTest(unittest.TestCase):
    """2026-10-09: 제목을 품은 바깥 글과 안쪽 글이 둘 다 문단이면 안쪽 글만 페이지 평균에 쓴다."""

    INNER = '학교 급식 식단과 영양 정보를 안내합니다. 가정 통신문을 확인하세요.'
    OUTER = '2학기 급식 운영 계획 ' + INNER
    OTHER = ('수급자 선정 기준에 따른 소득인정액 산정 절차와 부양의무자 기준 완화 여부를 '
             '관계 법령에 근거하여 심사한 결과를 개별 통지합니다.')

    @staticmethod
    def run_page(blocks):
        import contextlib, io, json, os, tempfile
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'result_text.json')
            with open(source, 'w', encoding='utf-8') as f:
                json.dump({'blocks': blocks}, f, ensure_ascii=False)
            with contextlib.redirect_stdout(io.StringIO()):
                return de.analyze(source, os.path.join(directory, 'out.json'))

    def test_outer_block_holding_an_inner_paragraph_is_not_averaged_twice(self):
        output = self.run_page([block(self.OUTER), block(self.INNER), block(self.OTHER)])
        by_text = {r['text']: r for r in output['results']}
        inner, outer, other = (by_text[t] for t in (self.INNER, self.OUTER, self.OTHER))
        # 세 블록 모두 공식이 적용되고 블록 점수는 그대로다.
        for r in (inner, outer, other):
            self.assertIsNotNone(r['difficulty_score'])
        self.assertNotEqual(inner['difficulty_score'], outer['difficulty_score'])
        # 페이지 평균에는 바깥 글을 빼고 안쪽 글과 다른 문단 둘만 들어간다.
        breakdown = output['meta']['score_breakdown']
        self.assertEqual(2, breakdown['scored_paragraphs'])
        self.assertEqual(round((inner['difficulty_score'] + other['difficulty_score']) / 2, 1),
                         breakdown['avg_difficulty_deduction'])
        self.assertEqual(round((inner['metrics']['gl_score'] + other['metrics']['gl_score']) / 2, 2),
                         output['meta']['readability']['avg_gl_score'])
        self.assertEqual([inner, other], de.innermost_scored_paragraphs([outer, inner, other]))

    def test_scored_paragraph_count_tells_nothing_to_measure_from_a_perfect_page(self):
        menu = '상단영역 바로가기 서비스 메뉴 바로가기 새소식 블록 바로가기 쇼핑 블록 바로가기 관심사 블록 바로가기'
        empty = self.run_page([block(menu), block('로그인', 'button')])
        self.assertEqual(0, empty['meta']['score_breakdown']['scored_paragraphs'])
        self.assertEqual(0.0, empty['meta']['score_breakdown']['avg_difficulty_deduction'])
        self.assertEqual(100.0, empty['meta']['page_score'])   # "쉽다"가 아니라 "잴 문장이 없다"
        # 완전히 같은 글이 서로 다른 블록으로 두 번 있으면 겹침이 아니므로 둘 다 센다.
        twice = self.run_page([block(self.INNER), block(self.INNER)])
        self.assertEqual(2, twice['meta']['score_breakdown']['scored_paragraphs'])


class PairScoringTest(unittest.TestCase):
    """2026-10-09: compute_pair_difficulty.py를 결과 파일에 다시 돌려도 flags가 쌓이지 않는다."""

    def test_rerun_on_scored_output_gives_the_same_file(self):
        import csv, os, subprocess, sys, tempfile
        here = os.path.dirname(os.path.abspath(__file__))
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'pairs.csv')
            with open(source, 'w', encoding='utf-8-sig', newline='') as f:
                # 실제 study_pairs.csv처럼 원문 점수 칸이 미리 있는 파일이어야 한다.
                writer = csv.DictWriter(f, fieldnames=['pair_id', 'difficulty_score', 'avg_sentence_length',
                                                       'easy_word_ratio', 'flags', 'original_text', 'revised_text'])
                writer.writeheader()
                writer.writerow({'pair_id': 1, 'flags': '메모', 'original_text': '오른쪽 버튼을 눌러 신청하세요',
                                 'revised_text': '신청 버튼을 누르세요'})
            first, second = (os.path.join(directory, name) for name in ('first.csv', 'second.csv'))
            for src, dst in ((source, first), (first, second)):
                subprocess.run([sys.executable, os.path.join(here, 'compute_pair_difficulty.py'), src, dst],
                               check=True, capture_output=True, cwd=here)
            with open(first, 'rb') as a, open(second, 'rb') as b:
                self.assertEqual(a.read(), b.read())
            with open(first, encoding='utf-8-sig', newline='') as f:
                flags = next(csv.DictReader(f))['flags']
        self.assertTrue(flags.startswith('메모; '))
        self.assertEqual(1, flags.count('감각 의존 지시'))


class WebInterfaceWordsTest(unittest.TestCase):
    """2026-10-04: 누리집 기능 이름은 학습용 목록 등급과 관계없이 쉬운 단어(W)."""

    def test_interface_words_count_as_easy(self):
        for word in ('로그인', '검색', '검색어', '입력', '게시판', '안내', '누리집', '챗', '봇'):
            self.assertEqual('W', de.get_word_grade(word), word)
            self.assertIn(de.get_word_grade(word), de.EASY_GRADES)

    def test_content_words_stay_hard(self):
        for word in ('입찰', '법령', '민원', '행정', '보건', '인증', '재난'):
            self.assertIn(de.get_word_grade(word), ('C', 'D'), word)

    def test_easy_listed_words_keep_their_grade(self):
        self.assertEqual(de.VOCAB_GRADES['메뉴'], de.get_word_grade('메뉴'))

    def test_list_only_holds_words_the_learner_list_calls_hard(self):
        import json, os
        with open(os.path.join(os.path.dirname(de.__file__), 'web_common_words.json'), encoding='utf-8') as f:
            entries = [e for group in json.load(f)['words'].values() for e in group]
        self.assertEqual(len(entries), len(de.WEB_COMMON_WORDS))
        for entry in entries:
            self.assertIn(de.VOCAB_GRADES.get(entry['word'], 'D'), ('C', 'D'), entry['word'])

    def test_short_ui_like_paragraphs_are_no_longer_flagged(self):
        for text in ('로그인 회원가입', '기관 검색 전체보기', '챗봇 상담', '검색어를 입력해 주세요'):
            self.assertFalse(any('어려운 어휘' in f for f in flags_of(text)), text)

    def test_short_paragraph_with_hard_content_words_is_still_flagged(self):
        self.assertTrue(any('어려운 어휘 포함' in f for f in flags_of('재난적의료비 지원사업')))


class NounStackingTest(unittest.TestCase):
    def test_counts_noun_only_eojeols_in_a_row(self):
        # 쉬운 우리말 쓰기 캠페인 예시: "이전 통계 조사의 / 사후 평가 결과 반영"
        self.assertEqual(4, de.longest_noun_eojeol_run('이전 통계 조사의 사후 평가 결과 반영'))
        self.assertEqual(6, de.longest_noun_eojeol_run('소득 부과 건강보험료 조정 정산 제도'))

    def test_particles_and_predicates_break_the_run(self):
        self.assertLess(de.longest_noun_eojeol_run('소득에 따라 건강보험료를 조정하고 정산하는 제도입니다.'), 3)

    def test_comma_lists_dates_and_english_are_not_stacking(self):
        self.assertEqual(1, de.longest_noun_eojeol_run('사업, 근로, 이자, 배당, 연금, 기타소득'))
        self.assertLessEqual(de.longest_noun_eojeol_run('2026년 9월 16일 개최 안내'), 2)
        self.assertEqual(0, de.longest_noun_eojeol_run("I haven't heard from him in ages."))

    def test_compound_written_as_one_word_counts_once(self):
        self.assertEqual(1, de.longest_noun_eojeol_run('국민건강보험공단'))

    def test_flag_only_for_sentences(self):
        sentence = '소득 부과 건강보험료 조정 정산 제도를 안내합니다.'
        result = de.analyze_block(block(sentence))
        self.assertTrue(any('명사 나열' in f for f in result['flags']))
        self.assertTrue(result['needs_suggestion'])
        label = de.analyze_block(block('소득 부과 건강보험료 조정 정산 제도', 'link'))
        self.assertFalse(any('명사 나열' in f for f in label['flags']))

    def test_short_noun_phrase_is_not_flagged(self):
        result = de.analyze_block(block('건강보험 납부 확인서를 발급받을 수 있습니다.'))
        self.assertFalse(any('명사 나열' in f for f in result['flags']))

    def test_v2_is_the_unweighted_mean_of_two_subscores(self):
        self.assertEqual(0.0, de.noun_stacking_score(1))
        self.assertEqual(50.0, de.noun_stacking_score(de.NOUN_STACK_MIN_EOJEOLS))
        self.assertEqual(100.0, de.noun_stacking_score(de.NOUN_STACK_FULL_EOJEOLS + 3))
        self.assertEqual(65.0, de.calc_difficulty_score_v2(80.0, 4))
        self.assertIsNone(de.calc_difficulty_score_v2(None, 4))

    def test_paragraph_result_carries_v2_and_metrics(self):
        result = de.analyze_block(block('학교 급식 식단과 영양 정보를 안내합니다. 가정 통신문을 확인하세요.'))
        self.assertIsNotNone(result['difficulty_score_v2'])
        self.assertIn('noun_eojeol_run', result['metrics'])
        self.assertIn('hard_noun_count', result['metrics'])

    def test_flag_maps_to_reading_level_and_gets_a_template(self):
        from text_standard_mapper import classify_text_flag
        from suggestion_generator import generate_rule_based_suggestion
        flag = '명사 나열: 조사 없이 명사만으로 된 어절 6개 연속 (기준: 4개)'
        finding = classify_text_flag(flag, 'paragraph')
        self.assertEqual(('noun_stacking', '3.1.5'), (finding['type'], finding['wcag']['id']))
        suggestions = generate_rule_based_suggestion(
            {'text': '', 'category': 'paragraph', 'flags': [flag], 'metrics': {'noun_eojeol_run': 6}})
        self.assertEqual(['noun_stacking'], [s['type'] for s in suggestions])


class FormGuideDuplicateTest(unittest.TestCase):
    LONG = ('보건복지부 전문임기제 나급 공무원(첨단재생의료사무국) 경력경쟁채용시험 '
            '최종합격자 공고 게시물로 이동')

    def test_title_repeating_visible_text_is_not_length_checked(self):
        self.assertGreater(len(self.LONG), de.MAX_TEXT_LENGTH['form_guide'])
        flags = flags_of(self.LONG, 'form_guide', source='title', duplicates_visible_text=True)
        self.assertFalse(any('텍스트 길이 과다' in f for f in flags))

    def test_standalone_long_guide_is_still_length_checked(self):
        flags = flags_of(self.LONG, 'form_guide', source='placeholder')
        self.assertTrue(any('텍스트 길이 과다' in f for f in flags))

    def test_extractor_marks_title_that_repeats_visible_text(self):
        html = ('<html><body>'
                '<a href="/1" title="채용시험 최종합격자 공고 게시물로 이동">채용시험 최종합격자 공고</a>'
                '<a href="/2" title="새 창에서 열림">자세히 보기</a>'
                '<button aria-label="메뉴 열기"><img src="m.png" alt=""></button>'
                '<input placeholder="검색어를 입력하세요">'
                '</body></html>')
        guides = {b['text']: b['attributes'] for b in extract_texts(html)['blocks']
                  if b['category'] == 'form_guide'}
        self.assertTrue(guides['채용시험 최종합격자 공고 게시물로 이동'].get('duplicates_visible_text'))
        self.assertNotIn('duplicates_visible_text', guides['새 창에서 열림'])
        self.assertNotIn('duplicates_visible_text', guides['메뉴 열기'])
        self.assertNotIn('duplicates_visible_text', guides['검색어를 입력하세요'])


class PageScoreTest(unittest.TestCase):
    """2026-10-13: 페이지 점수는 문단 난이도 평균만 반영한다. 위치 의존·UI 길이 감점은 뺐다."""

    PARAGRAPH = '학교 급식 식단과 영양 정보를 안내합니다. 가정 통신문을 확인하세요.'
    SENSORY = '오른쪽 버튼을 누르세요'
    LONG_LINK = '보건복지부 전문임기제 나급 공무원 경력경쟁채용시험 최종합격자 공고 게시물로 이동 안내'

    @staticmethod
    def run_page(blocks):
        return PageAverageNestingTest.run_page(blocks)

    def test_page_score_is_100_minus_the_average_difficulty(self):
        output = self.run_page([block(self.PARAGRAPH)])
        paragraph = output['results'][0]
        self.assertEqual(round(100 - paragraph['difficulty_score'], 1), output['meta']['page_score'])

    def test_flags_without_penalty(self):
        base = self.run_page([block(self.PARAGRAPH)])
        noisy = self.run_page(
            [block(self.PARAGRAPH)]
            + [block(self.SENSORY, 'paragraph'), block('오른쪽 메뉴를 선택하세요', 'list')]
            + [block(self.LONG_LINK + str(i), 'link') for i in range(15)])
        # 감각 의존 지시와 긴 링크는 플래그와 수정 제안으로는 남는다
        flagged = [r for r in noisy['results'] if r['flags']]
        self.assertTrue(any(f.startswith(de.SENSORY_FLAG_PREFIX) for r in flagged for f in r['flags']))
        self.assertTrue(any('텍스트 길이 과다' in f for r in flagged for f in r['flags']))
        self.assertTrue(all(r['needs_suggestion'] for r in flagged))
        # 페이지 점수는 둘이 같다 (예전에는 3×2 + 2×15 = 36점이 더 빠졌다)
        self.assertEqual(base['meta']['page_score'], noisy['meta']['page_score'])

    def test_breakdown_keeps_reference_counts_but_no_penalty_fields(self):
        output = self.run_page([block(self.PARAGRAPH), block(self.SENSORY, 'list'),
                                block(self.LONG_LINK, 'link'), block(self.LONG_LINK + '2', 'link')])
        breakdown = output['meta']['score_breakdown']
        self.assertEqual(1, breakdown['scored_paragraphs'])
        self.assertEqual(1, breakdown['sensory_instruction_texts'])
        self.assertEqual(2, breakdown['ui_length_flags'])
        for removed in ('location_penalty', 'location_occurrences', 'length_penalty'):
            self.assertNotIn(removed, breakdown)
        self.assertIn('2026-10-13', output['meta']['page_score_formula'])

    def test_page_without_measurable_paragraph_is_100_even_with_flags(self):
        output = self.run_page([block(self.SENSORY, 'button'), block(self.LONG_LINK, 'link')])
        self.assertEqual(100.0, output['meta']['page_score'])
        self.assertEqual(0, output['meta']['score_breakdown']['scored_paragraphs'])
        self.assertEqual(2, output['meta']['flagged_count'])


class GlTargetsTest(unittest.TestCase):
    """2026-10-13: 기준(GL 9)을 정한 식에서 거꾸로 계산한 목표값."""

    def test_worked_example(self):
        # 평균 12어절, 쉬운 단어 45% → 난이도 92.1점
        self.assertEqual(92.1, de.gl_to_difficulty_score(de.calc_gl_score(12, 0.45)))
        self.assertEqual({'max_avg_sentence_length': 8.4, 'min_easy_word_ratio': 0.686},
                         de.calc_gl_targets(12, 0.45))

    def test_targets_land_on_the_threshold_and_not_beyond(self):
        for avg_len, easy in ((12, 0.45), (10.5, 0.30), (14, 0.60), (9, 0.20), (8, 0.0)):
            targets = de.calc_gl_targets(avg_len, easy)
            self.assertLessEqual(de.calc_gl_score(targets['max_avg_sentence_length'], easy), de.THRESHOLD_GL)
            self.assertGreater(de.calc_gl_score(targets['max_avg_sentence_length'] + 0.1, easy), de.THRESHOLD_GL - 0.01)
            ratio = targets['min_easy_word_ratio']
            self.assertLessEqual(de.calc_gl_score(avg_len, ratio), de.THRESHOLD_GL)
            self.assertGreater(de.calc_gl_score(avg_len, ratio - 0.002), de.THRESHOLD_GL)

    def test_long_sentences_cannot_be_fixed_by_vocabulary_alone(self):
        # 쉬운 단어 100%여도 GL = 4.874 + 0.591×A − 9.201 > 9 이면 어휘만으로는 못 맞춘다 (A > 약 22.6어절)
        self.assertIsNone(de.calc_gl_targets(25, 0.9)['min_easy_word_ratio'])
        self.assertIsNotNone(de.calc_gl_targets(22, 0.9)['min_easy_word_ratio'])
        self.assertGreaterEqual(de.calc_gl_targets(25, 0.9)['max_avg_sentence_length'], 6.98)

    def test_block_carries_targets_only_when_over_the_threshold(self):
        over = de.analyze_block(block('누각과 정자문화를 이해하고 체험할 수 있는 문화공간, '
                                      '사랑하는 사람들과 함께 아름다운 추억을 만들어보세요.'))
        self.assertGreaterEqual(over['difficulty_score'], de.THRESHOLD_DIFFICULTY_SCORE)
        targets = over['metrics']['gl_targets']
        self.assertLess(targets['max_avg_sentence_length'], over['metrics']['avg_sentence_length'])
        under = de.analyze_block(block('학교 급식 식단과 영양 정보를 안내합니다. 가정 통신문을 확인하세요.'))
        self.assertNotIn('gl_targets', under['metrics'])
        short = de.analyze_block(block('수수료는 3.5%입니다. 2026.06.22부터 시행합니다.'))
        self.assertNotIn('gl_targets', short['metrics'])

    def test_suggestions_state_the_target(self):
        from suggestion_generator import generate_rule_based_suggestion
        result = de.analyze_block(block('누각과 정자문화를 이해하고 체험할 수 있는 문화공간, '
                                        '사랑하는 사람들과 함께 아름다운 추억을 만들어보세요.'))
        guide = generate_rule_based_suggestion(result)[0]['guide']
        targets = result['metrics']['gl_targets']
        self.assertEqual('reading_level', generate_rule_based_suggestion(result)[0]['type'])
        self.assertIn(f"{targets['max_avg_sentence_length']:.1f}어절 이하", guide)
        self.assertIn(f"{targets['min_easy_word_ratio'] * 100:.1f}% 이상", guide)

    def test_long_sentence_suggestion_asks_to_split(self):
        from suggestion_generator import generate_rule_based_suggestion
        result = de.analyze_block(block(SentenceLengthTest.LONG_SENTENCE))
        guides = {s['type']: s['guide'] for s in generate_rule_based_suggestion(result)}
        self.assertIn('문장을 나눠야 합니다', guides['sentence_length'])
        self.assertIn(f"{result['metrics']['gl_targets']['max_avg_sentence_length']:.1f}어절 이하", guides['sentence_length'])

    def test_suggestions_without_targets_keep_the_old_wording(self):
        from suggestion_generator import generate_rule_based_suggestion
        old = generate_rule_based_suggestion(
            {'text': '', 'category': 'paragraph', 'flags': ['문장 길이 과다: 평균 30.0어절 (기준: 25어절)'],
             'metrics': {'avg_sentence_length': 30.0}})
        self.assertTrue(old[0]['guide'].endswith('마침표로 나누면 됩니다.'))


class FrozenFormulaTest(unittest.TestCase):
    """
    블록 단위 점수는 2026-10-04에 고정한 값이다 (설문 응답을 받은 뒤 엔진을 고치면 검증이 아니라
    맞추기가 된다). 2026-10-13 개편(감점 제거·탐지기 교체·목표값 추가)이 이 값을 건드리지 않았는지
    10/4 엔진이 낸 값과 비교해 고정한다. 공식이나 어휘 목록을 일부러 바꿀 때만 이 값을 고친다.
    """

    # 글, (난이도 점수, 종합 난이도 v2, 평균 문장 길이, 쉬운 단어 비율, GL)
    CASES = (
        ('학교 급식 식단과 영양 정보를 안내합니다. 가정 통신문을 확인하세요.', (45.0, 30.9, 4.5, 0.556, 5.95)),
        ('민원 신청은 누리집에서 하실 수 있습니다. 신청서를 내려받아 작성한 뒤 제출해 주세요. '
         '처리 결과는 문자로 알려 드립니다.', (60.4, 30.2, 5.67, 0.4, 7.64)),
        ('누각과 정자문화를 이해하고 체험할 수 있는 문화공간, 사랑하는 사람들과 함께 아름다운 추억을 만들어보세요.',
         (76.4, 38.2, 13.0, 0.7, 9.4)),
        ('어려운 행정 용어와 법령 조항 해석에 관한 질의 회신 사례집 발간 및 배포 계획 공고 통지 처분 집행을 알립니다.',
         (100.0, 83.3, 19.0, 0.25, 15.96)),
        (SentenceLengthTest.LONG_SENTENCE, (100.0, 58.4, 31.0, 0.318, 22.9)),
    )

    # 형태소 사전 버전에 따라 '누리집'을 한 단어(NNG)로 보기도 하고 '누리'+'집'으로 쪼개기도 한다.
    # 클라우드 검증 환경의 사전은 한 단어, 윈도우 PC의 C:/mecab 사전은 둘로 쪼갠다 (2026-10-14 확인).
    # 공식은 같고 단어 수만 하나 달라지므로, 쪼개는 사전에서는 그 사전으로 낸 값을 기대한다.
    SPLIT_DICT_CASES = {
        CASES[1][0]: (61.6, 30.8, 5.67, 0.364, 7.78),
    }

    @classmethod
    def _dict_splits_nurijip(cls):
        # '누리집' 한 단어만 넣으면 사전이 달리 볼 수 있어, 실제 사례 문장 안에서 확인한다.
        morphemes = [m for m, _ in de.parse_morphemes(cls.CASES[1][0])]
        return '누리집' not in morphemes and '누리' in morphemes

    def test_block_scores_are_unchanged(self):
        # 값은 형태소 사전(mecab-ko-dic)의 단어 쪼개기에 달려 있다. 사전 버전이 다르면 어긋날 수 있어서
        # 사례마다 따로 보고한다 (한 사례가 틀려도 나머지 결과가 보이게).
        for text, expected in self.CASES:
            if text in self.SPLIT_DICT_CASES and self._dict_splits_nurijip():
                expected = self.SPLIT_DICT_CASES[text]
            score, v2, avg_len, easy, gl = expected
            with self.subTest(text=text[:30]):
                result = de.analyze_block(block(text))
                metrics = result['metrics']
                self.assertEqual((score, v2, avg_len, easy, gl),
                                 (result['difficulty_score'], result['difficulty_score_v2'],
                                  metrics['avg_sentence_length'], metrics['easy_word_ratio'], metrics['gl_score']),
                                 text[:30])

    def test_thresholds_are_unchanged(self):
        self.assertEqual((25, 0.6, 72.7, 9.0, 2, 4),
                         (de.THRESHOLD_SENTENCE_LENGTH, de.EASY_WORD_RATIO_MIN, de.THRESHOLD_DIFFICULTY_SCORE,
                          de.THRESHOLD_GL, de.SHORT_TEXT_MIN_HARD_NOUNS, de.NOUN_STACK_MIN_EOJEOLS))
        self.assertEqual({'button': 20, 'link': 30, 'label': 40, 'form_guide': 50, 'heading': 60},
                         de.MAX_TEXT_LENGTH)

    def test_short_paragraph_without_ratio_stays_unscored(self):
        result = de.analyze_block(block('수수료는 3.5%입니다. 2026.06.22부터 시행합니다.'))
        self.assertIsNone(result['difficulty_score'])
        self.assertEqual(2, result['metrics']['hard_noun_count'])
        self.assertTrue(any('표본 부족' in f for f in result['flags']))


if __name__ == '__main__':
    unittest.main()
