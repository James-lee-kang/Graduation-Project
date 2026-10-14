# rule-based-analyzer

공공 웹사이트 접근성 자동 평가 플랫폼 **UniAccess**의 규칙 기반 분석 모듈.  
Playwright로 웹페이지를 렌더링하고, axe-core로 접근성을 검사한 뒤, 결과를 KWCAG 2.2 기준으로 변환하여 100점 감점제 점수를 산출한다.
브라우저는 이 모듈에서만 띄우므로, 문장 난이도 모듈이 읽을 DOM 스냅샷(`result.html`)과 CV 모듈이 쓸 전체 페이지 이미지도 여기서 만든다.

---

## 파일 구성

```
rule-based-analyzer/
├── run.js               진입점. URL을 받아 페이지 열기 → 대상 페이지 판정 → 팝업 → axe → 저장까지 실행
├── adapter.js           axe-core 결과(WCAG 기준) → KWCAG 2.2 33개 항목으로 변환
├── mapping.js           KWCAG ↔ WCAG ↔ axe-core 규칙 ID 매핑 테이블 (파이썬 모듈도 이 표를 씀)
├── scorer.js            KWCAG 변환 결과 → 100점 감점제 점수 산출 (등급 없음)
├── excluded-regions.js  광고(AD)·동적 영역(DYNAMIC) 판정과 표시, 위반을 점수 대상과 제외 영역으로 분리
├── popup-layers.js      레이어 팝업 찾기·따로 검사·저장·닫기 (제외 사유 POPUP)
├── carousel-audit.js    숨은 캐러셀 슬라이드 상태를 제한적으로 순회해 axe 결과 병합
├── hidden-elements.js   이 화면 폭에서 그려지지 않는 요소에 data-ua-hidden 표시
├── link-audit.js        axe에 없는 링크 검사 2개: 새 창 고지(7.2.1), 모호한 링크 텍스트(6.4.3) (2026-10-03)
├── axe-locale.js        axe 메시지를 한국어로: 공식 번역(axe-core locales/ko.json) + 보충 번역 (2026-10-13)
├── locales/ko-supplement.json  공식 번역에 없는 6규칙·10체크의 한국어 문구 (2026-10-13)
├── fix-hints.js         노드별 개선 안내: 명도 대비 추천 색, 조작 대상 크기·간격 (2026-10-13)
├── cv-anchors.js        CV 이미지를 찍는 순간의 요소 위치·내용 기록
├── artifact.js          내부 분석용 DOM 스냅샷 직렬화, 위반 요소 위치(locator), 애니메이션 정지
├── test/                Node 테스트 12개 파일, 78개 (실제 Chromium을 띄움)
├── package.json         의존성과 npm 스크립트
└── package-lock.json    설치 버전 고정
```

---

## 실행 방법

```powershell
cd rule-based-analyzer
npm ci                       # package-lock.json 버전 그대로 설치
npx playwright install chromium
node run.js <URL> [출력파일.json] [--cv-screenshot <PNG 경로>]

# 예시
node run.js https://www.mohw.go.kr result.json
npm run scan -- https://www.mohw.go.kr result.json   # 위와 같음
```

출력 파일 이름을 주지 않으면 `result_<날짜>.json`이 된다. 나머지 파일은 출력 파일 이름을 바탕으로 같은 폴더에 생긴다.

| 출력 파일 | 언제 | 용도 |
|---|---|---|
| `result.json` | 항상 | 내부 형식 결과 (camelCase, 디버깅용) |
| `result_api.json` | 항상 | 백엔드 스펙 형식(snake_case). `run_all.py`가 읽어서 통합에 사용. 대상 페이지가 아니면(아래) `metadata.document_health`만 담긴다 |
| `result.html` | 채점한 경우 | 스크립트를 뺀 UTF-8 DOM 스냅샷. 광고·동적 영역에 `data-ua-excluded-region`, 숨김 요소에 `data-ua-hidden`이 붙어 있고 팝업은 닫힌 상태. 문장 난이도 모듈의 입력 (외부 미전송) |
| `result_artifact.json` | 채점한 경우 | 요청·최종 URL, 뷰포트·문서 크기 같은 캡처 메타데이터. `result_final.json`의 `capture_metadata`로 들어감 |
| `result_popup.html` | 레이어 팝업을 찾은 경우 | 닫기 전에 저장한 팝업 내용. 문장 난이도 모듈이 팝업 모드로 따로 분석 |
| `result_cv_anchors.json` | `--cv-screenshot`을 준 경우 | CV 이미지를 찍은 순간의 요소 위치·선택자·내용 서명. `run_all.py`가 CV 위반을 요소에 연결할 때 씀 |
| `<PNG 경로>`, `<PNG 경로 이름>-popup-<번호>.png` | `--cv-screenshot`을 준 경우 | CV용 전체 페이지 이미지(가로 1280px, 세로 페이지 전체)와 팝업 이미지. `run_all.py`는 OS 임시 폴더 경로를 주고 끝나면 지운다 |

