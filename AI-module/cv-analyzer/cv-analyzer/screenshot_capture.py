"""
CV 모듈 - 스크린샷 캡처 모듈
ai-analysis/cv/screenshot_capture.py

[역할]
  입력 URL의 웹사이트에서 대표 페이지를 최대 5개 샘플링하고,
  각 페이지의 풀페이지 스크린샷을 이미지 파일로 저장
  이 스크린샷들이 다음 단계(vision_ocr.py → contrast_analyzer.py)의 입력이 됨.

[왜 여러 페이지를 캡처하는가]
  웹사이트의 접근성 문제는 특정 페이지 유형에 집중되는 경향이 있음.
  예를 들어 로그인 페이지는 폼 요소가 많아 접근성 위반이 잦고,
  FAQ 페이지는 텍스트 밀도가 높아 명암비 위반이 자주 발생함.
  메인 페이지 1장만 분석하면 이런 문제를 놓칠 수 있으므로,
  접근성 취약 페이지 유형을 우선 선택하여 최대 5개까지 샘플링함.

[run.js와의 관계]
  run.js는 메인 URL 1개의 스크린샷(result.png)만 저장
  이 모듈은 그 사이트의 서브페이지들(로그인, 민원, FAQ 등)을
  추가로 캡처하여 CV 분석의 커버리지를 넓히는 역할

[전체 파이프라인에서의 위치]
  run.js (메인 페이지 스크린샷 1장 저장)
    → ★screenshot_capture.py (대표 서브페이지 샘플링 + 스크린샷 저장)
    → vision_ocr.py (각 스크린샷에서 OCR 텍스트 추출)
    → contrast_analyzer.py (텍스트 위치의 명암비 측정)

[실행 방법]
  python ai-analysis/cv/screenshot_capture.py <URL> [출력디렉토리]
  예: python ai-analysis/cv/screenshot_capture.py https://www.gov.kr screenshots/

[출력]
  <출력디렉토리>/
    index.json      - 캡처된 페이지 목록 및 메타 정보 (vision_ocr.py가 이 파일로 처리 대상을 파악함)
    page_0.png      - 메인 페이지 스크린샷
    page_1.png      - 서브페이지 1 스크린샷
    ...             - 최대 MAX_PAGES(5)개까지
"""

import sys
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


# ── 상수 ──────────────────────────────────────────────────────────────────────

MAX_PAGES = 5           # 최대 샘플링 페이지 수 (Google Vision API 무료 티어 월 1,000건 고려)
PAGE_LOAD_WAIT = 3000   # 페이지 렌더링 추가 대기 ms (SPA 등 동적 콘텐츠 로딩 대기용)
VIEWPORT = {"width": 1280, "height": 720}  # run.js와 동일한 뷰포트 크기로 통일

# 대표 페이지 우선 선택 패턴 (우선순위 순서)
# 공공 웹사이트에서 접근성 문제가 자주 발생하는 페이지 유형을 먼저 캡처함.
# 예: 로그인 페이지 → 폼 요소 접근성 취약, FAQ → 텍스트 밀도 높아 명암비 위반 빈번
PRIORITY_PATTERNS = [
    r'/login',      # 로그인 - 폼 요소 접근성 취약 빈번
    r'/signin',
    r'/mypage',     # 마이페이지 - 개인정보 폼
    r'/apply',      # 민원 신청 - 복잡한 폼
    r'/faq',        # FAQ - 텍스트 밀도 높음
    r'/notice',     # 공지사항
    r'/board',      # 게시판
    r'/search',     # 검색 결과
    r'/guide',      # 이용 안내
    r'/service',    # 서비스 소개
]

# 수집 제외 패턴 - 접근성 분석 대상이 아닌 URL
# 파일 다운로드 링크, 앵커, JavaScript 호출 등은 웹페이지가 아니므로 제외함
EXCLUDE_PATTERNS = [
    r'\.(pdf|docx?|xlsx?|hwp|zip|jpg|png|gif|svg|css|js)$',  # 파일 다운로드
    r'#',           # 앵커 링크 (같은 페이지 내 이동)
    r'javascript:',
    r'mailto:',
    r'tel:',
    r'/logout',
    r'/api/',
]


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────

