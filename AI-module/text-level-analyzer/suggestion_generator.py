"""
============================================================
 LLM 수정 제안 생성기 (suggestion_generator.py)
 위반 블록에 대한 구체적 수정 가이드 자동 생성
============================================================

[파일 목적]
  difficulty_engine.py가 "이 문장은 어렵다"고 판정한 블록들에 대해,
  "그러면 어떻게 고쳐야 하는가"를 구체적으로 제시하는 모듈.

[핵심 설계: 역할 분담]
  측정/판정: difficulty_engine.py (자체 구현 엔진)
  수정 제안: 이 모듈 (규칙 기반 템플릿 + LLM 보조)

[두 가지 제안 생성 방식]
  1) 규칙 기반 템플릿 (오프라인, 항상 동작)
     - 플래그 유형별로 미리 작성해 둔 수정 가이드 템플릿
     - LLM 없이도 동작하므로 API 키가 없어도 기본 가이드 제공
     - 예: "문장 길이 과다" → "한 문장에 하나의 정보만 담도록 분리하세요"

  2) LLM 수정 제안 (온라인, OpenAI GPT API)
     - 난이도 엔진의 측정 수치를 프롬프트에 포함하여 LLM에게 전달
     - LLM이 원문을 쉽게 다시 작성한 수정문과 수정 이유를 반환
     - 비용 관리를 위해 난이도 점수가 높은 paragraph만 대상 (최대 20건/실행)

[비용 관리 전략]
  - MAX_LLM_CALLS = 20: 한 번 실행에 최대 20건만 LLM 호출
  - 대상 제한: paragraph 중 난이도 점수 50 이상, 또는 40글자 이상 link/form_guide만
  - 모델: gpt-4o-mini (gpt-4 대비 비용 대폭 절감, 수정 제안 품질은 충분)
  - 향후 개선: 배치 처리(여러 문장을 한 번에 묶어 호출)로 추가 절감 가능

[파이프라인 내 위치]
  text_extractor.py (텍스트 추출)
    → difficulty_engine.py (난이도 측정 + 위반 플래그)
    → [이 파일] suggestion_generator.py (수정 제안 생성)
    → result_text_suggestions.json (최종 출력)

[사용법]
  python suggestion_generator.py result_text_difficulty.json
  python suggestion_generator.py result_text_difficulty.json output.json

[환경변수]
  OPENAI_API_KEY: OpenAI API 키 (없으면 오프라인 모드로 동작)

[입출력]
  입력: result_text_difficulty.json (difficulty_engine.py 출력)
  출력: 각 위반 블록에 수정 제안(suggestions)과 LLM 수정문(llm_revision)이 추가된 JSON
"""

import json
import sys
import os

# .env 파일에서 환경변수 로드 (OPENAI_API_KEY 등)
from dotenv import load_dotenv
load_dotenv()

import time


# ─────────────────────────────────────────
# 0. 설정
# ─────────────────────────────────────────

# OpenAI API 키: .env 파일 또는 시스템 환경변수에서 읽음
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# LLM 모델 선택
# gpt-4o-mini: 비용 절감 + 수정 제안 수준의 작업에는 충분한 품질
LLM_MODEL = 'gpt-4o-mini'

# ── LLM 호출 제한 (비용 관리) ──
MAX_LLM_CALLS = 20       # 한 번 실행 시 최대 LLM 호출 수 (비용 상한)
LLM_RETRY_COUNT = 2      # API 실패 시 재시도 횟수
LLM_RETRY_DELAY = 2      # 재시도 간 대기 시간 (초)

# API 키가 없으면 오프라인 모드로 자동 전환
# 오프라인 모드: 규칙 기반 템플릿 제안만 생성 (LLM 호출 안 함)
OFFLINE_MODE = not bool(OPENAI_API_KEY)


