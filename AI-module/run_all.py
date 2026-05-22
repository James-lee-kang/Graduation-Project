"""
통합 실행기 - run_all.py

[역할]
  URL 하나를 입력하면 3개 분석 모듈을 순서대로 실행하고,
  각 모듈의 결과를 하나의 통합 JSON(result_final.json)으로 합쳐서
  총점과 등급을 계산

[이 파일의 역할 한 줄 요약]
  "전체 파이프라인의 지휘자. URL → 규칙 기반 → 난이도 분석 → CV 분석 → 총점 계산 → 백엔드 전송"

[실행 파이프라인 — 7단계]
  Step 1: [Node.js] 규칙 기반 평가 (axe-core + KWCAG 매핑 + 100점 감점 방식)
  Step 2: [Python]  HTML에서 분석 대상 텍스트 추출 + 카테고리 분류
  Step 3: [Python]  한국어 인지 난이도 분석 (MeCab 형태소 분석 기반)
  Step 4: [Python]  난이도 높은 문장에 대한 LLM 수정 제안 생성 (GPT-4o-mini)
  Step 5: [Python]  스크린샷 OCR → 명암비 측정 (Google Vision API)
  Step 6: 위 결과들을 합쳐서 총점 계산 → result_final.json 생성
  Step 7: result_final.json을 백엔드 서버에 POST 전송

[총점 계산 공식]
  총점 = (규칙 기반 점수 × 50%) + ((100 - 난이도 점수) × 30%) + (CV 통과율 × 20%)
  
  난이도 점수는 "높을수록 어려움"이므로 100에서 빼서 반전함.
  예: 난이도 20점(쉬움) → 100 - 20 = 80점이 총점에 반영됨.

[등급 기준]
  A+(95↑), A(90↑), B+(85↑), B(80↑), C(70↑), D(60↑), F(60 미만)

[모듈 부분 실패 처리]
  특정 모듈이 실패해도 나머지 모듈 결과는 정상적으로 반영
  실패한 모듈은 가중치 재분배 후 나머지 모듈만으로 총점을 계산
  예: CV 모듈만 실패 → 규칙 기반(50/80=62.5%)과 난이도(30/80=37.5%)로 재계산

[실행 방법]
  python run_all.py <URL>
  예: python run_all.py https://www.gov.kr

[출력]
  output/ 폴더에 모든 결과 파일이 저장됨:
    result.json                 ← axe-core 원본 + KWCAG 매핑 결과
    result_api.json             ← 규칙 기반 결과 (API 스펙 형태)
    result.html                 ← 렌더링된 HTML (텍스트 추출 입력)
    result.png                  ← 풀페이지 스크린샷 (CV 분석 입력)
    result_text.json            ← 추출된 텍스트 블록 (카테고리별 분류)
    result_text_difficulty.json ← 블록별 난이도 점수
    result_text_suggestions.json ← 블록별 수정 제안
    result_cv.json              ← 텍스트별 명암비 + 수정 추천 색상
    ★result_final.json          ← 최종 통합 결과 (백엔드가 받는 파일)
"""

import json
import sys
import os
import subprocess
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


# ── 설정 ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.resolve()

# 각 모듈의 소스 코드 경로
RULE_BASED_DIR = PROJECT_ROOT / "rule-based-analyzer"    # 모듈 1: 규칙 기반 (Node.js)
TEXT_LEVEL_DIR = PROJECT_ROOT / "text-level-analyzer"    # 모듈 2: 난이도 분석 (Python)
CV_ANALYZER_DIR = PROJECT_ROOT / "cv-analyzer"           # 모듈 3: CV 시각 분석 (Python)

# 결과 파일 출력 디렉토리 — 모든 모듈의 결과가 이 폴더에 모임
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Google Vision API 서비스 계정 키 경로
# .gitignore에 포함되어 있으므로 각 개발자가 로컬에 설정해야 함
VISION_CREDENTIALS = CV_ANALYZER_DIR / "uniaccess-495010-08a5c6701cd7.json"

# 백엔드 서버 주소 (Spring Boot 서버)
API_BASE_URL = "http://localhost:8080/api/v1"

