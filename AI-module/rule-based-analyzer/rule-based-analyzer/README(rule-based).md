# rule-based-analyzer

공공 웹사이트 접근성 자동 평가 플랫폼 **UniAccess**의 규칙 기반 분석 모듈.  
Playwright로 웹페이지를 렌더링하고, axe-core로 접근성을 검사한 뒤, 결과를 KWCAG 2.2 기준으로 변환하여 100점 감점제 점수를 산출한다.

---

## 파일 구성

```
rule-based-analyzer/
├── run.js        진입점. URL을 받아 전체 파이프라인을 실행
├── adapter.js    axe-core 결과(WCAG 기준) → KWCAG 2.2 33개 항목으로 변환
├── mapping.js    KWCAG ↔ WCAG ↔ axe-core 규칙 ID 매핑 테이블
└── scorer.js     KWCAG 변환 결과 → 100점 감점제 점수 산출
```

---

## 실행 방법

```powershell
cd rule-based-analyzer
node run.js <URL> [출력파일.json]

# 예시
node run.js https://www.mohw.go.kr result.json
```

실행하면 세 파일이 생성된다.

| 출력 파일 | 용도 |
|---|---|
| `result.json` | 규칙기반모듈 최종 결과(내부 형식) (디버깅용, camelCase) |
| `result_api.json` | result.json을 백엔드 스펙 형식으로 변환한 결과 (run_all.py가 읽어서 통합에 사용) |
| `result.html` | 렌더링된 DOM (문장난이도 모듈 입력용) |
| `result.png` | 풀페이지 스크린샷 (CV 모듈 입력용) |

> 실제 서비스에서는 `run_all.py`가 이 파일을 호출하여 결과를 `output/` 폴더에 저장한다.  
> 단독 실행 시에는 `rule-based-analyzer/` 폴더 안에 결과 파일이 생성된다.

---

## 전체 파이프라인

```
[run.js] ← URL 입력
    │
    ├─ axe-core 검사 (WCAG 기준)
    │       │
    │   [adapter.js] ← mapping.js 참조
    │       │  axe 결과 → KWCAG 33개 항목으로 재분류
    │       ↓
    │   [scorer.js]
    │       │  100점 감점제 점수 산출
    │       ↓
    ├─ result.json / result_api.json 저장
    ├─ result.html 저장 → text_extractor.py (AI 모듈) 입력
    └─ result.png 저장  → cv_runner.py (CV 모듈) 입력
```

---

## 파일별 역할

### run.js — 진입점 (오케스트레이터)

전체 파이프라인을 순서대로 실행하는 최상위 파일.

1. Playwright로 헤드리스 Chrome을 띄워 페이지 렌더링
2. 렌더링된 HTML 저장 (`result.html`) — 문장난이도 모듈이 이 파일로 텍스트를 추출
3. 풀페이지 스크린샷 저장 (`result.png`) — CV 모듈이 이 파일로 명암비를 분석
4. axe-core 실행 (WCAG 2.0/2.1/2.2 A/AA 등급 대상)
5. `adapter.convert()` 호출 → KWCAG 변환
6. `scorer.score()` 호출 → 점수 산출
7. `toApiFormat()` 호출 → snake_case 변환 후 JSON 저장

**Playwright는 run.js 한 곳에서만 실행**  
규칙 기반 모듈과 AI/CV 모듈이 각자 브라우저를 띄우면 리소스가 낭비되고, 렌더링 시점이 달라 데이터 일관성이 깨진다. run.js에서 "렌더링된 최종 DOM"을 파일로 저장하고, 다른 모듈은 그 파일을 소비하는 방식으로 역할을 분리했다.

---

### adapter.js — WCAG → KWCAG 변환기

axe-core는 국제 표준인 WCAG 기준으로 결과를 출력하지만, 본 프로젝트는 한국형 지침인 KWCAG 2.2 기준으로 평가한다. adapter.js가 이 변환을 담당한다.

**2단계 매핑 방식 (Two-stage Resolution):**

| 단계 | 방법 | 예시 |
|---|---|---|
| 1단계 (직접 매핑) | axe-core 규칙 ID → KWCAG 번호 직접 조회 | `image-alt` → `5.1.1` |
| 2단계 (fallback) | WCAG 태그 번호 추출 → KWCAG 번호 조회 | `wcag412` → WCAG `4.1.2` → `8.1.1`, `8.2.1` |
| 실패 (unmapped) | 두 단계 모두 실패 시 unmapped 목록에 보존 | 정보 유실 방지 |