# ─────────────────────────────────────────
# 1. 규칙 기반 수정 제안 (LLM 없이 템플릿으로 생성)
# ─────────────────────────────────────────
# [왜 규칙 기반 템플릿이 필요한가]
#   LLM은 API 키가 있어야 동작하고, 비용도 발생.
#   규칙 기반 템플릿은 API 없이도 항상 동작하는 기본 가이드이며,
#   LLM이 활성화된 경우에도 함께 제공됨.
#
# [제공하는 정보]
#   각 제안에는 다음 정보가 포함:
#     type      : 문제 유형 (sentence_length, hard_vocab_ratio 등)
#     issue     : 구체적 문제 설명 + 측정 수치
#     guide     : 수정 방법 가이드 + 예시
#     kwcag_ref : 관련 KWCAG 항목 참조
#     priority  : 우선순위 (high/medium/low)

def generate_rule_based_suggestion(block):
    """
    플래그 유형에 따라 템플릿 기반 수정 제안을 생성.

    difficulty_engine.py가 생성한 flags 배열의 각 플래그를 확인하고,
    해당 유형에 맞는 수정 가이드를 반환.

    [플래그 유형별 처리]
      '문장 길이 과다'     → 문장 분리 가이드 (priority: high)
      '고난이도 어휘 과다' → 쉬운 어휘 대체 가이드 + 고난이도 어휘 목록 (priority: medium)
      '어절 길이 과다'     → 복합어 풀어쓰기 가이드 (priority: medium)
      '위치 참조/모호한 참조' → 구체적 이름 사용 가이드 (priority: high)
      '텍스트 길이 과다'   → 카테고리별 간결화 가이드 (priority: low~medium)

    Args:
      block: difficulty_engine.py가 출력한 분석 결과 블록
    Returns:
      수정 제안 dict의 리스트
    """
    suggestions = []
    text = block.get('text', '')
    category = block.get('category', '')
    flags = block.get('flags', [])
    metrics = block.get('metrics', {})

    for flag in flags:
        # ── 문장 길이 과다 ──
        # 난이도 엔진이 평균 문장 길이가 25어절을 초과한다고 판정한 경우
        if '문장 길이 과다' in flag:
            avg_len = metrics.get('avg_sentence_length', 0)
            suggestions.append({
                'type': 'sentence_length',
                'issue': f'평균 문장 길이가 {avg_len:.1f}어절로 기준(25어절)을 초과합니다.',
                'guide': '한 문장에 하나의 정보만 담도록 분리하세요. '
                         '접속사(~하고, ~하며, ~하여)로 이어진 문장을 마침표로 나누면 됩니다.',
                'kwcag_ref': '3.1.1 읽기 쉬운 콘텐츠',
                'priority': 'high',
            })

        # ── 고난이도 어휘 비율 과다 (국립국어원 학습용 어휘 등급 기반) ──
        # 난이도 엔진이 고난이도 어휘(C등급 + 미등재) 비율이 40%를 초과한다고 판정한 경우
        # 실제 검출된 고난이도 어휘 목록을 함께 보여줌 (최대 5개)
        # ※ 기존 '추상어 비율 과다' 플래그도 호환 유지
        elif '고난이도 어휘 과다' in flag or '추상어 비율 과다' in flag:
            hard_nouns = metrics.get('hard_vocab_nouns', metrics.get('abstract_nouns', []))
            ratio = metrics.get('hard_vocab_ratio', metrics.get('abstract_ratio', 0))
            examples = ', '.join(hard_nouns[:5]) if hard_nouns else ''
            suggestions.append({
                'type': 'hard_vocab_ratio',
                'issue': f'고난이도 어휘 비율이 {ratio*100:.1f}%로 기준(40%)을 초과합니다. '
                         f'주요 고난이도 어휘: {examples}',
                'guide': '고급 어휘나 전문 용어를 쉬운 단어로 바꾸세요. '
                         '예: "이행" → "지키기", "제반 사항" → "모든 내용", '
                         '"의거하여" → "따라서", "시행" → "실시/시작"',
                'kwcag_ref': '3.1.1 읽기 쉬운 콘텐츠',
                'priority': 'medium',
            })

        # ── 어절 길이 과다 ──
        # 난이도 엔진이 평균 어절 길이가 4.5글자를 초과한다고 판정한 경우
        elif '어절 길이 과다' in flag:
            avg_eojeol = metrics.get('avg_eojeol_length', 0)
            suggestions.append({
                'type': 'eojeol_length',
                'issue': f'평균 어절 길이가 {avg_eojeol:.1f}글자로 기준(4.5글자)을 초과합니다. '
                         f'전문용어나 복합어가 많을 수 있습니다.',
                'guide': '긴 복합어를 풀어 쓰세요. '
                         '예: "부동산공시가격산정시스템" → "부동산 공시가격 산정 시스템", '
                         '"건축물대장" → "건축물 대장"',
                'kwcag_ref': '3.1.1 읽기 쉬운 콘텐츠',
                'priority': 'medium',
            })

        # ── 위치 의존 표현 ──
        # 난이도 엔진이 '위의 버튼을 클릭하세요' 같은 위치 참조를 탐지한 경우
        # KWCAG 2.2의 5.3.3 '명확한 지시사항 제공'에 직접 해당
        elif '위치 참조' in flag or '모호한 참조' in flag:
            suggestions.append({
                'type': 'location_dependency',
                'issue': f'위치에 의존하는 모호한 표현이 있습니다: {flag}',
                'guide': '위치 참조 대신 구체적 이름을 사용하세요. '
                         '예: "위의 버튼을 클릭하세요" → "\'제출\' 버튼을 클릭하세요", '
                         '"해당 메뉴" → "\'민원 신청\' 메뉴"',
                'kwcag_ref': '1.3.3 감각적 특성에 의존하지 않는 콘텐츠',
                'priority': 'high',
            })

        # ── 카테고리별 길이 과다 (link, button, form_guide 등) ──
        # 난이도 엔진이 해당 카테고리의 최대 허용 길이를 초과한다고 판정한 경우
        # 카테고리에 따라 다른 수정 가이드를 제공
        elif '텍스트 길이 과다' in flag:
            if category == 'link':
                suggestions.append({
                    'type': 'link_length',
                    'issue': f'링크 텍스트가 {len(text)}글자로 기준(30글자)을 초과합니다.',
                    'guide': '링크 텍스트는 목적지를 간결하게 설명해야 합니다. '
                             '부가 설명은 링크 밖에 두고, 링크 자체는 핵심만 담으세요.',
                    'kwcag_ref': '2.4.4 링크 목적 식별',
                    'priority': 'low',
                })
            elif category == 'button':
                suggestions.append({
                    'type': 'button_length',
                    'issue': f'버튼 텍스트가 {len(text)}글자로 기준(20글자)을 초과합니다.',
                    'guide': '버튼 텍스트는 동작을 명확하게 2~4단어로 표현하세요. '
                             '예: "신청서 작성 및 제출하기" → "신청하기"',
                    'kwcag_ref': '2.4.4 링크 목적 식별',
                    'priority': 'medium',
                })
            elif category == 'form_guide':
                suggestions.append({
                    'type': 'form_guide_length',
                    'issue': f'안내 문구가 {len(text)}글자로 기준(50글자)을 초과합니다.',
                    'guide': 'placeholder나 aria-label은 간결해야 합니다. '
                             '자세한 설명은 별도 안내 텍스트로 분리하세요.',
                    'kwcag_ref': '3.3.2 레이블 또는 설명 제공',
                    'priority': 'low',
                })
            else:
                suggestions.append({
                    'type': 'text_length',
                    'issue': f'{category} 텍스트가 길이 기준을 초과합니다.',
                    'guide': '핵심 내용만 남기고 부가 설명은 분리하세요.',
                    'kwcag_ref': '3.1.1 읽기 쉬운 콘텐츠',
                    'priority': 'low',
                })

    return suggestions