종료 코드는 정상 0, 대상 페이지가 아님(`HTTP_ERROR`, `EMPTY`, `BLOCKED`) 2, 그 밖의 실패 1이다.

메시지(`help`, `failure_summary`)는 기본이 한국어다. axe 영어 원문이 필요하면 `AXE_LOCALE=en`(PowerShell: `$env:AXE_LOCALE="en"`)을 주고 실행한다. 점수와 위반 규칙·개수는 같다.

> 실제 서비스에서는 `run_all.py`가 이 파일을 호출하여 결과를 `output/` 폴더에 저장한다.  
> 단독 실행 시에는 현재 폴더(또는 지정한 경로)에 결과 파일이 생성된다.

---

## 전체 흐름 (run.js)

| 순서 | 하는 일 |
|---|---|
| 1 | Chromium을 화면 없이 실행. 언어 `ko-KR`, 창 1280x720, 화면 배율 1 고정 |
| 2 | 페이지 로딩. 최초 응답 HTML을 따로 기록해 두고 `load`까지 최대 60초 대기 |
| 3 | 동적 영역 비교용 두 번째 로딩을 미리 시작. 첫 로딩과 같은 설정이지만 **쿠키·저장소가 빈 새 브라우저 컨텍스트**에서 연다(2026-10-01) |
| 4 | 안정화 대기 (5초 + `document.readyState` 최대 10초) |
| 5 | 봇 대기 화면 감지. 다른 출처의 보안 확인 화면(MBuster, Cloudflare, STCLab, CAPTCHA 등)이나 BotManager 대기 화면이면, 최초 응답 HTML이 쓸 만할 때만 스크립트를 빼고 다시 열어 정적 DOM을 분석한다(`INITIAL_RESPONSE_STATIC`). CAPTCHA 우회나 webdriver 위장은 하지 않는다 |
| 6 | 대상 페이지 판정(`assessTargetPage`). `HTTP_ERROR`(4xx·5xx), `EMPTY`(보이는 글자 20자 미만, 이미지·링크·입력 없음), `BLOCKED`(짧은 문서에 차단 문구)면 점수를 내지 않고 종료 코드 2 |
| 7 | 레이어 팝업. 화면의 20% 이상을 덮는 고정 위치 레이어를 찾아 팝업만 axe와 링크 검사(`link-audit.js`)로 검사하고, 내용과 CV 이미지를 저장한 뒤 닫는다 |
| 8 | 두 번째 로딩의 내용 서명(글자, 이미지 주소, iframe 주소)을 받는다 |
| 9 | 애니메이션 정지 (axe와 스냅샷이 같은 화면 상태를 보게) |
| 10 | axe-core 검사: WCAG 2.0/2.1/2.2 A·AA 태그 + `landmark-one-main`, 메시지는 한국어(`axe-locale.js`). 같은 스캔에 자체 링크 검사 2개(`link-audit.js`)를 붙인다. 캐러셀은 숨은 슬라이드를 하나씩 켜서 둘 다 추가 검사 |
| 11 | 제외 영역 표시: 광고(`AD`)와 두 로딩에서 바뀐 영역(`DYNAMIC`)에 `data-ua-excluded-region` |
| 12 | 숨김 요소 표시: 이 화면 폭에서 안 그려지는 요소에 `data-ua-hidden` |
| 13 | DOM 스냅샷(`result.html`)과 캡처 메타데이터(`result_artifact.json`) 저장, 위반 요소 위치(locator) 계산 |
| 14 | `--cv-screenshot`이 있으면 전체 페이지 이미지와 `result_cv_anchors.json` 저장 |
| 15 | 위반을 점수 대상과 제외 영역(`AD`, `DYNAMIC`)으로 나누고 팝업 위반을 `POPUP`으로 붙인 뒤 `adapter.convert()`(노드별 개선 안내 계산 포함) → `scorer.score()` → `toApiFormat()`(`failure_summary` 끝에 "개선 안내", `fix_hint`) |
| 16 | `result.json`, `result_api.json` 저장, 콘솔에 점수와 위반 많은 항목 출력 |

**Playwright는 run.js 한 곳에서만 실행**  
모듈마다 브라우저를 따로 띄우면 리소스가 낭비되고 렌더링 시점이 달라 데이터가 어긋난다. run.js에서 axe와 locator가 본 같은 일시정지 DOM을 정적 HTML로 저장하고, 다른 모듈은 그 파일을 읽는다. CV 이미지는 `--cv-screenshot`을 줄 때만 만든다.

---

## 파일별 역할

### excluded-regions.js — 점수에서 빼는 영역