1단계가 더 정확하고, 2단계는 1단계 실패 시 안전망 역할을 한다.  
매핑 실패 항목(unmapped)도 버리지 않고 별도 보존하여 WCAG 참조 정보를 유지한다.

---

### mapping.js — 매핑 테이블

KWCAG 33개 검사항목 정의와 axe-core 규칙 ID 매핑 데이터를 담고 있다.

**각 항목에 포함된 정보:**

| 필드 | 의미 | 사용처 |
|---|---|---|
| `name` | KWCAG 항목명 | 출력 및 대시보드 표시 |
| `wcag` | 대응 WCAG 번호 배열 | 2단계 폴백 매핑 |
| `module` | 담당 모듈 (규칙기반 / 문장 난이도 분석 / CV / 수동) | 모듈 분업 구분 |
| `weight` | 항목 중요도 (high / medium / low) | scorer.js 감점 배수 결정 |
| `severity` | 위반 시 영향도 (critical / major / minor) | scorer.js 기본 감점값 결정 |
| `axeRules` | 대응 axe-core 규칙 ID 목록 | 1단계 직접 매핑 |

**weight와 severity의 구분:**

- `severity`: 이 항목을 위반했을 때 장애 사용자에게 미치는 영향도 → **감점 기준값** (critical=3점, major=2점, minor=1점)
- `weight`: 이 항목이 전체 점수에서 차지하는 중요도 → **감점 배수** (high=×1.5, medium=×1.0, low=×0.5)

두 값이 조합되어 항목별 감점이 결정된다. `axeRules`가 빈 배열인 항목(module이 AI분석/CV/수동)은 axe-core로 자동 검사가 불가능한 항목으로, 해당 모듈이 별도로 담당한다.

---

### scorer.js — 점수 산출

adapter.js의 변환 결과를 받아 100점 감점제 점수를 계산한다.

**감점 공식:**
```
항목별 감점 = severity 기본 감점 × weight 배수 × 위반 노드 수
```

**severity 기본 감점:**

| 등급 | 점수 | 기준 |
|---|---|---|
| critical | 3점/건 | 장애인 접근 자체 불가 (예: 대체 텍스트 누락) |
| major | 2점/건 | 심각한 사용 불편 (예: heading 순서 오류) |
| minor | 1점/건 | 경미한 불편 (예: lang 속성 누락) |

**weight 배수:**

| 등급 | 배수 | 기준 |
|---|---|---|
| high | ×1.5 | 핵심 항목 (WCAG Level A 대응) |
| medium | ×1.0 | 중요 항목 (WCAG Level AA 대응) |
| low | ×0.5 | 부가 항목 |

**계산 예시:**
```
5.1.1 (severity=critical, weight=high): alt 없는 <img> 5개 발견
→ 3 × 1.5 × 5 = 22.5점 감점

7.1.1 (severity=minor, weight=medium): lang 속성 누락 1건
→ 1 × 1.0 × 1 = 1점 감점
```

KWCAG에 매핑되지 않은 unmapped 위반은 minor × medium (건당 1점)으로 감점한다.

**등급 기준:**

| 점수 | 등급 | 의미 |
|---|---|---|
| 95점 이상 | A | 우수 |
| 85점 이상 | B | 양호 |
| 70점 이상 | C | 보통 |
| 50점 이상 | D | 미흡 |
| 50점 미만 | F | 심각 |

---

## 의존성

```json
"dependencies": {
  "@axe-core/playwright": "^4.11.1",
  "playwright": "^1.x"
}
```

```powershell
npm install
npx playwright install chromium
```

---

## 자동화 검사 범위

axe-core는 KWCAG 33개 항목 중 규칙 기반으로 자동 검사 가능한 항목만 커버한다.  
나머지 항목은 아래 모듈이 담당하거나 수동 검토가 필요하다.

| 모듈 | 담당 항목 예시 |
|---|---|
| 규칙기반 (이 모듈) | 대체 텍스트, 명도 대비, heading 구조, 레이블 등 |
| AI 분석 (text-level-analyzer) | 명확한 지시사항 제공 (5.3.3) — 텍스트 난이도 |
| CV 분석 (cv-analyzer) | 이미지 내 텍스트 명암비, 콘텐츠 간 구분 |
| 수동 검토 | 키보드 사용 보장, 깜빡임 제한, 포인터 입력 등 |

WAVE나 Lighthouse 등 기존 도구도 자동화 가능 범위는 전체의 30~40% 수준이며, 나머지는 수동 검토가 필요하다는 점은 업계 표준과 동일하다.