# ─────────────────────────────────────────
# 2. LLM 수정 제안 (OpenAI GPT API)
# ─────────────────────────────────────────
# [규칙 기반 템플릿과의 차이]
#   규칙 기반 템플릿: "이렇게 고치면 됩니다"라는 일반적 가이드 제공
#   LLM 수정 제안:    원문을 실제로 쉽게 다시 써서 구체적 수정문 제공
#
# [LLM에게 전달하는 정보]
#   난이도 엔진의 측정 수치(평균 문장 길이, 어휘 난이도 등)를 프롬프트에 포함
#   → LLM은 "어디가 왜 어려운지"를 이미 알고 있는 상태에서 수정안을 생성
#   → 엔진이 진단하고, LLM이 처방하는 역할 분담
#
# [프롬프트 설계의 핵심]
#   1) 난이도 엔진의 측정 결과를 구조화하여 전달 (LLM이 맥락을 이해하도록)
#   2) 수정 원칙 명시 (고난이도 어휘→쉬운 어휘, 긴 문장→짧게, 전문용어→쉬운 말)
#   3) 출력 형식을 JSON으로 강제 (파싱 용이)
#   4) 원래 의미 유지 제약 (쉽게 쓰되 내용이 바뀌면 안 됨)

def build_llm_prompt(block):
    """
    난이도 엔진의 측정 수치를 포함한 LLM 프롬프트를 구성.

    [프롬프트 구조]
      역할 설정: "당신은 웹 접근성 전문가입니다"
      원문 제시: 수정 대상 텍스트
      분석 결과: 난이도 엔진이 측정한 수치들 (문장 길이, 어휘 난이도 등)
      탐지된 문제: flags 배열의 내용
      수정 지시: 수정 원칙 + JSON 출력 형식 강제

    [왜 측정 수치를 프롬프트에 포함하는가]
      LLM에게 "이 문장을 쉽게 써줘"라고만 하면 개선 방향이 모호.
      "평균 28.5어절이고, 고난이도 어휘 비율 45%이며, '제반', '의거' 등이 문제"라고
      구체적으로 알려주면 LLM이 정확히 어디를 어떻게 고쳐야 하는지 알 수 있음.

    Args:
      block: difficulty_engine.py가 출력한 분석 결과 블록
    Returns:
      LLM에게 전달할 프롬프트 문자열
    """
    text = block.get('text', '')
    category = block.get('category', '')
    metrics = block.get('metrics', {})
    flags = block.get('flags', [])
    score = block.get('difficulty_score')

    # 난이도 엔진 측정 수치를 읽기 좋은 형태로 구성
    metric_lines = []
    if metrics.get('avg_sentence_length'):
        metric_lines.append(f"- 평균 문장 길이: {metrics['avg_sentence_length']}어절")
    if metrics.get('avg_eojeol_length'):
        metric_lines.append(f"- 평균 어절 길이: {metrics['avg_eojeol_length']}글자")

    # 어휘 난이도: 새 키(hard_vocab_ratio) 우선, 구 키(abstract_ratio) 폴백
    if metrics.get('hard_vocab_ratio') is not None:
        metric_lines.append(f"- 고난이도 어휘 비율: {metrics['hard_vocab_ratio']*100:.1f}%")
    elif metrics.get('abstract_ratio') is not None:
        metric_lines.append(f"- 고난이도 어휘 비율: {metrics['abstract_ratio']*100:.1f}%")

    if metrics.get('hard_vocab_nouns'):
        metric_lines.append(f"- 주요 고난이도 어휘: {', '.join(metrics['hard_vocab_nouns'][:8])}")
    elif metrics.get('abstract_nouns'):
        metric_lines.append(f"- 주요 고난이도 어휘: {', '.join(metrics['abstract_nouns'][:8])}")

    if score is not None:
        metric_lines.append(f"- 종합 난이도 점수: {score}/100 (높을수록 어려움)")

    metric_str = '\n'.join(metric_lines) if metric_lines else '(지표 없음)'
    flag_str = '\n'.join(f'- {f}' for f in flags) if flags else '(없음)'

    prompt = f"""당신은 웹 접근성 전문가입니다. 아래 웹페이지 텍스트는 한국어 인지 난이도 분석 결과 문제가 있습니다.

[원문]
{text}

[텍스트 유형]
{category}

[난이도 엔진 분석 결과]
{metric_str}

[탐지된 문제]
{flag_str}

위 분석 결과를 참고하여, 다음 형식으로 수정 제안을 해주세요:

1. **수정문**: 일반 성인(노인 포함)이 한 번 읽고 이해할 수 있도록 원문을 쉽게 다시 작성해주세요.
   - 고난이도 어휘(고급/전문 용어)는 쉬운 단어로 바꾸세요
   - 긴 문장은 짧게 나누세요
   - 전문용어는 쉬운 말로 풀어쓰세요
   - 원래 의미는 유지하세요

2. **수정 이유**: 어떤 부분을 왜 바꿨는지 한 줄로 설명해주세요.

JSON 형식으로만 응답해주세요:
{{"revised_text": "수정된 문장", "reason": "수정 이유 한 줄 설명"}}"""

    return prompt