운영자가 통제할 수 없거나 방문마다 바뀌는 콘텐츠는 사이트 자체의 점수에 섞지 않는다. 검사 결과는 버리지 않고 `excluded_violations`에 사유별로 따로 남긴다.

| 사유 | 무엇 | 판정 |
|---|---|---|
| `AD` | 광고 서버가 끼워 넣은 광고, 스스로 "[광고]"라고 밝힌 광고 | 광고 표식(`ins.adsbygoogle`, `data-ad-slot`, `aria-label="광고"` 등)이나 광고 서버 주소의 iframe, 대체 텍스트·`aria-label`이 "[광고]"로 시작하는 요소 |
| `DYNAMIC` | 방문마다 바뀌는 뉴스·추천 피드 | 쿠키 없는 새 컨텍스트에서 다시 불러와 비교했을 때 글자·이미지 주소·iframe 주소가 달라졌거나 한쪽에만 있는 요소. 두 번째 로딩이 분석 페이지 요소의 절반도 공유하지 않으면(오류·차단 화면) 비교하지 않는다 |
| `POPUP` | 접속 직후 본문을 덮는 레이어 팝업 | `popup-layers.js`가 찾음. 세 모듈 모두 검사하되 점수에서만 뺀다 |

두 번째 로딩을 새 컨텍스트에서 여는 이유(2026-10-01): 같은 컨텍스트를 쓰면 첫 방문 때 사이트가 심은 쿠키를 들고 들어가 재방문자로 보인다. 그러면 재방문자용 문구나 쿠키를 보고 바꾼 이미지처럼 원래 고정된 요소가 `DYNAMIC`으로 잘못 빠지고, 쿠키가 언제 심어졌느냐에 따라 실행마다 결과도 달라진다.

기관이 직접 만든 배너·슬라이드는 빼지 않는다. 캐러셀은 `carousel-audit.js`가 모든 슬라이드를 검사한다.

### popup-layers.js — 레이어 팝업

화면의 20% 이상을 덮고 fixed·absolute 위치이며 z-index가 100 이상인 요소를 팝업으로 보고 `data-ua-popup`을 붙인다. 팝업이 열린 상태에서 팝업만 axe로 검사하고, 내용을 `result_popup.html`로, 통합 실행이면 팝업 CV 이미지를 저장한다. 그 뒤 "닫기", "오늘 하루 보지 않기" 같은 버튼을 누르고, 결과와 상관없이 `display:none`으로 숨기고 Esc도 누른다. 이후 본문 검사와 스냅샷은 팝업이 닫힌 화면을 본다.

### carousel-audit.js — 숨은 슬라이드 검사

axe-core 한 번의 검사는 `display:none`, `hidden`, `inert` 등으로 비활성화된 인접
슬라이드를 검사하지 않는다. 이 모듈은 현재 보이는 기준 상태를 먼저 검사한 뒤,
지원되는 캐러셀의 나머지 논리 슬라이드를 하나씩 독립적으로 활성화해 axe를 다시
실행한다. 정적 영역에서 반복된 결과는 규칙 ID와 노드 식별자로 중복 제거한다.

- 지원 구조: Swiper, Slick, Splide, 명시적 generic carousel/slider 구조
- clone/duplicate 슬라이드는 제외한다.
- 클릭, 프레임워크 API, 자동 재생 타이머를 호출하지 않고 DOM 표시 상태만 임시로 바꾼다.
- 검사 중 새 네트워크 요청은 차단한다.
- 각 상태 뒤 원래 class, inline style, `hidden`/`inert`/ARIA/`tabindex`, scroll을 복원하고,
  전체 완료 시 focus를 한 번 복원한다.
- 조합 전수 검사는 하지 않는다. 다른 캐러셀은 기준 상태에 둔 채 각 캐러셀의
  비기준 슬라이드만 독립 검사한다.
- 기본 상한: 캐러셀 12개, 캐러셀당 논리 슬라이드 20개, 추가 상태 60개.

직렬화되는 실제 논리 슬라이드에는 다음 계약을 남긴다. 값은 각각 캡처 내 캐러셀
ID(1-based), 논리 슬라이드 index(0-based), clone을 제외한 논리 슬라이드 수다.

```html
<section data-ua-audit-carousel-id="1"
         data-ua-audit-slide-index="2"
         data-ua-audit-slide-count="5">...</section>
```

숨은 이슈의 `locator.pathSteps`는 해당 후손 노드를 가리킨다. 분석기 내부 JSON의
`locator.carouselContext`는 같은 캐러셀 ID와 슬라이드 위치를 보존한다.
`result.html`의 annotation은 로컬 분석·회귀 진단용이며 백엔드에 업로드하지 않는다.

### link-audit.js — axe에 없는 링크 검사 (2026-10-03)

