"""
============================================================
 한국어 인지 난이도 분석 엔진 (difficulty_engine.py)
 웹페이지 텍스트의 인지적 난이도를 측정하는 자체 설계 엔진
============================================================

[파일 목적]
  웹페이지에서 추출한 텍스트가 노인/인지약자에게 얼마나 어려운지를
  자동으로 측정하고, 위반 플래그를 생성하는 엔진.

[기존 도구와의 차이]
  기존 도구: HTML 코드만 검사 (alt 태그 유무, 색 대비 등)
  본 엔진:   콘텐츠 자체의 인지적 난이도를 측정
             → 코드상으로 문제없어도 "내용이 어려워서 이해 못하는" 경우를 잡아냄

[측정 지표 4가지]
  1. 평균 문장 길이 (어절 수) — 25어절 이상이면 인지 부담 높음
  2. 평균 어절 길이 (글자 수) — 4.5글자 이상이면 어휘 복잡도 높음
  3. 고난이도 어휘 비율 (국립국어원 학습용 어휘 등급 기반) — 40% 이상이면 과다
  4. 위치 의존 표현 탐지 — '위의 버튼' 같은 모호한 위치 참조

[종합 점수 산출 방식]
  종합 점수 = 문장 길이(×0.45) + 어절 길이(×0.30) + 어휘 난이도(×0.25)

[파이프라인 내 위치]
  text_extractor.py → [이 파일] difficulty_engine.py → suggestion_generator.py

[사용법]
  python difficulty_engine.py result_text.json
  python difficulty_engine.py result_text.json output.json

[사용 라이브러리]
  MeCab: 한국어 형태소 분석기 (Pusnow/mecab-ko-msvc Windows 바이너리)
"""

import json
import re
import sys
import os
import MeCab


# ─────────────────────────────────────────
# 0. 어휘 사전 로딩 (국립국어원 학습용 어휘 등급)
# ─────────────────────────────────────────
# A등급(초급) 894개, B등급(중급) 1994개, C등급(고급) 2655개, 총 5543개
# 출처: 국립국어원 (2003), 공공누리 제1유형

_VOCAB_DICT_PATH = os.path.join(os.path.dirname(__file__), 'korean_vocab_grades.json')
with open(_VOCAB_DICT_PATH, 'r', encoding='utf-8') as _f:
    VOCAB_GRADES = json.load(_f)


# ─────────────────────────────────────────
# 1. MeCab 래퍼 (형태소 분석 인터페이스)
# ─────────────────────────────────────────

_tagger = MeCab.Tagger('-r C:/mecab/etc/mecabrc -d C:/mecab/share/mecab-ko-dic')


def parse_morphemes(text):
    """문장을 형태소 분석하여 (표층형, 품사) 리스트를 반환."""
    parsed = _tagger.parse(text)
    morphemes = []
    for line in parsed.strip().split('\n'):
        if line == 'EOS' or line == '':
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        surface = parts[0]
        pos = parts[1].split(',')[0]
        morphemes.append((surface, pos))
    return morphemes


def extract_nouns(text):
    """텍스트에서 명사(NNG, NNP)만 추출하여 리스트로 반환."""
    morphemes = parse_morphemes(text)
    nouns = [surface for surface, pos in morphemes if pos in ('NNG', 'NNP')]
    return nouns


# ─────────────────────────────────────────
# 2. 평균 문장 길이 (어절 수)
# ─────────────────────────────────────────

THRESHOLD_SENTENCE_LENGTH = 25  # 25어절 이상이면 인지 부담 높음