# 총점 가중치
# 규칙 기반 50%: KWCAG 33개 항목 대부분을 커버하므로 가장 높은 비중
# 난이도 30%: 기존 도구에 없는 독창적 기능이므로 의미 있는 비중
# CV 20%: KWCAG 5.3.3 한 항목만 검사하므로 상대적으로 낮은 비중
WEIGHT_RULE_BASED = 0.50
WEIGHT_DIFFICULTY = 0.30
WEIGHT_CV = 0.20


# ── Step 실행 함수들 ─────────────────────────────────────────────────────────


def run_step(step_num: int, total: int, description: str):
    """각 Step의 시작을 콘솔에 출력하는 헬퍼 함수."""
    print(f"\n[Step {step_num}/{total}] {description}")
    print("-" * 50)


def run_command(cmd: list, cwd: str = None, description: str = "") -> bool:
    """
    외부 명령어(Node.js, Python 스크립트 등)를 subprocess로 실행
    
    [반환값]
    True: 정상 종료 (종료 코드 0)
    False: 실패 (비정상 종료, 타임아웃, 파일 없음 등)
    
    [타임아웃]
    각 Step은 최대 2분(120초)까지 대기함.
    공공 웹사이트 중 로딩이 느린 경우가 있어 여유 있게 설정
    
    [인코딩 처리]
    한국어 출력이 깨지지 않도록 PYTHONIOENCODING=utf-8 환경변수를 설정하고,
    stdout/stderr를 UTF-8로 디코딩
    """
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=False,
            timeout=120,
            env=env,
        )

        stdout = result.stdout.decode('utf-8', errors='replace').strip()
        stderr = result.stderr.decode('utf-8', errors='replace').strip()

        if stdout:
            print(stdout)

        if stderr:
            print(stderr)

        if result.returncode != 0:
            print(f"  [실패] {description} (종료 코드: {result.returncode})")
            return False

        return True

    except subprocess.TimeoutExpired:
        print(f"  [시간초과] {description} - 2분 초과")
        return False
    except FileNotFoundError as e:
        print(f"  [실행불가] {e}")
        return False
    except Exception as e:
        print(f"  [오류] {description}: {e}")
        return False


def load_json(filepath: Path) -> Optional[Dict]:
    """JSON 파일을 읽어서 딕셔너리로 반환. 파일이 없으면 None을 반환."""
    if not filepath.exists():
        print(f"  [경고] 파일 없음: {filepath.name}")
        return None

    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── 총점 계산 ────────────────────────────────────────────────────────────────


def calculate_total_score(rule_score: Optional[Dict],
                          difficulty_score: Optional[Dict],
                          cv_score: Optional[Dict]) -> Dict[str, Any]:
    """
    3개 모듈의 개별 점수를 가중 합산하여 총점과 등급을 계산
    
    [총점 공식]
    총점 = (규칙 기반 점수 × 50%) + ((100 - 난이도 점수) × 30%) + (CV 통과율 × 20%)
    
    [각 모듈 점수의 의미]
    - 규칙 기반: scorer.js가 계산한 100점 감점 방식 점수 (높을수록 좋음)
    - 난이도: difficulty_engine.py의 overall_score (높을수록 어려움 → 100에서 빼서 반전)
    - CV: contrast_analyzer.py의 pass_rate (명암비 통과율 %, 높을수록 좋음)
    
    [모듈 부분 실패 시 가중치 재분배]
    특정 모듈이 실패하면 해당 모듈의 가중치를 제외하고,
    나머지 모듈의 가중치를 합이 100%가 되도록 재분배함.
    예: CV 실패 → 규칙 기반 50/(50+30)=62.5%, 난이도 30/(50+30)=37.5%
    이렇게 하면 한 모듈이 실패해도 나머지만으로 의미 있는 총점을 계산할 수 있음.
    """
    scores = {}
    weights = {}

    # 규칙 기반 점수 추출
    if rule_score:
        score_val = rule_score.get("score", {})
        if isinstance(score_val, dict):
            scores["rule_based"] = score_val.get("score", 0)
        else:
            scores["rule_based"] = score_val
        weights["rule_based"] = WEIGHT_RULE_BASED

    # 난이도 점수 추출 — 100에서 빼서 "높을수록 좋음"으로 반전
    if difficulty_score:
        difficulty_val = difficulty_score.get("overall_score", 0)
        scores["difficulty"] = 100 - difficulty_val
        weights["difficulty"] = WEIGHT_DIFFICULTY

    # CV 점수 추출 — 명암비 통과율(%)을 그대로 사용
    if cv_score:
        summary = cv_score.get("summary", {})
        scores["cv"] = summary.get("pass_rate", 0)
        weights["cv"] = WEIGHT_CV

    # 모든 모듈이 실패한 경우
    total_weight = sum(weights.values())
    if total_weight == 0:
        return {
            "total_score": 0,
            "grade": "F",
            "module_scores": {},
            "weights_applied": {},
        }

    # 가중 합산 — 실패한 모듈을 제외하고 나머지 가중치를 재분배함
    weighted_sum = 0
    weights_applied = {}
    for module, score in scores.items():
        normalized_weight = weights[module] / total_weight  # 재분배된 가중치
        weighted_sum += score * normalized_weight
        weights_applied[module] = round(normalized_weight * 100, 1)

    total_score = round(weighted_sum, 1)

    # 등급 판정
    if total_score >= 95:
        grade = "A+"
    elif total_score >= 90:
        grade = "A"
    elif total_score >= 85:
        grade = "B+"
    elif total_score >= 80:
        grade = "B"
    elif total_score >= 70:
        grade = "C"
    elif total_score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "total_score": total_score,
        "grade": grade,
        "module_scores": {k: round(v, 1) for k, v in scores.items()},
        "weights_applied": weights_applied,
    }