axe-core에는 새 창 고지와 "더보기"류 링크 텍스트를 보는 규칙이 없다(`link-name`은 이름이 **아예 없는** 링크만 잡는다). 그래서 두 규칙을 직접 만들어 axe 결과와 같은 형태(`id`, `impact`, `tags`, `help`, `nodes[{target, html, failureSummary}]`)로 붙인다. `run.js`의 `scanPage`가 axe 결과에 붙이므로 캐러셀 슬라이드별 검사·중복 제거, 광고·동적 영역 제외, 팝업 분리(`POPUP`), KWCAG 매핑, 감점을 axe 규칙과 똑같이 탄다.

| 규칙 ID | KWCAG (`mapping.js` `axeRules`) | 위반 조건 | 통과 |
|---|---|---|---|
| `uniaccess-new-window-notice` | 7.2.1 사용자 요구에 따른 실행 (major·medium) | 새 창으로 열림: `target="_blank"`, 페이지에 같은 이름의 frame이 없는 이름 있는 target(`target="popup"` 등), `onclick`이나 `javascript:` href의 `window.open(` | 링크 글자, 화면에 숨긴 글, `title`, `aria-label`, `aria-describedby`, 이미지 alt 중 하나에 "새 창/새창", "새 탭", "새로운 창", "창 열림/창열림", "팝업", "new window/tab"이 있음 |
| `uniaccess-ambiguous-link` | 6.4.3 적절한 링크 텍스트 (major·medium) | 접근 가능한 이름(aria-labelledby → aria-label → 글자·이미지 alt·숨긴 글, 없으면 title)에서 공백·기호를 뺀 값이 "더보기", "자세히(보기)", "상세보기", "바로가기", "보기", "이동", "클릭", "여기", "이곳", "링크", "more", "read more", "view more", "click here", "go" 등뿐이거나 기호뿐("+", ">") | `aria-label`·숨긴 글로 대상을 밝힘, 또는 `title`·`aria-describedby`가 대상을 밝힘("공지사항 더보기"). "새창"만 적힌 title은 대상을 밝힌 게 아니라 통과가 아님 |

- **이중 감점 방지:** 이름이 아예 없는 링크는 axe `link-name`(6.4.3)이 잡으므로 두 규칙 모두 건너뛴다.
- **검사 대상:** 분석 화면 폭에서 그려진 `a[href]`, `area[href]`(이미지 맵은 이미지가 그려졌을 때). `display:none`·`visibility:hidden`·`aria-hidden="true"` 안의 링크는 axe처럼 건너뛴다. 메인 문서만 보고 같은 출처 iframe·shadow DOM 안 링크는 보지 않는다(axe는 본다).
- **엄격도:** 모호한 링크는 링크만 보고 판정한다. WCAG 2.4.4(A)는 링크가 든 문단·목록 항목 같은 주변 문맥으로 목적을 알 수 있으면 통과로 보므로 이보다 엄격하고 2.4.9(AAA)에 가깝다. 국내 심사는 보통 링크 글자로 판단해서 이렇게 정했다. 태그에 `wcag244`와 `wcag249`를 같이 적었다.
- **새 창 고지의 WCAG 근거:** WCAG에서는 3.2.5(AAA, 요청에 의한 변화)·기법 G201 수준이지만 KWCAG 2.2는 7.2.1에서 필수로 본다. 태그는 `kwcag721`, `wcag325`.
- **수정 예시:** 노드의 `failureSummary`(API `failure_summary`)에 한국어 설명과 예시를 넣는다. 모호한 링크는 같은 구역(조상 6단계 안)에서 링크 앞에 있는 가장 가까운 제목을 찾아 `"공지사항 더보기"`처럼 제안한다(`contextHeading`). 백엔드는 `help + 줄바꿈 + failure_summary`를 이슈 설명으로 저장하고, 대시보드는 모르는 규칙 ID의 설명을 그대로 보여 준다.
- **선택자:** 고유 id가 있으면 `#id`, 없으면 가장 가까운 고유 id 조상부터 `태그:nth-of-type` 경로. `partitionAxeResultsByRegion`이 이 선택자로 요소를 찾아 제외 영역을 판정한다.
- **감점 크기:** axe 규칙과 같이 요소 1개당 major(2) × medium(×1.0) = 2점이고 상한이 없다. 저장된 스냅샷(CSS 없이 열어 화면 숨김을 반영 못 함, 상한치)으로 센 건수는 새 창 고지 누락이 네이버 83·봉화군청 30·위례별초 5·국민건강보험공단 1, 모호한 링크가 국민건강보험공단 4·네이버 1이고 나머지 사이트는 0이다. 봉화군청은 규칙 점수가 최대 60점 내려갈 수 있다. 실제 값은 로컬 재실행으로 확인해야 한다.

### axe-locale.js, fix-hints.js — 한국어 메시지와 노드별 개선 안내 (2026-10-13)

