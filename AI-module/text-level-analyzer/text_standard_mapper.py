"""Map text-analyzer findings through the canonical KWCAG 2.2 table.

The rule-based analyzer owns the canonical mapping in ``mapping.js``. This
module uses the shared Python bridge so the text analyzer cannot drift to a
second, hand-maintained KWCAG numbering scheme.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


AI_MODULE_DIR = Path(__file__).resolve().parents[1]
if str(AI_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODULE_DIR))

from standard_mapping import kwcag_items_for_wcag
import re


# 감각 의존 지시 플래그 (difficulty_engine.detect_sensory_instructions가 만드는 문자열 기준).
#   예) '감각 의존 지시(위치): "오른쪽 상단의 버튼" — 이름 없이 위치로만 가리킴'
# 좌우·옆·색·모양·소리는 화면을 못 보거나 색을 못 구별하면 단서가 전혀 없어 high.
# "화면 아래의 버튼"처럼 화면 전체 기준의 위·아래는 문서의 처음과 끝은 짐작할 수 있어 한 단계
# 낮춰 medium이다 (2026-10-03 위·아래 medium, 좌우·옆 high를 새 탐지기로 옮김, 2026-10-13).
# 위치 플래그의 인용문이 화면·페이지·창의 위·아래 기준이고 좌우 단서가 없을 때만 medium이다.
_SENSORY_FLAG = re.compile(r'감각 의존 지시\((위치|색|모양|소리)\)')
_HORIZONTAL_CUE = re.compile(r'오른쪽|왼쪽|우측|좌측|옆|우상단|우하단|좌상단|좌하단')
_SCREEN_EDGE_CUE = re.compile(r'(?:화면|페이지|창)의?\s?(?:상단|하단|위쪽|아래쪽|위|아래|맨\s?위|맨\s?아래)')
_QUOTED = re.compile(r'"([^"]*)"')

# 2026-10-13 이전 엔진이 만든 '위치 참조' 플래그. 보관해 둔 결과 파일을 다시 처리할 때만 들어온다.
# 위·아래는 읽는 순서와 맞으면 어느 정도 통해 medium, 좌우·옆은 단서가 없어 high였다 (2026-10-03).
_LEGACY_VERTICAL_LOCATION_FLAG = re.compile(r'"(위|아래)\(의\)"')


def classify_text_flag(flag: str, category: str) -> dict[str, Any]:
    """Return standards metadata for one text-engine flag."""
    if "문장 길이 과다" in flag:
        issue_type, wcag_id, wcag_name, priority = (
            "sentence_length", "3.1.5", "읽기 수준", "high"
        )
    elif "어려운 어휘 과다" in flag:
        issue_type, wcag_id, wcag_name, priority = (
            "hard_vocab_ratio", "3.1.5", "읽기 수준", "medium"
        )
    elif "어려운 어휘 포함" in flag:
        # 2026-10-02: 짧은 문단의 어려운 단어 플래그. 예전에는 아래 else로 빠져 유형이
        # text_analysis가 되어, 제안(short_text_hard_vocab)에 기준 번호가 붙지 않았다.
        issue_type, wcag_id, wcag_name, priority = (
            "short_text_hard_vocab", "3.1.5", "읽기 수준", "medium"
        )
    elif "읽기 수준 초과" in flag:
        # 2026-10-02 추가. 문단 난이도 점수가 기준을 넘었는데 문장 길이·어휘 원인 플래그가
        # 없을 때 붙는다. 예전에는 standard_issues가 비어 백엔드에서 분류되지 않았다.
        issue_type, wcag_id, wcag_name, priority = (
            "reading_level", "3.1.5", "읽기 수준", "medium"
        )
    elif "명사 나열" in flag:
        # 2026-10-02 추가. 읽기 수준 문제로 본다(KWCAG 직접 대응 없음).
        issue_type, wcag_id, wcag_name, priority = (
            "noun_stacking", "3.1.5", "읽기 수준", "medium"
        )
    elif _SENSORY_FLAG.search(flag):
        # 2026-10-13: 예전 "위치 참조" 플래그(location_dependency)를 이름 없이 위치·색·모양·소리로만
        # 가리키는 안내로 좁혀 대체했다. 기준은 같은 1.3.3(KWCAG 5.3.3)이고 유형 이름만 바뀐다.
        kind = _SENSORY_FLAG.search(flag).group(1)
        quoted = _QUOTED.search(flag)
        phrase = quoted.group(1) if quoted else ""
        screen_wide_only = (kind == "위치" and bool(_SCREEN_EDGE_CUE.search(phrase))
                            and not _HORIZONTAL_CUE.search(phrase))
        priority = "medium" if screen_wide_only else "high"
        issue_type, wcag_id, wcag_name = "sensory_instruction", "1.3.3", "감각적 특성"
    elif "위치 참조" in flag:
        priority = "medium" if _LEGACY_VERTICAL_LOCATION_FLAG.search(flag) else "high"
        issue_type, wcag_id, wcag_name = "location_dependency", "1.3.3", "감각적 특성"
    elif "모호한 참조" in flag:
        # 2026-10-03: "해당 ~"·"여기 클릭"은 위치 정보가 아니라 무엇을 가리키는지 모호한
        # 문제라 1.3.3(감각적 특성)이 아니라 2.4.4(링크 목적)로 본다. 페이지 감점은 없다.
        issue_type, wcag_id, wcag_name, priority = (
            "ambiguous_reference", "2.4.4", "링크 목적", "medium"
        )
    elif "텍스트 길이 과다" in flag:
        if category in {"link", "button"}:
            issue_type, wcag_id, wcag_name = "link_length", "2.4.4", "링크 목적"
            if category == "button":
                issue_type = "button_length"
            priority = "low" if category == "link" else "medium"
        elif category in {"form_guide", "label"}:
            issue_type = "form_guide_length" if category == "form_guide" else "label_length"
            wcag_id, wcag_name, priority = "3.3.2", "레이블 또는 설명", "low"
        elif category == "heading":
            issue_type, wcag_id, wcag_name, priority = (
                "heading_length", "2.4.6", "제목과 레이블", "low"
            )
        else:
            issue_type, wcag_id, wcag_name, priority = (
                "text_length", "3.1.5", "읽기 수준", "low"
            )
    else:
        issue_type, wcag_id, wcag_name, priority = (
            "text_analysis", "3.1.5", "읽기 수준", "low"
        )

    return {
        "type": issue_type,
        "flag": flag,
        "priority": priority,
        "wcag": {
            "id": wcag_id,
            "name": wcag_name,
            "standard": "WCAG",
            "version": "2.2",
        },
        "kwcag_items": kwcag_items_for_wcag(wcag_id),
    }


def classify_text_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    category = str(block.get("category", ""))
    return [
        classify_text_flag(str(flag), category)
        for flag in block.get("flags", [])
        if str(flag).strip()
    ]