def call_openai_api(prompt):
    """
    OpenAI GPT API를 호출하여 수정 제안을 받음.

    [API 호출 방식]
      requests 라이브러리로 OpenAI /v1/chat/completions 엔드포인트에 POST 요청
      temperature=0.3: 일관성 있는 출력을 위해 낮게 설정
                       (높으면 같은 입력에 매번 다른 출력이 나옴)
      max_tokens=500: 수정문 + 이유 정도면 충분한 길이

    [에러 처리]
      429 (Rate Limit): 대기 후 재시도 (LLM_RETRY_DELAY × 시도 횟수)
      JSON 파싱 실패: LLM이 지시대로 JSON을 안 줄 수 있음 → None 반환
      네트워크 오류: 재시도 후에도 실패하면 None 반환
      → None 반환 시 규칙 기반 템플릿 제안만 사용됨 (전체 파이프라인은 중단 안 됨)

    [LLM 응답 파싱]
      LLM이 ```json ... ``` 형태로 감싸서 응답할 수 있으므로
      앞뒤의 백틱 마크다운을 제거한 후 JSON 파싱

    Args:
      prompt: build_llm_prompt()이 생성한 프롬프트 문자열
    Returns:
      {'revised_text': '수정된 문장', 'reason': '수정 이유'} 또는 None (실패 시)
    """
    try:
        import requests
    except ImportError:
        print('  [경고] requests 패키지 없음. pip install requests 필요')
        return None

    url = 'https://api.openai.com/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENAI_API_KEY}',
    }
    body = {
        'model': LLM_MODEL,
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.3,
        'max_tokens': 500,
    }

    for attempt in range(LLM_RETRY_COUNT + 1):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)

            if resp.status_code == 429:
                # Rate limit 초과 — 대기 후 재시도
                wait = LLM_RETRY_DELAY * (attempt + 1)
                print(f'  [Rate limit] {wait}초 대기 후 재시도...')
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                print(f'  [API 에러] status={resp.status_code}: {resp.text[:200]}')
                return None

            data = resp.json()
            content = data['choices'][0]['message']['content']

            # JSON 파싱: LLM이 ```json ... ``` 형태로 감쌀 수 있으므로 제거
            content = content.strip()
            if content.startswith('```'):
                content = content.split('\n', 1)[1] if '\n' in content else content[3:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()

            result = json.loads(content)
            return result

        except json.JSONDecodeError:
            print(f'  [파싱 실패] LLM 응답이 JSON이 아님: {content[:100]}')
            return None
        except Exception as e:
            if attempt < LLM_RETRY_COUNT:
                time.sleep(LLM_RETRY_DELAY)
                continue
            print(f'  [API 에러] {e}')
            return None

    return None


# ─────────────────────────────────────────
# 3. 규칙 기반 위반에 대한 코드 수정 가이드
# ─────────────────────────────────────────
# [이 섹션의 목적]
#   axe-core 규칙 기반 모듈(run.js)이 발견한 HTML 코드 위반에 대해
#   "코드를 이렇게 고치세요"라는 구체적 수정 예시를 제공합니다.
#   이건 텍스트 난이도와는 다른 영역 — HTML 코드 수준의 수정 가이드.
#
# [현재 상태]
#   함수와 데이터만 준비해 둔 상태이며,
#   통합 단계(Phase 4)에서 axe-core 위반 결과와 연결할 예정.
#
# [제공 정보]
#   guide        : 수정 방법 설명
#   code_before  : 위반 코드 예시 (이렇게 작성하면 안 됨)
#   code_after   : 수정 코드 예시 (이렇게 고쳐야 함)
#   kwcag_ref    : 관련 KWCAG 항목

RULE_BASED_GUIDES = {
    # 대체 텍스트 누락: <img>에 alt 속성 없음
    'image-alt': {
        'guide': '이미지에 대체 텍스트(alt 속성)를 추가하세요.',
        'code_before': '<img src="photo.jpg">',
        'code_after': '<img src="photo.jpg" alt="시청 전경 사진">',
        'kwcag_ref': '1.1.1 적절한 대체 텍스트 제공',
    },
    # 명도 대비 부족: 텍스트와 배경의 대비가 4.5:1 미만
    'color-contrast': {
        'guide': '텍스트와 배경의 명암비를 4.5:1 이상으로 조정하세요.',
        'color_suggestion': '밝은 배경(#FFFFFF)에는 #595959 이상의 어두운 글자색을 사용하세요.',
        'kwcag_ref': '1.4.3 명도 대비',
    },
    # 제목 순서 오류: h1 → h3 처럼 레벨을 건너뜀
    'heading-order': {
        'guide': '제목 태그(h1~h6)를 순서대로 사용하세요. h1 다음에 h3가 오면 안 됩니다.',
        'code_before': '<h1>제목</h1>\n<h3>소제목</h3>',
        'code_after': '<h1>제목</h1>\n<h2>소제목</h2>',
        'kwcag_ref': '1.3.1 정보와 관계',
    },
    # 레이블 누락: 입력 필드에 연결된 <label>이 없음
    'label': {
        'guide': '입력 필드에 연결된 label을 추가하세요.',
        'code_before': '<input type="text" id="name">',
        'code_after': '<label for="name">이름</label>\n<input type="text" id="name">',
        'kwcag_ref': '1.3.1 정보와 관계',
    },
    # 버튼 이름 없음: 아이콘만 있는 버튼에 접근 가능한 이름이 없음
    'button-name': {
        'guide': '버튼에 접근 가능한 이름을 추가하세요.',
        'code_before': '<button><img src="search.png"></button>',
        'code_after': '<button aria-label="검색"><img src="search.png"></button>',
        'kwcag_ref': '4.1.2 이름, 역할, 값',
    },
    # 링크 텍스트 부적절: '여기' 같은 모호한 링크 텍스트
    'link-name': {
        'guide': '링크에 명확한 텍스트를 제공하세요.',
        'code_before': '<a href="/apply">여기</a>를 클릭하세요',
        'code_after': '<a href="/apply">민원 신청 페이지로 이동</a>',
        'kwcag_ref': '2.4.4 링크 목적 식별',
    },
    # 언어 속성 누락: <html> 태그에 lang 속성이 없음
    'html-has-lang': {
        'guide': 'HTML 태그에 언어 속성을 추가하세요.',
        'code_before': '<html>',
        'code_after': '<html lang="ko">',
        'kwcag_ref': '3.1.1 페이지 언어 표시',
    },
}


def get_rule_based_guide(axe_rule_id):
    """
    axe-core 규칙 ID로 코드 수정 가이드를 반환.
    통합 단계(Phase 4)에서 axe-core 위반 결과와 연결할 때 사용.

    Args:
      axe_rule_id: axe-core 규칙 ID (예: 'image-alt', 'color-contrast')
    Returns:
      수정 가이드 dict 또는 None (해당 규칙의 가이드가 없는 경우)
    """
    return RULE_BASED_GUIDES.get(axe_rule_id)


# ─────────────────────────────────────────
# 4. 메인: 수정 제안 생성 실행
# ─────────────────────────────────────────

def generate_suggestions(input_path, output_path=None):
    """
    difficulty_engine.py의 출력을 읽어서 수정 제안을 추가한 JSON을 생성.

    [처리 흐름]
      1) 전체 블록에서 needs_suggestion == true인 블록만 처리 대상
      2) 모든 대상 블록에 규칙 기반 템플릿 제안 생성 (항상 동작)
      3) LLM 호출 대상 판별:
         - paragraph: 난이도 점수 50 이상인 경우만
         - link/form_guide: 텍스트 40글자 이상인 경우만
         - 최대 20건까지 (MAX_LLM_CALLS)
      4) LLM 호출 성공 시: llm_revision에 수정문과 수정 이유 저장
         LLM 호출 실패 시: 규칙 기반 템플릿 제안만 유지 (파이프라인 중단 안 됨)
      5) 결과를 원본 JSON에 합쳐서 저장

    [출력 JSON 구조 (각 블록에 추가되는 필드)]
      {
        ...기존 difficulty_engine 출력 필드...,
        "suggestions": [                    ← 규칙 기반 템플릿 제안 (항상 있음)
          { "type": "hard_vocab_ratio",
            "issue": "고난이도 어휘 비율이 45.0%로...",
            "guide": "고급 어휘나 전문 용어를 쉬운 단어로...",
            "kwcag_ref": "3.1.1 ...",
            "priority": "medium" }
        ],
        "llm_revision": {                   ← LLM 수정문 (호출 성공 시에만)
          "revised_text": "쉽게 다시 쓴 문장",
          "reason": "수정 이유 한 줄",
          "model": "gpt-4o-mini"
        }
      }

    Args:
      input_path: 입력 JSON 파일 경로 (difficulty_engine.py 출력)
      output_path: 출력 JSON 파일 경로 (None이면 자동 생성)
    Returns:
      출력 JSON 데이터 (dict)
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = data.get('results', [])
    llm_call_count = 0
    suggestion_total = 0

    # 오프라인 모드 안내 (API 키 미설정 시)
    if OFFLINE_MODE:
        print('[오프라인 모드] OPENAI_API_KEY가 설정되지 않아 LLM 호출을 건너뜁니다.')
        print('  → 규칙 기반 템플릿 제안만 생성합니다.')
        print(f'  → API 키 설정: set OPENAI_API_KEY=sk-xxxx (Windows)')
        print()

    for i, block in enumerate(results):
        if not block.get('needs_suggestion', False):
            # 수정 제안 불필요한 블록 — 빈 값만 세팅하고 건너뜀
            block['suggestions'] = []
            block['llm_revision'] = None
            continue

        # ── Step 1: 규칙 기반 템플릿 제안 (항상 생성) ──
        rule_suggestions = generate_rule_based_suggestion(block)
        block['suggestions'] = rule_suggestions
        suggestion_total += len(rule_suggestions)

        # ── Step 2: LLM 수정 제안 (조건부 호출) ──
        block['llm_revision'] = None

        if not OFFLINE_MODE and llm_call_count < MAX_LLM_CALLS:
            # LLM 호출 대상 판별:
            #   paragraph: 종합 난이도 점수 50 이상 (정말 어려운 문장만)
            #   link/form_guide: 40글자 이상 (사용자에게 직접 보이는 긴 텍스트)
            #   그 외: LLM 호출 안 함 (비용 절감)
            should_call_llm = False

            if block.get('category') == 'paragraph':
                score = block.get('difficulty_score')
                if score is not None and score >= 50:
                    should_call_llm = True
            elif block.get('category') in ('link', 'form_guide'):
                if len(block.get('text', '')) > 40:
                    should_call_llm = True

            if should_call_llm:
                print(f'  [{i}] LLM 호출 중... (카테고리: {block["category"]})')
                prompt = build_llm_prompt(block)
                llm_result = call_openai_api(prompt)

                if llm_result:
                    block['llm_revision'] = {
                        'revised_text': llm_result.get('revised_text', ''),
                        'reason': llm_result.get('reason', ''),
                        'model': LLM_MODEL,
                    }
                    llm_call_count += 1
                    print(f'    → 수정문: {llm_result.get("revised_text", "")[:60]}...')
                else:
                    print(f'    → LLM 응답 실패, 템플릿 제안만 사용')

    # ── 메타데이터 업데이트 ──
    # 실행 결과 통계를 meta에 추가 (프론트엔드/보고서에서 활용)
    data['meta']['suggestion_stats'] = {
        'total_suggestions': suggestion_total,      # 생성된 규칙 기반 제안 총 수
        'llm_calls': llm_call_count,                # 실제 LLM 호출 횟수
        'llm_model': LLM_MODEL if not OFFLINE_MODE else None,
        'mode': 'offline' if OFFLINE_MODE else 'online',
    }

    # ── 저장 ──
    # 출력 파일명: 입력 파일명에서 _difficulty를 _suggestions로 변경
    # 예: result_text_difficulty.json → result_text_suggestions.json
    if output_path is None:
        output_path = input_path.replace('_difficulty.json', '_suggestions.json')
        if output_path == input_path:
            output_path = input_path.replace('.json', '_suggestions.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 콘솔에 실행 결과 요약 출력
    print()
    print(f'수정 제안 생성 완료')
    print(f'  대상 블록: {sum(1 for r in results if r.get("needs_suggestion"))}개')
    print(f'  규칙 기반 제안: {suggestion_total}개')
    print(f'  LLM 호출: {llm_call_count}회')
    print(f'  결과 저장: {output_path}')

    return data


# ─────────────────────────────────────────
# 5. CLI 실행
# ─────────────────────────────────────────
# 커맨드 라인에서 직접 실행할 때의 진입점
#
# 실행 예시:
#   kwcag-adapter/ 디렉토리에서:
#   python ..\ai-analysis\suggestion_generator.py result_text_difficulty.json
#
# 전체 파이프라인 순서:
#   1) node src/run.js https://www.gov.kr result.json           → result.html 생성
#   2) python ..\ai-analysis\text_extractor.py result.html       → result_text.json 생성
#   3) python ..\ai-analysis\difficulty_engine.py result_text.json → result_text_difficulty.json 생성
#   4) python ..\ai-analysis\suggestion_generator.py result_text_difficulty.json → result_text_suggestions.json 생성

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('사용법: python suggestion_generator.py <result_text_difficulty.json> [output.json]')
        print()
        print('환경변수:')
        print('  OPENAI_API_KEY  - OpenAI API 키 (없으면 오프라인 모드)')
        print()
        print('예시:')
        print('  python suggestion_generator.py result_text_difficulty.json')
        print('  python suggestion_generator.py result_text_difficulty.json result_final.json')
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    generate_suggestions(input_path, output_path)