규칙 기반은 세 모듈 중 유일하게 "어떻게 고치는지"를 주지 않았다. axe의 영어 `help`·`failure_summary`가 그대로 백엔드 이슈 메시지가 됐고, 대시보드는 10개 규칙에만 한국어 설명을 따로 붙였다.

**axe-locale.js.** axe-core 4.11.4 패키지에 들어 있는 한국어 번역(`locales/ko.json`)을 쓴다. `@axe-core/playwright`의 `AxeBuilder`는 `configure()`가 없지만 생성자에서 `axeSource`(브라우저에 주입할 스크립트)를 받으므로, axe 소스 뒤에 `axe.configure({ locale })`를 붙인 문자열(`koreanAxeSource()`)을 넘긴다. 본문·팝업·캐러셀 검사와 iframe이 모두 같은 설정으로 돈다.

- 실행 범위 70개 규칙 중 6개(`target-size`, `summary-name`, `aria-prohibited-attr`, `aria-conditional-attr`, `aria-deprecated-role`, `aria-braille-equivalent`)와 체크 83개 중 10개는 공식 번역이 없어 `locales/ko-supplement.json`이 채운다. 공식 번역에 있는 키는 덮어쓰지 않는다.
- axe는 모르는 규칙·체크 ID가 locale에 있으면 설정 전체를 거부하므로, 설치된 axe가 아는 ID의 보충분만 넣는다.
- axe-core를 못 찾거나 번역 파일을 못 읽으면 경고를 한 번 찍고 영어로 검사한다(검사는 멈추지 않음). `AXE_LOCALE=en`(또는 `off`)이면 일부러 영어.
- axe-core는 `package.json`에 따로 넣지 않았다. `@axe-core/playwright`가 의존하고 npm이 최상위에 올려 두므로 그대로 쓰고, 안 보이면 `@axe-core/playwright` 옆에서 찾는다(`package-lock.json`과 어긋나 `npm ci`가 깨지지 않게).

**fix-hints.js.** axe가 이미 잰 값(색, 크기, 간격)만으로 "얼마나 고치면 되는지"를 계산해 노드마다 붙인다. 추측하지 않고, 필요한 값이 없으면 `null`이다.

| 규칙 | 계산 | `failure_summary` 끝에 붙는 문장 예 |
|---|---|---|
| `color-contrast` | CV 모듈 `contrast_analyzer.suggest_fix`와 같은 방식. 상대 휘도로 방향을 정하고(글자가 어두우면 글자는 더 어둡게·배경은 더 밝게, 글자가 밝으면 반대) RGB 세 채널을 같은 만큼씩 움직여 기준(4.5:1, 큰 글자 3:1)에 처음 닿는 색. 끝까지 가도 모자라면 `meets_target: false`. 표시 대비값은 소수 둘째 자리에서 버림 | `• 글자색을 바꾼다면: #777777 → #767676 (더 어둡게, 명도 대비 4.54:1 / 기준 4.5:1)` |
| `target-size` | 현재 크기·이웃과의 간격과 axe가 준 기준(최소 24px)까지 모자란 만큼 | `• 크기를 키운다면: 현재 10px × 10px → 최소 24px × 24px (가로 14px, 세로 14px 더 필요)` |

- 결과에는 `result_api.json` 노드의 `fix_hint`(구조화된 값: `kind`, `text_color`·`background_color` 또는 `size`·`spacing`)와, `failure_summary` 끝의 "개선 안내" 단락으로 두 번 실린다. 백엔드는 `failure_summary`를 그대로 저장하므로 수정할 것이 없다.
- 같은 두 색이면 CV 모듈과 같은 추천 색이 나오도록 고정 벡터로 테스트한다. 그림자가 걸린 변형처럼 두 색만으로 설명되지 않으면 만들지 않는다. 판단 보류(`incomplete`) 노드에는 만들지 않는다.
- 대시보드 `rule-issue-description.ts`는 `color-contrast` 등 10개 규칙에서 요소별 메시지 대신 일반 안내만 보여 준다. 추천 색이 화면에 보이려면 대시보드 수정이 필요하다(팀 저장소 쪽 할 일).
- 대체 텍스트·레이블처럼 내용을 지어야 하는 수정안은 없다(후속: LLM 코드 수정 초안).

### hidden-elements.js, cv-anchors.js, artifact.js

- `hidden-elements.js`: axe 검사 뒤 실제 계산된 스타일로 `display:none`, `hidden` 속성, `visibility:hidden`(보이는 자식이 없을 때), `content-visibility:hidden` 요소에 `data-ua-hidden`을 붙인다. PC 화면에서 숨겨진 모바일 전용 목록 같은 것이다. 스크린리더 전용 텍스트, 투명한 요소, 캐러셀 슬라이드는 표시하지 않는다. 문장 난이도 모듈은 이 요소를 분석하지 않는다.
- `cv-anchors.js`: CV 이미지를 찍는 순간 보이는 요소마다 문서 좌표, 선택자, 내용 서명을 `result_cv_anchors.json`에 기록한다.
- `artifact.js`: 위반 요소의 위치 정보(`locator`: iframe·Shadow DOM까지 따라가는 경로 `pathSteps`와 문서 CSS 좌표), 스크립트를 뺀 DOM 스냅샷, 캡처 메타데이터를 만든다. 애니메이션과 페이지 시간을 멈추는 함수도 여기 있다.