def is_same_domain(url: str, base_url: str) -> bool:
    """
    링크가 베이스 URL과 같은 도메인인지 확인함.
    서브도메인은 같은 사이트로 간주함.
    예: www.gov.kr과 m.gov.kr → 같은 사이트(gov.kr)로 판단
    """
    try:
        base_root = '.'.join(urlparse(base_url).netloc.split('.')[-2:])
        link_root = '.'.join(urlparse(url).netloc.split('.')[-2:])
        return base_root == link_root
    except Exception:
        return False


def should_exclude(url: str) -> bool:
    """수집 제외 패턴(EXCLUDE_PATTERNS)에 해당하는 URL인지 확인함."""
    return any(re.search(p, url, re.IGNORECASE) for p in EXCLUDE_PATTERNS)


def get_priority_score(url: str) -> int:
    """
    URL의 우선순위 점수를 반환함. 낮을수록 고우선순위.
    PRIORITY_PATTERNS에 매칭되는 패턴의 인덱스를 반환하며,
    매칭되는 패턴이 없으면 가장 낮은 우선순위(= 리스트 길이)를 반환함.
    """
    for i, pattern in enumerate(PRIORITY_PATTERNS):
        if re.search(pattern, url, re.IGNORECASE):
            return i
    return len(PRIORITY_PATTERNS)