# ── 통합 결과 JSON 생성 ─────────────────────────────────────────────────────


def build_final_result(url, rule_result, difficulty_result,
                       suggestion_result, cv_result, total_score, elapsed):
    """
    모든 모듈의 결과 + 총점을 하나의 JSON으로 합침.
    이 JSON(result_final.json)이 백엔드가 받아서 DB에 저장하는 최종 결과물임
    
    [구조]
    - 상단: URL, 총점, 등급, 소요 시간 등 요약 정보
    - score_breakdown: 모듈별 점수 + 적용된 가중치
    - modules: 각 모듈의 상세 결과 전체 (위반 항목, 수정 가이드 등)
    
    프론트엔드 대시보드는 이 JSON 하나로
    총점/등급, 모듈별 점수, 위반 항목 목록, 수정 가이드를 모두 렌더링
    """
    return {
        "url": url,
        "analyzed_at": datetime.now().isoformat(),
        "elapsed_seconds": elapsed,
        "platform_version": "1.0.0",

        "total_score": total_score["total_score"],
        "grade": total_score["grade"],
        "score_breakdown": {
            "module_scores": total_score["module_scores"],
            "weights_applied": total_score["weights_applied"],
        },

        # 각 모듈의 상세 결과를 그대로 포함함.
        # 모듈이 실패한 경우 status: "failed" 객체로 대체됨.
        "modules": {
            "rule_based": rule_result or {
                "status": "failed", "message": "규칙 기반 평가 실패"
            },
            "text_difficulty": difficulty_result or {
                "status": "failed", "message": "난이도 분석 실패"
            },
            "text_suggestions": suggestion_result or {
                "status": "failed", "message": "수정 제안 생성 실패"
            },
            "cv_visual": cv_result or {
                "status": "failed", "message": "CV 분석 실패"
            },
        },
    }


# ── 백엔드 전송 ──────────────────────────────────────────────────────────────