### adapter.js — WCAG → KWCAG 변환기

axe-core는 국제 표준인 WCAG 기준으로 결과를 출력하지만, 본 프로젝트는 한국형 지침인 KWCAG 2.2 기준으로 평가한다. adapter.js가 이 변환을 담당한다.

**2단계 매핑 방식 (Two-stage Resolution):**

| 단계 | 방법 | 예시 |
|---|---|---|
| 1단계 (직접 매핑) | axe-core 규칙 ID → KWCAG 번호 직접 조회 | `image-alt` → `5.1.1` |
| 2단계 (fallback) | WCAG 태그 번호 추출 → KWCAG 번호 조회 | `wcag244` → WCAG `2.4.4` → `6.4.3` |
| 실패 (unmapped) | 두 단계 모두 실패 시 unmapped 목록에 보존 | 정보 유실 방지 |

1단계가 더 정확하고, 2단계는 1단계 실패 시 안전망 역할을 한다.  
매핑 실패 항목(unmapped)도 버리지 않고 별도 보존하여 WCAG 참조 정보를 유지한다.

WCAG 4.1.2는 KWCAG 8.1.1과 8.2.1 두 항목에 대응하므로, 폴백으로 들어오면 두 항목에서 동시에 감점됐다. 그래서 4.1.2 규칙 16개를 `mapping.js`의 `axeRules`에 하나씩 배정하고, 새 4.1.2 규칙이 폴백으로 들어와도 8.2.1 하나에만 들어가도록 `FALLBACK_PRIMARY = { '4.1.2': '8.2.1' }`을 두었다(2026-09-28).

### mapping.js — 매핑 테이블

KWCAG 33개 검사항목 정의와 axe-core 규칙 ID 매핑 데이터를 담고 있다. `link-audit.js`의 자체 규칙 ID(`uniaccess-*`)도 같은 `axeRules` 목록에 들어 있다(6.4.3, 7.2.1). 6.4.3에 함께 적힌 `identical-links-same-purpose`는 태그가 `wcag2aaa`라 현재 axe 실행 범위(A·AA)에서는 돌지 않는다(axe-core 4.11.4에서 확인). 실제로 6.4.3을 채우는 규칙은 `link-name`과 `uniaccess-ambiguous-link`다. `node mapping.js`로 직접 실행하면 표를 JSON으로 출력하며, 루트의 `standard_mapping.py`가 이것을 읽어 문장 난이도·CV 결과에도 같은 KWCAG 번호를 붙인다.

**각 항목에 포함된 정보:**

| 필드 | 의미 | 사용처 |
|---|---|---|
| `name` | KWCAG 항목명 | 출력 및 대시보드 표시 |
| `wcag` | 대응 WCAG 번호 배열 | 2단계 폴백 매핑 |
| `mappingType` | 1:1, 1:N, N:1(부분), 고유 | 참고 |
| `module` | 담당 모듈 (규칙기반 / 규칙기반+CV / CV / AI분석 / 수동) | 모듈 분업 구분 |
| `weight` | 항목 중요도 (high / medium / low) | scorer.js 감점 배수 |
| `severity` | 위반 시 영향도 (critical / major / minor) | scorer.js 기본 감점값, 백엔드 이슈 심각도 |
| `axeRules` | 대응 axe-core 규칙 ID 목록 | 1단계 직접 매핑 |

**weight와 severity의 구분:**

- `severity`: 이 항목을 위반했을 때 장애 사용자에게 미치는 영향도 → **감점 기준값** (critical=3점, major=2점, minor=1점)
- `weight`: 이 항목이 전체 점수에서 차지하는 상대적 중요도 → **감점 배수** (high=×1.5, medium=×1.0, low=×0.5)

두 값은 대체로 같은 방향이다. critical 항목 7개는 모두 high이고, 둘이 갈리는 항목은 5.4.3 명도 대비(major·high), 8.1.1 마크업 오류 방지(minor·high), 그리고 minor·medium인 5.4.4, 6.4.2, 7.1.1 정도다. WCAG 레벨(A/AA)과 연결된 값은 아니다. 점수에서는 곱으로만 쓰이므로 아래 scorer.js의 "건당 감점" 한 칸으로 읽는 것이 정확하다.