def collect_links(page, base_url: str) -> list:
    """
    현재 페이지에서 같은 도메인의 내부 링크를 수집하고,
    우선순위(접근성 취약 페이지 유형) 순으로 정렬하여 반환함.

    [브라우저 내부 JavaScript(evaluate)로 수집하는 이유]
    일부 공공 사이트는 onclick 이벤트로 페이지를 이동하거나,
    JavaScript가 실행된 후에야 href 값이 채워지는 경우가 있음.
    page.evaluate()를 쓰면 최종 렌더링된 DOM에서 href를 가져올 수 있음.

    [필터링 과정]
    1. 같은 도메인 링크만 남김 (외부 사이트 제외)
    2. 제외 패턴(파일, 앵커, API 등) 해당 링크 제거
    3. 쿼리스트링을 제거하여 중복 판단 (같은 페이지의 ?tab=1, ?tab=2 구분 방지)
    4. 우선순위 패턴 순으로 정렬
    """
    raw_links = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]'))
              .map(a => a.href)
              .filter(href => href && href.startsWith('http'))
    """)

    seen = set()
    filtered = []
    for link in raw_links:
        clean = link.split('?')[0].rstrip('/')  # 쿼리스트링 제거 후 중복 판단
        if clean in seen:
            continue
        seen.add(clean)
        if is_same_domain(link, base_url) and not should_exclude(link):
            filtered.append(link)

    filtered.sort(key=lambda u: (get_priority_score(u), u))
    return filtered


def capture_page(page, url: str, output_path: Path, page_index: int) -> dict:
    """
    단일 페이지를 캡처하고 메타 정보를 반환함.
    
    Playwright의 page.screenshot(full_page=True)를 사용하여
    스크롤 없이 페이지 전체를 하나의 이미지로 저장함.
    캡처 실패 시(타임아웃, 네트워크 오류 등) None을 반환하고
    다음 페이지로 진행함 — 한 페이지 실패가 전체 파이프라인을 멈추지 않음.
    """
    try:
        print(f"  [{page_index}] 캡처 중: {url}")
        start = time.time()

        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(PAGE_LOAD_WAIT)

        screenshot_filename = f"page_{page_index}.png"
        page.screenshot(path=str(output_path / screenshot_filename), full_page=True)

        elapsed = int((time.time() - start) * 1000)
        title = page.title()
        print(f"      완료 ({elapsed}ms) - {title[:40]}")

        return {
            "index": page_index,
            "url": url,
            "screenshot": screenshot_filename,
            "title": title,
            "capture_time_ms": elapsed,
        }

    except Exception as e:
        print(f"      실패: {e}")
        return None


# ── 메인 실행 함수 ────────────────────────────────────────────────────────────

def run(base_url: str, output_dir: str = "screenshots") -> dict:
    """
    base_url(메인 페이지)을 포함해 최대 MAX_PAGES개의 대표 페이지를 캡처함.

    [샘플링 전략]
      1. base_url(메인 페이지)을 먼저 캡처함
      2. 메인 페이지가 열린 상태에서 내부 링크를 수집함
      3. 수집된 링크를 우선순위 패턴(로그인, 민원, FAQ 등)으로 정렬함
      4. 우선순위가 높은 순서대로 캡처하되, MAX_PAGES에 도달하면 종료함

    [페이지 수를 5개로 제한하는 이유]
      Google Vision API 무료 티어가 월 1,000건이므로,
      한 사이트에 너무 많은 페이지를 캡처하면 금방 소진됨.
      접근성 문제가 집중되는 핵심 페이지 유형 5개만 샘플링하는 것이
      비용 대비 분석 커버리지를 최대화하는 전략임.
      (같은 이미지 재분석 방지를 위한 캐싱은 vision_ocr.py에서 처리함)

    [반환값]
      {
        "base_url": str,              ← 분석 대상 사이트 URL
        "captured_pages": list[dict],  ← 캡처된 각 페이지의 메타 정보
        "total_captured": int,         ← 실제 캡처 성공한 페이지 수
        "output_dir": str,             ← 스크린샷 저장 디렉토리 절대 경로
        "timestamp": str,              ← 캡처 시각
      }
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\nCV 모듈 - 스크린샷 캡처")
    print(f"대상: {base_url}")
    print(f"최대 페이지 수: {MAX_PAGES}")
    print("─" * 50)

    captured_pages = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ko-KR", viewport=VIEWPORT)
        page = context.new_page()

        # ── 1) 메인 페이지 캡처 ──
        result = capture_page(page, base_url, output_path, page_index=0)
        if result:
            captured_pages.append(result)

        # ── 2) 내부 링크 수집 (메인 페이지가 열려 있는 상태에서 수집) ──
        if result:
            print("\n내부 링크 수집 중...")
            candidates = collect_links(page, base_url)
            print(f"  수집된 후보 링크: {len(candidates)}개")

            for link in candidates[:3]:
                idx = get_priority_score(link)
                label = PRIORITY_PATTERNS[idx] if idx < len(PRIORITY_PATTERNS) else "일반"
                print(f"  → [{label}] {link}")
            if len(candidates) > 3:
                print(f"  ... 외 {len(candidates) - 3}개")
            print()
        else:
            candidates = []

        # ── 3) 서브페이지 순서대로 캡처 (MAX_PAGES - 1개, 메인 1개는 이미 포함) ──
        for link in candidates:
            if len(captured_pages) >= MAX_PAGES:
                break
            result = capture_page(page, link, output_path, page_index=len(captured_pages))
            if result:
                captured_pages.append(result)

        browser.close()

    # ── 4) index.json 저장 ──
    # vision_ocr.py가 이 파일을 읽어서 어떤 스크린샷을 OCR 처리할지 파악함
    index_data = {
        "base_url": base_url,
        "captured_pages": captured_pages,
        "total_captured": len(captured_pages),
        "output_dir": str(output_path.resolve()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(output_path / "index.json", "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    # ── 5) 콘솔 요약 출력 ──
    print("─" * 50)
    print(f"캡처 완료: {len(captured_pages)} / {MAX_PAGES} 페이지")
    for p_info in captured_pages:
        print(f"  [{p_info['index']}] {p_info['screenshot']}  ←  {p_info['url']}")
    print(f"\n결과 저장: {output_path.resolve()}/")
    print(f"  index.json  - 페이지 목록 및 메타 정보")
    print(f"  page_N.png  - 각 페이지 스크린샷")
    print("─" * 50)

    return index_data


# ── CLI 진입부 ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python screenshot_capture.py <URL> [출력디렉토리]")
        print("예시:   python screenshot_capture.py https://www.gov.kr screenshots/")
        sys.exit(1)

    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "screenshots")