def calc_avg_sentence_length(text):
    """평균 문장 길이(어절 수)를 계산."""
    sentences = re.split(r'[.!?。]\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0, 0
    total_eojeols = sum(len(s.split()) for s in sentences)
    avg = total_eojeols / len(sentences)
    return round(avg, 1), total_eojeols


# ─────────────────────────────────────────
# 3. 평균 어절 길이 (글자 수)
# ─────────────────────────────────────────

THRESHOLD_EOJEOL_LENGTH = 4.5  # 4.5글자 이상이면 어휘 복잡도 높음

def calc_avg_eojeol_length(text):
    """평균 어절 길이(글자 수)를 계산."""
    eojeols = text.split()
    if not eojeols:
        return 0.0
    total_chars = sum(len(e) for e in eojeols)
    return round(total_chars / len(eojeols), 1)


# ─────────────────────────────────────────
# 4. 어휘 난이도 (국립국어원 학습용 어휘 등급 기반)
# ─────────────────────────────────────────
# 고난이도 어휘 = C등급(고급) + 미등재 단어
# 40% 이상이면 고난이도 어휘 과다로 판단
# 명사 5개 미만이면 비율 왜곡되므로 플래그 안 함

THRESHOLD_DIFFICULT_WORD = 0.40


def get_word_grade(noun):
    """명사의 어휘 등급을 반환. A/B/C/D(미등재)"""
    return VOCAB_GRADES.get(noun, 'D')


def is_difficult_word(noun):
    """C등급(고급) 또는 미등재(D)이면 고난이도."""
    return get_word_grade(noun) in ('C', 'D')


def calc_difficult_word_ratio(text):
    """고난이도 어휘 비율을 계산."""
    nouns = extract_nouns(text)
    if not nouns:
        return 0.0, [], [], {}

    difficult_nouns = [n for n in nouns if is_difficult_word(n)]

    grade_detail = {}
    for n in nouns:
        g = get_word_grade(n)
        if g not in grade_detail:
            grade_detail[g] = []
        grade_detail[g].append(n)

    ratio = len(difficult_nouns) / len(nouns)
    return ratio, difficult_nouns, nouns, grade_detail


# ─────────────────────────────────────────
# 5. 위치 의존 표현 탐지
# ─────────────────────────────────────────

LOCATION_PATTERNS = [
    (re.compile(r'(?<![가-힣/])위의?\s'), '위치 참조: "위(의)" 사용'),
    (re.compile(r'(?<![가-힣/])아래의?\s'), '위치 참조: "아래(의)" 사용'),
    (re.compile(r'(?<![가-힣/])옆의?\s'), '위치 참조: "옆(의)" 사용'),
    (re.compile(r'(?<![가-힣/])오른쪽의?\s'), '위치 참조: "오른쪽(의)" 사용'),
    (re.compile(r'(?<![가-힣/])왼쪽의?\s'), '위치 참조: "왼쪽(의)" 사용'),
    (re.compile(r'해당\s+(버튼|메뉴|링크|항목|페이지)'), '모호한 참조: "해당 ~" 사용'),
    (re.compile(r'(여기|이곳)를?\s*클릭'), '모호한 참조: "여기/이곳 클릭" 사용'),
]


def detect_location_dependency(text):
    """위치 의존 표현을 탐지하여 플래그 리스트 반환."""
    flags = []
    for pattern, message in LOCATION_PATTERNS:
        if pattern.search(text):
            flags.append(message)
    return flags


# ─────────────────────────────────────────
# 6. 종합 난이도 점수 산출
# ─────────────────────────────────────────

W_SENTENCE_LENGTH = 0.45
W_EOJEOL_LENGTH = 0.30
W_DIFFICULT_WORD = 0.25

THRESHOLD_DIFFICULTY_SCORE = 40  # 이 점수 이상이면 수정 제안 필요


def calc_difficulty_score(avg_sent_len, avg_eojeol_len, difficult_word_ratio):
    """3가지 지표를 종합하여 난이도 점수를 산출 (0~100)."""
    sent_score = min(max((avg_sent_len - 10) / 30 * 100, 0), 100)
    eojeol_score = min(max((avg_eojeol_len - 2) / 5 * 100, 0), 100)
    word_score = min(max(difficult_word_ratio / 0.6 * 100, 0), 100)

    total = (sent_score * W_SENTENCE_LENGTH +
             eojeol_score * W_EOJEOL_LENGTH +
             word_score * W_DIFFICULT_WORD)

    return round(total, 1)


# ─────────────────────────────────────────
# 7. 카테고리별 분석 (블록 단위)
# ─────────────────────────────────────────

FULL_ANALYSIS_CATEGORIES = {'paragraph'}

# 카테고리별 최대 허용 길이 (글자 수)
MAX_TEXT_LENGTH = {
    'button': 20,
    'link': 30,
    'label': 40,
    'form_guide': 50,
    'heading': 60,
}


def analyze_block(block):
    """
    개별 텍스트 블록을 분석하여 난이도 결과를 반환.
    카테고리에 따라 분석 수준을 다르게 적용.
    """
    text = block.get('text', '').strip()
    category = block.get('category', 'other')
    tag = block.get('tag', '')
    selector = block.get('selector', '')

    if not text or len(text) < 2:
        return None

    word_count = len(text.split())

    result = {
        'text': text,
        'category': category,
        'tag': tag,
        'selector': selector,
        'metrics': {
            'avg_sentence_length': None,
            'avg_eojeol_length': None,
            'word_count': word_count,
        },
        'flags': [],
        'difficulty_score': None,
        'needs_suggestion': False,
    }

    # 기본 지표: 모든 카테고리에 계산
    avg_sent_len, total_eojeols = calc_avg_sentence_length(text)
    avg_eojeol_len = calc_avg_eojeol_length(text)
    result['metrics']['avg_sentence_length'] = avg_sent_len
    result['metrics']['avg_eojeol_length'] = avg_eojeol_len

    # ── paragraph: 전체 분석 (4가지 지표 모두 적용) ──
    if category in FULL_ANALYSIS_CATEGORIES:
        diff_ratio, diff_nouns, all_nouns, grade_detail = calc_difficult_word_ratio(text)
        result['metrics']['hard_vocab_ratio'] = round(diff_ratio, 3)
        result['metrics']['hard_vocab_nouns'] = diff_nouns
        result['metrics']['grade_detail'] = grade_detail
        result['metrics']['total_noun_count'] = len(all_nouns)

        score = calc_difficulty_score(avg_sent_len, avg_eojeol_len, diff_ratio)
        result['difficulty_score'] = score

        # 위반 플래그 생성
        if avg_sent_len >= THRESHOLD_SENTENCE_LENGTH:
            result['flags'].append(
                f'문장 길이 과다: 평균 {avg_sent_len:.1f}어절 (기준: {THRESHOLD_SENTENCE_LENGTH})')

        if diff_ratio >= THRESHOLD_DIFFICULT_WORD and len(all_nouns) >= 5:
            result['flags'].append(
                f'고난이도 어휘 과다: {diff_ratio*100:.1f}% (기준: {THRESHOLD_DIFFICULT_WORD*100:.0f}%)')

        if avg_eojeol_len >= THRESHOLD_EOJEOL_LENGTH and word_count >= 3:
            result['flags'].append(
                f'어절 길이 과다: 평균 {avg_eojeol_len:.1f}글자 (기준: {THRESHOLD_EOJEOL_LENGTH})')

        loc_deps = detect_location_dependency(text)
        if loc_deps:
            result['flags'].extend(loc_deps)

        if score >= THRESHOLD_DIFFICULTY_SCORE or loc_deps:
            result['needs_suggestion'] = True

    # ── button, link, label, form_guide, heading: 길이 검사 + 위치 의존 ──
    elif category in MAX_TEXT_LENGTH:
        max_len = MAX_TEXT_LENGTH[category]
        if len(text) > max_len:
            result['flags'].append(
                f'{category} 텍스트 길이 과다: {len(text)}글자 (기준: {max_len})')
            result['needs_suggestion'] = True

        loc_deps = detect_location_dependency(text)
        if loc_deps:
            result['flags'].extend(loc_deps)
            result['needs_suggestion'] = True

    # ── table, list, alert, other: 문장 길이만 기본 검사 ──
    else:
        if avg_sent_len >= THRESHOLD_SENTENCE_LENGTH and word_count >= 5:
            result['flags'].append(
                f'문장 길이 과다: 평균 {avg_sent_len:.1f}어절 (기준: {THRESHOLD_SENTENCE_LENGTH})')
            result['needs_suggestion'] = True

    return result


# ─────────────────────────────────────────
# 8. 메인: 전체 분석 실행
# ─────────────────────────────────────────

def analyze(input_path, output_path=None):
    """result_text.json 전체를 분석하여 난이도 결과 JSON을 생성."""
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    blocks = data.get('blocks', [])
    results = []
    flagged_count = 0
    suggestion_count = 0

    for block in blocks:
        result = analyze_block(block)
        if result is None:
            continue
        results.append(result)
        if result['flags']:
            flagged_count += 1
        if result['needs_suggestion']:
            suggestion_count += 1

    # ── 페이지 단위 점수 산출 (100점 만점, 감점 방식) ──
    para_scores = [r['difficulty_score'] for r in results
                   if r['category'] == 'paragraph' and r['difficulty_score'] is not None]
    avg_difficulty = sum(para_scores) / len(para_scores) if para_scores else 0

    # 길이 위반 감점 (건당 2점, 최대 20점)
    length_violations = sum(1 for r in results
                           if any('텍스트 길이 과다' in f for f in r['flags']))
    length_penalty = min(length_violations * 2, 20)

    # 위치 의존 감점 (건당 3점, 최대 15점)
    location_violations = sum(1 for r in results
                             if any('위치 참조' in f or '모호한 참조' in f for f in r['flags']))
    location_penalty = min(location_violations * 3, 15)

    page_score = round(max(0, 100 - avg_difficulty - length_penalty - location_penalty), 1)

    # 출력 JSON 구성
    output = {
        'meta': {
            'page_score': page_score,
            'score_breakdown': {
                'avg_difficulty_deduction': round(avg_difficulty, 1),
                'length_penalty': length_penalty,
                'location_penalty': location_penalty,
            },
            'total_analyzed': len(results),
            'flagged_count': flagged_count,
            'suggestion_needed': suggestion_count,
            'thresholds': {
                'sentence_length': THRESHOLD_SENTENCE_LENGTH,
                'eojeol_length': THRESHOLD_EOJEOL_LENGTH,
                'difficult_word_ratio': THRESHOLD_DIFFICULT_WORD,
                'difficulty_score': THRESHOLD_DIFFICULTY_SCORE,
            },
            'weights': {
                'sentence_length': W_SENTENCE_LENGTH,
                'eojeol_length': W_EOJEOL_LENGTH,
                'difficult_word_ratio': W_DIFFICULT_WORD,
            },
        },
        'results': results,
    }

    if output_path is None:
        output_path = input_path.replace('.json', '_difficulty.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'분석 완료: {len(results)}개 블록 분석')
    print(f'  페이지 점수: {page_score}/100')
    print(f'    - 난이도 감점: -{round(avg_difficulty, 1)}')
    print(f'    - 길이 위반 감점: -{length_penalty}')
    print(f'    - 위치 의존 감점: -{location_penalty}')
    print(f'  위반 플래그: {flagged_count}개')
    print(f'  수정 제안 필요: {suggestion_count}개')
    print(f'  결과 저장: {output_path}')

    return output


# ─────────────────────────────────────────
# CLI 진입부
# ─────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('사용법: python difficulty_engine.py <result_text.json> [output.json]')
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    analyze(input_path, output_path)