def send_to_backend(final_result: Dict) -> bool:
    """
    result_final.json을 백엔드 서버에 HTTP POST로 전송함.
    
    백엔드 서버가 꺼져 있거나 연결할 수 없는 경우에도
    로컬 JSON 파일(result_final.json)은 이미 저장되어 있으므로
    나중에 수동으로 전송하거나 파일을 직접 확인할 수 있음.
    
    [엔드포인트]
    POST http://localhost:8080/api/v1/evaluations
    Body: result_final.json 전체
    """
    import urllib.request
    import urllib.error

    url = f"{API_BASE_URL}/evaluations"

    try:
        data = json.dumps(final_result, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status in (200, 201):
                print(f"  백엔드 전송 성공 (HTTP {response.status})")
                return True
            else:
                print(f"  백엔드 전송 실패 (HTTP {response.status})")
                return False

    except urllib.error.URLError:
        print(f"  백엔드 서버 연결 불가 ({API_BASE_URL})")
        print(f"  -> 로컬 JSON 파일로만 저장됩니다.")
        return False
    except Exception as e:
        print(f"  백엔드 전송 오류: {e}")
        print(f"  -> 로컬 JSON 파일로만 저장됩니다.")
        return False


# ── 메인 실행 ────────────────────────────────────────────────────────────────


def main():
    """
    전체 파이프라인을 순서대로 실행하는 메인 함수.
    
    [실행 순서와 의존 관계]
    Step 1 (규칙 기반) → result.json, result.html, result.png 생성
    Step 2 (텍스트 추출) → Step 1의 result.html을 입력으로 사용
    Step 3 (난이도 분석) → Step 2의 result_text.json을 입력으로 사용
    Step 4 (수정 제안)  → Step 3의 result_text_difficulty.json을 입력으로 사용
    Step 5 (CV 분석)   → Step 1의 result.png를 입력으로 사용
    Step 6 (통합)      → 위 모든 결과 파일을 읽어서 총점 계산
    Step 7 (전송)      → Step 6의 result_final.json을 백엔드로 POST
    
    각 Step은 이전 Step의 출력 파일이 존재하는지 확인하고,
    없으면 해당 Step을 건너뜀 (부분 실패 허용).
    """
    if len(sys.argv) < 2:
        print("사용법: python run_all.py <URL>")
        print("예시:   python run_all.py https://www.gov.kr")
        sys.exit(1)

    url = sys.argv[1]
    start_time = time.time()

    print("=" * 60)
    print("  공공 디지털 서비스 접근성 통합 평가")
    print("=" * 60)
    print(f"  대상 URL: {url}")
    print(f"  시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  가중치: 규칙 {int(WEIGHT_RULE_BASED*100)}% / "
          f"난이도 {int(WEIGHT_DIFFICULTY*100)}% / "
          f"CV {int(WEIGHT_CV*100)}%")
    print("=" * 60)

    total_steps = 7

    # ── Step 1: 규칙 기반 평가 ──
    # run.js를 실행하여 Playwright로 페이지를 열고 axe-core 검사를 수행함.
    # 결과: result.json(axe-core 결과), result.html(렌더링 HTML), result.png(스크린샷)
    run_step(1, total_steps, "규칙 기반 접근성 평가 (axe-core + KWCAG)")

    result_json_path = str(OUTPUT_DIR / "result.json")
    step1_ok = run_command(
        ["node", "run.js", url, result_json_path],
        cwd=str(RULE_BASED_DIR),
        description="규칙 기반 평가",
    )

    # ── Step 2: 텍스트 추출 ──
    # Step 1에서 저장한 result.html을 입력으로 받아서
    # 분석 대상 텍스트를 추출하고 10개 카테고리로 분류함.
    run_step(2, total_steps, "텍스트 추출 전처리")

    result_html = OUTPUT_DIR / "result.html"
    if result_html.exists():
        step2_ok = run_command(
            ["python", str(TEXT_LEVEL_DIR / "text_extractor.py"),
             str(result_html)],
            cwd=str(OUTPUT_DIR),
            description="텍스트 추출",
        )
    else:
        print("  [건너뜀] result.html 파일이 없습니다.")
        step2_ok = False

    # ── Step 3: 난이도 분석 ──
    # Step 2에서 생성한 result_text.json을 입력으로 받아서
    # MeCab 형태소 분석 → 난이도 점수 산출 (문장 길이, 어절 길이, 고난이도 어휘 비율)
    run_step(3, total_steps, "한국어 인지 난이도 분석")

    result_text = OUTPUT_DIR / "result_text.json"
    if result_text.exists():
        step3_ok = run_command(
            ["python", str(TEXT_LEVEL_DIR / "difficulty_engine.py"),
             str(result_text)],
            cwd=str(OUTPUT_DIR),
            description="난이도 분석",
        )
    else:
        print("  [건너뜀] result_text.json 파일이 없습니다.")
        step3_ok = False

    # ── Step 4: LLM 수정 제안 ──
    # Step 3에서 난이도가 높다고 판정된 문장에 대해
    # GPT-4o-mini에게 쉬운 표현으로의 수정안을 생성하도록 요청함.
    # (GPT는 측정이 아닌 수정 제안 생성에만 사용 — 측정은 자체 엔진이 담당)
    run_step(4, total_steps, "LLM 수정 제안 생성")

    result_difficulty = OUTPUT_DIR / "result_text_difficulty.json"
    if result_difficulty.exists():
        step4_ok = run_command(
            ["python", str(TEXT_LEVEL_DIR / "suggestion_generator.py"),
             str(result_difficulty)],
            cwd=str(OUTPUT_DIR),
            description="수정 제안 생성",
        )
    else:
        print("  [건너뜀] result_text_difficulty.json 파일이 없습니다.")
        step4_ok = False

    # ── Step 5: CV 시각 분석 ──
    # Step 1에서 저장한 result.png(스크린샷 1장)를 입력으로 받아서
    # Google Vision API OCR → 텍스트 위치 추출 → 명암비 측정 → 수정 색상 추천
    run_step(5, total_steps, "CV 시각 접근성 분석 (OCR + 명암비)")

    result_png = OUTPUT_DIR / "result.png"
    if result_png.exists():
        step5_ok = run_command(
            ["python", str(CV_ANALYZER_DIR / "cv_runner.py"),
             str(result_png),
             "--credentials", str(VISION_CREDENTIALS),
             "--output", str(OUTPUT_DIR / "result_cv.json")],
            cwd=str(OUTPUT_DIR),
            description="CV 분석",
        )
    else:
        print("  [건너뜀] result.png 파일이 없습니다.")
        step5_ok = False

    # ── Step 6: 결과 통합 + 총점 계산 ──
    # 각 모듈이 생성한 JSON 파일을 읽어서 총점을 계산하고,
    # 모든 결과를 하나의 result_final.json으로 합침.
    run_step(6, total_steps, "결과 통합 및 총점 계산")

    rule_result = load_json(OUTPUT_DIR / "result_api.json")
    difficulty_result = load_json(OUTPUT_DIR / "result_text_difficulty.json")
    suggestion_result = load_json(OUTPUT_DIR / "result_text_suggestions.json")
    cv_result = load_json(OUTPUT_DIR / "result_cv.json")

    total_score = calculate_total_score(rule_result, difficulty_result, cv_result)

    elapsed = round(time.time() - start_time, 2)

    final_result = build_final_result(
        url=url,
        rule_result=rule_result,
        difficulty_result=difficulty_result,
        suggestion_result=suggestion_result,
        cv_result=cv_result,
        total_score=total_score,
        elapsed=elapsed,
    )

    # 최종 통합 결과를 JSON 파일로 저장함
    final_path = OUTPUT_DIR / "result_final.json"
    with open(final_path, 'w', encoding='utf-8') as f:
        json.dump(final_result, f, ensure_ascii=False, indent=2)

    print(f"  통합 결과 저장: {final_path}")

    # ── Step 7: 백엔드 전송 ──
    # 백엔드 서버가 실행 중이면 result_final.json을 POST로 전송함.
    # 서버가 꺼져 있어도 로컬 파일은 이미 저장되어 있으므로 문제없음.
    run_step(7, total_steps, "백엔드 서버 전송")

    send_to_backend(final_result)

    # ── 최종 요약 출력 ──
    print("\n" + "=" * 60)
    print("  평가 완료")
    print("=" * 60)
    print(f"  URL: {url}")
    print(f"  소요 시간: {elapsed}초")
    print()

    print(f"  ★ 총점: {total_score['total_score']}점 / 100점"
          f" (등급: {total_score['grade']})")
    print()

    module_names = {
        "rule_based": "규칙 기반",
        "difficulty": "난이도 (접근성 변환)",
        "cv": "CV 시각 분석",
    }
    for module, score in total_score["module_scores"].items():
        weight = total_score["weights_applied"].get(module, 0)
        name = module_names.get(module, module)
        print(f"    {name}: {score}점 (가중치 {weight}%)")

    print()

    # 각 Step의 성공/실패 상태를 요약 출력함
    steps = [
        (step1_ok, "규칙 기반 평가"),
        (step2_ok, "텍스트 추출"),
        (step3_ok, "난이도 분석"),
        (step4_ok, "수정 제안 생성"),
        (step5_ok, "CV 시각 분석"),
    ]

    for ok, name in steps:
        status = "OK" if ok else "FAIL"
        print(f"    [{status}] {name}")

    print()
    print(f"  결과 폴더: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