**7.3.4의 WCAG 번호 (2026-10-13).** 반복 입력 정보가 WCAG 3.3.9(접근 가능한 인증, AAA)로 잘못 적혀 있어 3.3.7(Redundant Entry)로 고쳤다. 수동 항목이라 점수·매핑 결과는 같다. `axeRules`가 빈 배열인 항목(담당이 AI분석/CV/수동)은 axe-core로 자동 검사할 수 없는 항목으로, 해당 모듈이 별도로 담당한다.

### scorer.js — 점수 산출

adapter.js의 변환 결과를 받아 100점 감점제 점수를 계산한다. 점수(0~100)만 내고 등급은 매기지 않는다.

**감점 공식:**
```
항목별 감점 = severity 기본 감점 × weight 배수 × 위반 요소(노드) 수
최종 점수   = max(0, 100 − 반올림(모든 항목 감점의 합 + 미매핑 감점))
```

**severity 기본 감점:**

| 등급 | 점수 | 기준 |
|---|---|---|
| critical | 3점/건 | 장애인 접근 자체 불가 (예: 대체 텍스트 누락) |
| major | 2점/건 | 심각한 사용 불편 (예: 부적절한 링크 텍스트) |
| minor | 1점/건 | 경미한 불편 (예: lang 속성 누락) |

**weight 배수:**

| 등급 | 배수 | 기준 |
|---|---|---|
| high | ×1.5 | 핵심 항목. 위반하면 접근 자체가 막힘 |
| medium | ×1.0 | 중요 항목 |
| low | ×0.5 | 부가 항목. 편의성 수준 |

**계산 예시:**
```
5.1.1 (severity=critical, weight=high): alt 없는 <img> 5개 발견
→ 3 × 1.5 × 5 = 22.5점 감점

7.1.1 (severity=minor, weight=medium): lang 속성 누락 1건
→ 1 × 1.0 × 1 = 1점 감점
```

KWCAG에 매핑되지 않은 unmapped 위반은 minor × medium (건당 1점)으로 감점한다.

**건당 감점표 (2026-10-13 정리, 계산은 그대로).** 33개 항목의 "요소 1개당 감점"은 여섯 값뿐이다. `*`는 axe 규칙이 직접 연결된 항목, 표시 없는 항목은 수동 검사 대상이다(5.4.4와 6.1.1은 WCAG 번호 폴백으로 axe 위반이 들어올 수 있음. 실행 범위 70개 규칙 중 직접 매핑 53, 폴백 12, 매핑 없음 5).

| 건당 | severity × weight | 항목 수 | KWCAG 항목 |
|---|---|---|---|
| 4.5 | critical × high | 7 | 5.1.1* 5.2.1* 5.4.2* 7.3.2* / 6.1.1 6.1.2 6.3.1 |
| 3.0 | major × high | 1 | 5.4.3* |
| 2.0 | major × medium | 16 | 5.3.1* 5.3.2* 5.4.1* 6.1.3* 6.2.1* 6.2.2* 6.4.1* 6.4.3* 6.5.3* 7.2.1* 7.3.1* 8.2.1* / 5.3.3 6.5.1 6.5.2 7.3.3 |
| 1.5 | minor × high | 1 | 8.1.1* |
| 1.0 | minor × medium | 3 | 6.4.2* 7.1.1* / 5.4.4 |
| 0.5 | minor × low | 5 | 6.1.4 6.4.4 6.5.4 7.2.2 7.3.4 (모두 수동, 실제로 쓰인 적 없음) |

값을 바꾸려면 `mapping.js`의 severity·weight만 고치면 된다. 이 값들은 팀이 정한 판단값(매핑 테이블 v2)이고 실측 근거는 없다. 화면에는 severity만 보이는데, 미매핑 위반은 axe impact(4단계)를 쓰므로 한 화면에 기준이 다른 심각도가 섞이고, 항목 등급과 axe impact가 어긋나는 규칙도 있다(예: `no-autoplay-audio`는 axe impact moderate인데 5.4.2라 4.5점).

감점은 규칙 수가 아니라 **요소 수**에 비례하므로, 위반 요소가 많은 대형 포털은 0점 바닥에 붙기 쉽다. 이 점수는 "개선 필요성의 상대적 강도"를 전하는 신호로 본다. 바닥에 붙으면 일부를 고쳐도 점수가 안 오른다(서울시: 감점 162점이라 `target-size` 8건을 고쳐도 0점). "건당 감점 × log2(1 + 요소 수)"처럼 요소가 늘수록 덜 깎는 식이면 같은 자료가 67점이 되고 그 수정이 +6.3점으로 보이지만, 점수 정의가 바뀌는 일이라 후속 과제로 남겼다.

**등급을 매기지 않는 이유 (2026-09-27).** 예전에는 이 점수에 A~F 5단계 모듈 등급을 붙였는데, `run_all.py`의 최종 등급(A+~F 7단계)과 구간과 글자가 달라 어느 쪽이 등급인지 헷갈렸다. 그래서 등급은 `result_final.json`의 `grade` 하나만 쓴다.

---

## 테스트

`npm test`(`node --test test/*.test.js`)로 12개 파일, 78개 테스트를 돌린다(2026-10-13 기준). 대부분 로컬 테스트 서버에 가짜 페이지를 띄우고 실제 Chromium으로 `run.js`를 돌려 결과를 확인한다.

| 파일 | 확인하는 것 |
|---|---|
| `artifact.test.js` | locator 경로, DOM 스냅샷, 캡처 메타데이터 |
| `carousel-audit.test.js` | 캐러셀 숨은 슬라이드 검사와 원상 복구 |
| `challenge-detection.test.js` | 봇 대기 화면 신호(MBuster, Cloudflare 포함), 태그만 심긴 정상 페이지 오탐 없음 |
| `document-content.test.js` | `EMPTY`, `HTTP_ERROR`, `BLOCKED` 판정 |
| `excluded-regions.test.js` | 광고·동적 영역 분리, "[광고]" 대체 텍스트 광고, 쿠키를 보고 재방문자에게 다른 문구를 주는 고정 요소가 `DYNAMIC`으로 빠지지 않음 |
| `hidden-elements.test.js` | 숨김 요소 표시 |
| `link-audit.test.js` | 새 창 고지 누락·모호한 링크 판정(title·숨긴 글·alt·aria-label로 통과, frame target·숨김·이름 없는 링크 제외), 가까운 제목으로 만든 수정 예시, 선택자가 그 링크를 가리키는지, 범위 제한(팝업), 6.4.3·7.2.1 매핑과 2점 감점, 팝업 안 링크가 `POPUP`으로 빠지는지 |
| `cv-anchors.test.js` | CV 위치 기록 |
| `popup-layers.test.js` | 팝업 위반이 `POPUP`으로 분리되고 본문 점수는 그대로인지 |
| `axe-locale.test.js` | 공식 번역 우선으로 합치기, 설치된 axe가 모르는 규칙 빼기, 실제 페이지의 한국어 `help`·`failureSummary`, `AXE_LOCALE=en`, 번역 파일을 못 읽어도 검사 계속 (2026-10-13) |
| `fix-hints.test.js` | 추천 색이 CV `suggest_fix`와 같은지(고정 벡터), 방향, 끝까지 가도 모자란 경우, 표시값 버림, 조작 대상 크기·간격, 값이 없으면 `null` (2026-10-13) |
| `fix-hints-pipeline.test.js` | `run()` 전체로 `result_api.json`의 한국어 `failure_summary`와 "개선 안내", 영어로 돌려도 점수·위반 규칙·개수가 같음 (2026-10-13) |

가끔 파일 단위로 "Unable to deserialize cloned data" 오류가 난다. Node 테스트 러너가 결과를 읽다가 나는 오류로 코드와 관계없으며, 다시 돌리면 통과한다.

---

## 의존성

```json
"dependencies": {
  "@axe-core/playwright": "^4.9.0",
  "playwright": "^1.42.0"
}
```

실제 설치 버전은 `package-lock.json`에 고정되어 있다(@axe-core/playwright 4.11.3, axe-core 4.11.4, playwright 1.61.0). `npm install` 대신 `npm ci`로 설치하면 같은 버전이 깔린다. 한국어 번역은 이 axe-core에 들어 있는 `locales/ko.json`을 쓴다(axe-core를 따로 추가하지 않음).

---

## 자동화 검사 범위

axe-core는 KWCAG 33개 항목 중 규칙 기반으로 자동 검사 가능한 항목만 커버한다.  
나머지 항목은 아래 모듈이 담당하거나 수동 검토가 필요하다.

| 모듈 | 담당 항목 예시 |
|---|---|
| 규칙기반 (이 모듈) | 대체 텍스트, 명도 대비, heading 구조, 레이블, 링크 텍스트(빈 링크·"더보기"류, 6.4.3), 새 창 고지(7.2.1) 등 |
| 문장 난이도 분석 (text-level-analyzer) | 명확한 지시사항(5.3.3, 감각 의존 지시), 링크 텍스트(6.4.3, 글자 수·"여기 클릭"류 문장), 레이블(7.3.2), 제목(6.4.2), WCAG 3.1.5 읽기 수준 |
| CV 분석 (cv-analyzer) | 화면에 보이는 글자(이미지 속 글자 포함)의 명암비(5.4.3). 5.4.4 콘텐츠 간의 구분은 담당으로 적혀 있지만 아직 검사하지 않음 |
| 수동 검토 | 키보드 사용 보장, 깜빡임 제한, 포인터 입력 등 |

WAVE나 Lighthouse 등 기존 도구도 자동화 가능 범위는 전체의 30~40% 수준이며, 나머지는 수동 검토가 필요하다는 점은 업계 표준과 동일하다.
