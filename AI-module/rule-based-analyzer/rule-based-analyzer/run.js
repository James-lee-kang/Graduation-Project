/**
 * ============================================================================
 *  run.js — KWCAG 접근성 검사 실행기 (규칙 기반 분석 모듈의 진입점)
 * ============================================================================
 *
 * [파일 역할]
 *   사용자가 입력한 URL 하나에 대해 전체 규칙 기반 접근성 검사를 수행하는
 *   최상위 오케스트레이터. 브라우저를 띄워 페이지를 렌더링하고, axe-core로
 *   접근성 검사를 돌린 뒤, KWCAG(한국형 웹 콘텐츠 접근성 지침) 기준으로 변환·
 *   점수화하여 JSON 파일로 저장. 동시에 AI 분석 모듈이 사용할 수 있도록
 *   렌더링된 HTML도 함께 저장(문장 난이도 분석에 사용)
 *
 * [전체 파이프라인에서의 위치]
 *   [이 파일] ─ 규칙 기반 모듈 (axe-core + KWCAG 매핑 + 점수화)
 *             ├─ 출력 1: result.json          (디버깅용, 내부 형식)
 *             ├─ 출력 2: result_api.json      (백엔드 전송용, API 스펙 형식)
 *             └─ 출력 3: result.html          (AI 모듈 입력용, 렌더링된 DOM)
 *                          │
 *                          ▼
 *                   text_extractor.py → difficulty_engine.py → suggestion_generator.py
 *                   (AI 분석 모듈 — 별도 파이프라인)
 *
 * [사용법]
 *   node run.js <URL> [출력파일.json]
 *   예: node run.js https://www.gov.kr result.json
 *
 * [처리 흐름]
 *   URL 입력
 *     → Playwright로 헤드리스 브라우저 실행 및 페이지 로딩
 *     → 렌더링된 HTML 저장 (AI 모듈용)
 *     → axe-core 실행 (WCAG 2.0/2.1/2.2 규칙 기반 검사)
 *     → adapter.convert() : axe 결과를 KWCAG 33개 항목 기준으로 재분류
 *     → scorer.score()    : 100점 감점 방식으로 점수 산출
 *     → toApiFormat()     : 백엔드 API 스펙(snake_case)으로 변환
 *     → JSON 저장 + (선택) 백엔드 전송
 *
 * [설계상 주의점]
 *   - Playwright 인스턴스를 run.js 한 곳에서만 띄움
 *     → 규칙 기반 모듈과 AI 모듈이 각자 브라우저를 띄우면 리소스 낭비가 크고,
 *        동적 렌더링 시점이 달라 데이터 일관성도 깨짐. 따라서 이 파일에서
 *        "렌더링된 최종 DOM"을 HTML 파일로 떨어뜨려 두고, AI 모듈은 그 파일을
 *        소비하는 방식으로 역할을 분리함.
 *   - axe-core는 "외부 라이브러리"가 아니라 "로컬 라이브러리"로 취급
 *     → 네트워크 호출이 아니라 Node 모듈로 import해서 쓰므로, 동일 입력에
 *        동일 출력이 보장되고 실험 재현성이 있음.
 * ============================================================================
 */

const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const { convert } = require('./adapter');  // axe 결과 → KWCAG 33개 항목 기준으로 재분류
const { score } = require('./scorer');     // KWCAG 결과 → 100점 감점 방식 점수화
const fs = require('fs');
const path = require('path');

// ─────────────────────────────────────────────────────────────────────────────
//  백엔드 서버 설정
// ─────────────────────────────────────────────────────────────────────────────
//  현재는 벡엔드의 Spring Boot 서버가 아직 배포되지 않은 상태이므로
//  로컬 주소를 placeholder로 둠. 서버 배포 후 실제 주소로 교체 예정.
//  참고: 이 주소로 전송이 실패해도 파이프라인 전체는 중단되지 않고 로컬 JSON
//  저장까지는 정상 수행되도록 sendToBackend()가 예외를 삼킴(아래 참조).
// ─────────────────────────────────────────────────────────────────────────────
const API_BASE_URL = 'http://localhost:8080/api/v1';

/**
 * ─────────────────────────────────────────────────────────────────────────
 *  toApiFormat(kwcagResult, scoreResult)
 * ─────────────────────────────────────────────────────────────────────────
 *  adapter.convert() 결과와 scorer.score() 결과를 받아,
 *  백엔드 API 스펙(snake_case, v1)에 맞는 단일 JSON으로 병합한다.
 *
 *  [왜 이런 변환이 필요한가 — 설계 의도]
 *    내부 모듈(adapter, scorer)은 JavaScript 관례에 따라 camelCase를 씀.
 *    하지만 백엔드(Spring Boot/Java)와 주고받을 API 스펙은 snake_case로
 *    통일되어 있음. "모듈 내부 표현"과 "외부 공개 인터페이스"를 분리함으로써
 *    내부 리팩터링이 API 호환성을 깨지 않게 함과 동시에 toApiFormat은 이
 *    파일에서만 호출되는 얇은 변환 계층이라 유지보수 비용이 낮음.
 *
 *  [입력 스키마]
 *    kwcagResult (from adapter.js):
 *      - kwcag: { '5.1.1': { name, violations[], passes[], violationCount, ... }, ... }
 *          → KWCAG 33개 항목(예: 5.1.1 = 대체 텍스트 제공) 기준으로 재분류된 결과
 *      - unmapped: { violations[], passes[] }
 *          → KWCAG에 매핑 불가한 axe 규칙(예: WCAG 2.2 신규 항목 등). 버리지 않고
 *            "추가 참고" 섹션으로 보존 — 발표에서 "우리는 axe가 찾은 모든 위반을
 *            감추지 않는다"는 투명성 근거가 됨.
 *      - summary: { totalViolations, totalPasses, kwcagViolations, ... }
 *      - meta: { url, timestamp, engine, engineVersion, adapterVersion }
 *
 *    scoreResult (from scorer.js):
 *      - score, maxScore, totalDeduction  (모듈 등급은 2026-09-27 제거)
 *      - severityBreakdown: { critical, major, minor } — 심각도별 감점 집계
 *      - items: KWCAG 항목별 점수 상세 (weight, weightMultiplier 포함)
 *
 *  [출력 스키마]
 *    이 함수의 반환값이 그대로 result_api.json 및 백엔드 POST body가 됨.
 *    최상위 키(analyzer_type, summary, violations, passes, unmapped_violations,
 *    score, metadata) 구조는 v1 API 스펙 문서에 정의되어 있음.
 * ─────────────────────────────────────────────────────────────────────────
 */
function toApiFormat(kwcagResult, scoreResult) {
  // ── 1) violations: KWCAG 항목별로 그룹화 ──
  //    위반이 0건인 항목은 제외(noise 감소). 각 위반은 axe 규칙 단위로 묶이고,
  //    그 안에 실제 위반 DOM 노드들이 nodes[]로 들어감.
  const violations = [];
  for (const [kwcagId, item] of Object.entries(kwcagResult.kwcag)) {
    if (item.violationCount === 0) continue;

    violations.push({
      kwcag_id: kwcagId,
      kwcag_name: item.name,
      // severity는 scorer에서 계산한 값을 재사용(항목별 고정 심각도).
      // scorer가 분류 실패한 경우 'minor'로 fallback — 점수 계산은 되지만
      // 가장 가벼운 등급으로 보수적 처리.
      severity: scoreResult.items[kwcagId]?.severity || 'minor',
      violation_count: item.violationCount,
      rules: item.violations.map(v => ({
        axe_rule_id: v.axeRuleId,
        description: v.description,
        help: v.help,
        impact: v.impact,
        nodes: v.nodes.map(n => ({
          selector: n.selector,        // CSS 셀렉터: 프론트엔드가 해당 요소 하이라이트할 때 사용
          html: n.html,                // 위반 요소의 outerHTML: 수정 가이드 생성 시 참조
          failure_summary: n.failureSummary,  // axe가 제공하는 "왜 위반인지" 자연어 설명
        })),
      })),
    });
  }

  // ── 2) passes: KWCAG 항목별로 그룹화 ──
  //    통과 항목도 저장하는 이유: 대시보드에서 "이 사이트는 X개 기준을 충족했다"
  //    라는 긍정 지표를 보여주기 위함. 접근성 개선의 동기 부여가 목적.
  //    (계획서 §4 "정량화된 점수 … 접근성 개선의 필요성·동기 제공").
  const passes = [];
  for (const [kwcagId, item] of Object.entries(kwcagResult.kwcag)) {
    if (item.passCount === 0) continue;

    passes.push({
      kwcag_id: kwcagId,
      kwcag_name: item.name,
      pass_count: item.passCount,
      rules: item.passes.map(p => ({
        axe_rule_id: p.axeRuleId,
        description: p.description,
        node_count: p.nodeCount,
      })),
    });
  }

  // ── 3) unmapped_violations: KWCAG 33개 항목에 매핑되지 않은 axe 위반 ──
  //    예: axe-core는 WCAG 2.2에 새로 추가된 항목도 검사하는데, KWCAG는
  //    2.1 기반 항목이 중심이라 매핑이 없는 경우가 생김. 이를 버리지 않고
  //    "참고 정보"로 노출해서 향후 KWCAG 확장 시 바로 편입할 수 있도록 함.
  const unmappedViolations = kwcagResult.unmapped.violations.map(v => ({
    axe_rule_id: v.axeRuleId,
    description: v.description,
    impact: v.impact,
    wcag_reference: v.wcagReference || 'WCAG 기준 미확인',
    node_count: (v.nodes || []).length,
  }));

  // ── 4) score: scorer 결과의 camelCase를 snake_case로 변환 ──
  //    단순 키 이름 변환이지만, 계층 구조(severityBreakdown, items 등)가 있어
  //    손으로 한 번 펼쳐서 매핑함. Object.entries + reduce로 일반화하는 것도
  //    가능하지만, 명시적 매핑이 스펙 변경 시 더 안전하고 diff가 읽기 쉬움.
  const scoreData = {
    score: scoreResult.score,
    max_score: scoreResult.maxScore,
    total_deduction: scoreResult.totalDeduction,
    severity_breakdown: {
      critical: {
        count: scoreResult.severityBreakdown.critical.count,
        deduction_per_node: scoreResult.severityBreakdown.critical.deductionPerNode,
        total_deduction: scoreResult.severityBreakdown.critical.totalDeduction,
      },
      major: {
        count: scoreResult.severityBreakdown.major.count,
        deduction_per_node: scoreResult.severityBreakdown.major.deductionPerNode,
        total_deduction: scoreResult.severityBreakdown.major.totalDeduction,
      },
      minor: {
        count: scoreResult.severityBreakdown.minor.count,
        deduction_per_node: scoreResult.severityBreakdown.minor.deductionPerNode,
        total_deduction: scoreResult.severityBreakdown.minor.totalDeduction,
      },
    },
    items: {},
  };

  // items: KWCAG 항목별 점수 상세도 snake_case 변환
  // ※ weight, weight_multiplier 필드 포함 (scorer.js에서 가중치 배수 적용)
  for (const [kwcagId, item] of Object.entries(scoreResult.items)) {
    scoreData.items[kwcagId] = {
      name: item.name,
      severity: item.severity,
      weight: item.weight,                      // 가중치 등급 (high/medium/low)
      weight_multiplier: item.weightMultiplier,  // 가중치 배수 (1.5/1.0/0.5)
      deduction_per_node: item.deductionPerNode,
      violation_count: item.violationCount,
      rule_count: item.ruleCount,
      pass_count: item.passCount,
      deduction: item.deduction,
    };
  }

  // ── 5) 최종 API 스펙 JSON 조립 ──
  //    analyzer_type: 'RULE_BASED' — 백엔드가 AI/CV 분석 결과와 구분하기 위한
  //    필드. v2 스펙에서는 여기에 'AI_NLP', 'COMPUTER_VISION'이 추가될 예정.
  return {
    analyzer_type: 'RULE_BASED',
    summary: {
      total_violations: kwcagResult.summary.totalViolations,
      total_passes: kwcagResult.summary.totalPasses,
      kwcag_violations: kwcagResult.summary.kwcagViolations,
      kwcag_passes: kwcagResult.summary.kwcagPasses,
      unmapped_violations: kwcagResult.summary.unmappedViolations,
      unmapped_passes: kwcagResult.summary.unmappedPasses,
    },
    violations,
    passes,
    unmapped_violations: unmappedViolations,
    score: scoreData,
    metadata: {
      url: kwcagResult.meta.url,
      engine: kwcagResult.meta.engine,
      engine_version: kwcagResult.meta.engineVersion,
      adapter_version: kwcagResult.meta.adapterVersion,
      scan_duration_ms: null,  // 여기서는 채우지 않음 — run() 본문에서 실제 측정값으로 덮어씀
      timestamp: kwcagResult.meta.timestamp,
    },
  };
}

/**
 * ─────────────────────────────────────────────────────────────────────────
 *  sendToBackend(requestId, apiData)
 * ─────────────────────────────────────────────────────────────────────────
 *  분석 결과를 백엔드 Spring Boot 서버로 POST 전송한다.
 *
 *  [왜 try/catch로 감싸서 예외를 "삼키는가"]
 *    중간발표 시점에는 백엔드가 아직 개발 중이라, 서버가 내려가 있어도 규칙
 *    기반 모듈 자체는 독립적으로 결과를 낼 수 있어야 한다. 네트워크 오류로
 *    인해 전체 파이프라인이 실패하면 데모·테스트가 막히므로, 실패를 조용히
 *    로그로만 남기고 로컬 JSON 저장은 계속 진행하게 설계했다.
 *    통합 단계(Phase 4)에서는 실패 시 재시도·큐잉 로직을 추가할 예정.
 *
 *  [엔드포인트 명명 규칙]
 *    /evaluations/{requestId}/analysis/rule-based
 *    → 하나의 "평가 요청(requestId)" 아래에 rule-based / ai-nlp / cv 세 개의
 *       분석 결과가 병렬로 POST되는 구조. 백엔드가 세 결과를 합쳐 대시보드를
 *       구성한다.
 * ─────────────────────────────────────────────────────────────────────────
 */
/**
 * ─────────────────────────────────────────────────────────────────────────
 *  detectBotBlock(page, renderedHtml)
 * ─────────────────────────────────────────────────────────────────────────
 *  [왜 추가했는가 — 실제로 발견된 문제]
 *    2026-06-22 hongik.ac.kr 실행 결과를 점검하다가, 저장된 result.html이
 *    실제 대학 홈페이지가 아니라 "Security Verification"이라는 봇 차단
 *    안내 페이지(botmanager-challenge.js 로드)였다는 사실을 발견함.
 *    page.goto()는 타임아웃/오류를 try/catch로 조용히 삼키고 있고(아래 run()
 *    참조), 그 뒤로는 "페이지를 성공적으로 받았다"고 가정하고 그대로
 *    axe-core를 돌려버림. 그 결과 빈 페이지가 위반 0건 통과 7건으로
 *    처리되어 rule_based 점수가 100점이 나왔고, text_extractor.py도
 *    블록 0개를 "완벽한 페이지"처럼 조용히 통과시켜서 난이도 점수도
 *    100점이 나왔음. 즉 "분석 실패"가 "만점"으로 둔갑하는 심각한 버그.
 *
 *  [탐지 방법 — 4가지 신호. 텍스트 길이만 단독으로는 더 이상 의심 판정하지 않음]
 *    1) 페이지 제목에 차단/캡차 관련 문구가 있는가
 *    2) 렌더링된 HTML에 알려진 봇 차단 스크립트 시그니처가 있는가
 *       (botmanager, cloudflare challenge, recaptcha, perimeterx, datadome 등)
 *    3) 최종 URL에 알려진 봇 차단/리다이렉트 서비스 시그니처가 있는가
 *       (예: 정부24 → plus.gov.kr/mbuster 리다이렉트 — 2026-09-16 추가)
 *    4) 렌더링된 본문 텍스트가 지나치게 짧고 (300자 미만) *동시에* 인터랙티브
 *       요소(a/button/input/img 등)도 적은가 (8개 미만)
 *
 *  [2026-09-16 개선 — 오탐 사례]
 *    기존에는 "본문 300자 미만"이면 그것만으로 OR 조건에 걸려 의심 판정이었음.
 *    그런데 jeongseon.go.kr처럼 버튼/이미지 위주라 실제 글자 수는 적지만 정상인
 *    페이지도 같은 방식으로 걸려버려 오탐(false positive)이 발생함
 *    (site_test_tracker.csv 9/14 기록). 텍스트가 짧아도 인터랙티브 요소가
 *    충분히 있으면 "콘텐츠가 원래 그런 페이지"로 보고 의심에서 제외하도록
 *    이중 조건(thinAndSparse)으로 변경. 대신 진짜 빈 페이지/차단 페이지를
 *    놓치지 않도록 URL 시그니처(3번)를 새로 추가해 텍스트 길이에 의존하지
 *    않는 탐지 경로를 하나 더 확보함.
 *
 *  [주의: 이 함수는 "확정 판정"이 아니라 "의심 신호"임]
 *    실제로 콘텐츠가 거의 없는 정상 페이지(예: 단순 안내 페이지)도 있을 수
 *    있으므로, 이 함수는 파이프라인을 중단시키지 않고 결과 JSON에 경고만
 *    남긴다. 최종 판단은 사람이 result_api.json의 warnings를 보고 내린다.
 * ─────────────────────────────────────────────────────────────────────────
 */
const BOT_TITLE_KEYWORDS = [
  'security verification', 'access denied', 'attention required',
  'just a moment', 'checking your browser', 'are you a robot',
  'unusual traffic', 'bot detection', '잠시만 기다려', '보안 확인',
  '접근이 거부', '비정상적인 접근',
];
const BOT_HTML_SIGNATURES = [
  'botmanager-challenge', '__cf_chl', 'cf-chl', 'g-recaptcha',
  'perimeterx', 'datadome', 'px-captcha', 'hcaptcha', '/deny/index.html',
];
// 2026-09-16 추가: URL 자체에 남는 봇 차단/리다이렉트 서비스 시그니처.
//   HTML 시그니처와 달리 렌더링된 페이지가 거의 비어 있어도(스크립트 자체가
//   안 잡혀도) 최종 URL만 보면 판별 가능한 경우를 커버.
const BOT_URL_SIGNATURES = [
  'mbuster', '/deny/', 'bot-check', 'bot_check', 'captcha',
];
const MIN_EXPECTED_BODY_TEXT_LENGTH = 300; // 실제 공공 웹페이지치고 이보다 짧으면 의심
// 2026-09-16 추가: 본문 텍스트가 짧아도 이 개수 이상의 인터랙티브 요소가 있으면
//   "버튼/이미지 위주라 글자가 적은 정상 페이지"로 보고 의심에서 제외.
const MIN_INTERACTIVE_ELEMENTS = 8;

async function detectBotBlock(page, renderedHtml) {
  const title = await page.title().catch(() => '');
  const currentUrl = page.url();
  const bodyText = await page
    .evaluate(() => (document.body ? document.body.innerText : ''))
    .catch(() => '');
  // 2026-09-16 추가: 인터랙티브 요소 수 — 텍스트가 짧아도 이게 많으면
  // "버튼 위주라 글자가 적은 정상 페이지"로 구분하기 위한 보조 신호.
  const interactiveCount = await page
    .evaluate(() => document.querySelectorAll('a, button, input, select, textarea, img').length)
    .catch(() => 0);

  const titleLower = title.toLowerCase();
  const htmlLower = renderedHtml.toLowerCase();
  const urlLower = currentUrl.toLowerCase();
  const bodyTextLength = bodyText.trim().length;

  const titleHit = BOT_TITLE_KEYWORDS.find((k) => titleLower.includes(k));
  const sigHit = BOT_HTML_SIGNATURES.find((k) => htmlLower.includes(k));
  const urlHit = BOT_URL_SIGNATURES.find((k) => urlLower.includes(k));
  const tooThin = bodyTextLength < MIN_EXPECTED_BODY_TEXT_LENGTH;
  const alsoSparse = interactiveCount < MIN_INTERACTIVE_ELEMENTS;
  // 본문이 짧다는 것만으로는 판정하지 않고, 인터랙티브 요소까지 적어야
  // ("진짜로 텅 빈 페이지") 의심 신호로 반영 — jeongseon.go.kr 오탐 방지.
  const thinAndSparse = tooThin && alsoSparse;

  const reasons = [];
  if (titleHit) reasons.push(`페이지 제목에 차단 관련 문구 감지: "${title}"`);
  if (sigHit) reasons.push(`알려진 봇 차단/캡차 스크립트 시그니처 감지: ${sigHit}`);
  if (urlHit) reasons.push(`최종 URL에 봇 차단/리다이렉트 서비스 시그니처 감지: "${urlHit}" (URL: ${currentUrl})`);
  if (thinAndSparse) {
    reasons.push(`렌더링된 본문 텍스트가 ${bodyTextLength}자로 짧고 인터랙티브 요소도 ${interactiveCount}개뿐 (임계값 텍스트 ${MIN_EXPECTED_BODY_TEXT_LENGTH}자/요소 ${MIN_INTERACTIVE_ELEMENTS}개) — 빈 페이지로 의심됨`);
  } else if (tooThin) {
    // 오탐 방지: 텍스트는 짧지만 인터랙티브 요소가 충분해 정상 UI로 판단.
    // 의심 판정에는 반영하지 않되, 참고용으로만 기록해 사람이 확인할 수 있게 함.
    reasons.push(`(참고) 본문 텍스트는 ${bodyTextLength}자로 짧지만 인터랙티브 요소가 ${interactiveCount}개 있어 정상 UI(버튼/이미지 위주 페이지)로 판단 — 차단 의심에서 제외`);
  }

  return {
    suspected: Boolean(titleHit || sigHit || urlHit || thinAndSparse),
    reasons,
    page_title: title,
    body_text_length: bodyTextLength,
    interactive_element_count: interactiveCount,
  };
}

/**
 * ─────────────────────────────────────────────────────────────────────────
 *  dismissPopups(page)
 * ─────────────────────────────────────────────────────────────────────────
 *  [왜 추가했는가 — 2026-09-16 테스트 중 발견]
 *    공공기관 사이트에 흔한 "레이어 팝업"(공지/이벤트 안내용 fixed/absolute
 *    오버레이 div)이 뜬 채로 스크린샷·렌더링 HTML을 그대로 캡처해버리는
 *    문제. 팝업이 화면을 가리면 CV 명암비 분석이 팝업 자체를 분석 대상으로
 *    삼아버리고, 텍스트 추출도 실제 본문 대신 팝업 문구를 가져가서
 *    data_quality_warning 오탐(본문 짧음 판정)의 숨은 원인이 되기도 함.
 *
 *  [전략 — 사이트마다 팝업 마크업이 전부 달라서 완벽한 해결은 불가능.
 *   범용 휴리스틱으로 최선의 노력만 함]
 *    1) 뷰포트의 20% 이상을 덮는 fixed/absolute, 고z-index(≥100) 요소를
 *       "팝업 후보"로 탐지
 *    2) 후보 내부에서 "닫기"류 텍스트/aria-label/class를 가진 자식을 찾아
 *       클릭 시도 (실제 팝업의 닫기 로직을 타는 게 가장 안전 — "오늘 하루
 *       보지 않기" 같은 세션/쿠키 처리까지 정상적으로 실행됨)
 *    3) 닫기 버튼을 못 찾으면 후보 자체를 display:none으로 강제 숨김
 *       (최후 수단 — 팝업 내부 로직은 안 타지만 화면에서는 사라짐)
 *    4) Escape 키 입력도 한 번 시도 (키보드로만 닫히는 모달 대응)
 *
 *  [주의] 오탐 가능성이 있음(예: 실제로 화면 대부분을 차지하는 게 정상인
 *  레이아웃). 하지만 실패 시 최악의 경우에도 "원래 있던 팝업이 그대로
 *  남아있는" 기존 상태와 같으므로 파이프라인에 해가 되지 않음(best-effort).
 * ─────────────────────────────────────────────────────────────────────────
 */
async function dismissPopups(page) {
  let closedCount = 0;
  try {
    closedCount = await page.evaluate(() => {
      const CLOSE_PATTERN = /(닫기|close|오늘\s*하루|다시\s*보지|안\s*보기|그만\s*보기|×|✕)/i;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const viewportArea = vw * vh;
      let closed = 0;

      const all = Array.from(document.querySelectorAll('body *'));
      for (const el of all) {
        const style = window.getComputedStyle(el);
        if (style.position !== 'fixed' && style.position !== 'absolute') continue;
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

        const zIndex = parseInt(style.zIndex, 10);
        if (!zIndex || zIndex < 100) continue; // 낮은 z-index는 헤더 등 팝업이 아닐 가능성이 높음

        const rect = el.getBoundingClientRect();
        const area = Math.max(0, rect.width) * Math.max(0, rect.height);
        if (area < viewportArea * 0.2) continue; // 화면의 20% 미만이면 작은 배너/툴팁으로 보고 건너뜀
        if (rect.bottom < 0 || rect.top > vh) continue; // 현재 화면 밖에 있으면 건너뜀

        // 팝업 후보 발견 — 내부에 "닫기"류 버튼이 있으면 클릭 시도(사이트 자체
        // 닫기 로직을 최대한 타게 하기 위함 — 있으면 클릭, 없어도 무방)
        const candidates = el.querySelectorAll('a, button, span, div, img, i');
        for (const c of candidates) {
          const label = `${c.textContent || ''} ${c.getAttribute('aria-label') || ''} ${c.className || ''} ${c.id || ''}`;
          if (CLOSE_PATTERN.test(label)) {
            c.click();
            break;
          }
        }
        // 닫기 버튼을 찾아 클릭은 해서 사이트 자체 로직(세션/쿠키 등)을
        // 최대한 타게 하되, 애니메이션 지연이나 핸들러 미동작으로 여전히
        // 화면에 남아있을 수 있으므로 클릭 여부와 무관하게 항상 강제로도
        // 숨긴다 — 스크린샷/HTML 캡처 시점엔 반드시 사라져 있어야 하므로.
        el.style.setProperty('display', 'none', 'important');
        closed += 1;
      }
      return closed;
    });
  } catch (e) {
    // 탐지 자체가 실패해도 파이프라인은 계속 진행 (best-effort이므로)
    console.log(`   [팝업 탐지 중 오류 — 무시하고 진행] ${e.message}`);
  }

  // 키보드 Escape도 한 번 시도 (일부 모달은 이 방식으로만 닫힘)
  await page.keyboard.press('Escape').catch(() => {});

  if (closedCount > 0) {
    console.log(`   팝업/오버레이 ${closedCount}개 닫음(또는 강제 숨김)`);
    // 클릭으로 인한 애니메이션/리렌더링이 끝날 시간을 잠깐 줌
    await page.waitForTimeout(500);
  }

  return closedCount;
}

async function sendToBackend(requestId, apiData) {
  const url = `${API_BASE_URL}/evaluations/${requestId}/analysis/rule-based`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(apiData),
    });

    if (response.ok) {
      const result = await response.json();
      console.log(`   백엔드 전송 성공 (analysis_id: ${result.analysis_id})`);
      return result;
    } else {
      // 4xx/5xx: 서버는 살아있지만 거부한 경우 (스펙 불일치 등)
      console.log(`    백엔드 전송 실패 (HTTP ${response.status})`);
      return null;
    }
  } catch (err) {
    // 네트워크 오류: 서버 자체가 접근 불가
    console.log(`    백엔드 서버 연결 불가 (${API_BASE_URL})`);
    console.log('      → 로컬 JSON 파일로만 저장됩니다.');
    return null;
  }
}

/**
 * ─────────────────────────────────────────────────────────────────────────
 *  run(url, outputPath) — 메인 실행 함수
 * ─────────────────────────────────────────────────────────────────────────
 * - 전체 흐름
    1. 브라우저 실행 & 페이지 로드
    2. 렌더링된 HTML 저장 (AI 모듈용)
    3. axe-core 접근성 검사
    4. 어댑터 반환 (axe(WCAG) -> KWCAG)
    5. 점수 산출
    6. API 형태로 반환(toApiFormat)
    7. 로컬 JSON 저장 (두 종류)
    8. 백앤두 전송 (현재 비활성화)
    9. 콘솔 요약 출력
 * ─────────────────────────────────────────────────────────────────────────
 *  단일 URL에 대한 전체 규칙 기반 분석 파이프라인을 수행
 *
 *  [왜 헤드리스 브라우저를 쓰는가]
 *    단순 fetch로 HTML을 가져오면 JavaScript가 실행되기 전의 "비어있는 DOM"이
 *    반환됨. 특히 정부24(www.gov.kr)는 Nuxt.js(Vue 기반 SSR/CSR 혼합)로
 *    만들어져 있어서, 원본 HTML에는 <div id="__nuxt"></div>만 있고 실제
 *    콘텐츠는 JS 실행 후에야 DOM에 들어감. Playwright로 실제 브라우저
 *    환경에서 렌더링해야 "사용자가 실제로 보는 화면"을 기준으로 접근성을
 *    검사할 수 있음.
 *
 *  [왜 chromium을 선택했는가]
 *    Playwright는 chromium/firefox/webkit 세 엔진을 지원하지만,
 *    ① 공공 웹사이트의 주요 사용자층(일반 국민) 중 크롬 계열 점유율이 높아
 *       실사용 환경과 가장 일치하고,
 *    ② axe-core가 chromium 기반에서 가장 많이 테스트되어 있으며,
 *    ③ Playwright 설치 시 기본으로 포함되어 초기 설정이 간단함.
 *
 *  [왜 locale: 'ko-KR' 을 명시하는가]
 *    일부 사이트가 Accept-Language 헤더로 언어별 다른 콘텐츠를 반환.
 *    (다국어 지원 정부 사이트). 한국 사용자 기준 접근성을 평가하므로 ko-KR로
 *    강제 고정해야 결과 재현성이 확보됨.
 *
 *  [왜 뷰포트를 1280x720으로 고정하는가]
 *    반응형 웹에서 뷰포트 크기에 따라 DOM 구조와 스타일이 달라질 수 있음.
 *    데스크톱 공공 서비스의 대표값으로 1280x720을 고정 — 테스트 재현성 확보.
 *    (모바일 접근성은 추후 별도 뷰포트로 확장 예정)
 * ─────────────────────────────────────────────────────────────────────────
 */
async function run(url, outputPath) {
  console.log(`\n검사 대상: ${url}`);
  console.log('─'.repeat(50));

  // ── 1) 브라우저 실행 & 페이지 로드 ──
  console.log('1. 브라우저 실행 중...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    locale: 'ko-KR',                     // 한국어 환경 강제 (Accept-Language: ko-KR)
    viewport: { width: 1280, height: 720 },  // 데스크톱 대표 해상도 고정
  });
  const page = await context.newPage();

  // ── 새 탭/창(window.open)으로 뜨는 팝업 자동 닫기 ──
  //   2026-09-16 추가: 구형 공공기관 사이트에 흔한 "오늘 하루 그만 보기"류
  //   이벤트/공지 팝업이 별도 브라우저 탭·창으로 열리는 경우 대응.
  //   메인 page가 아닌 새 Page가 열리면 즉시 닫아서 분석 대상에서 배제한다.
  //   (같은 페이지 안의 레이어 팝업은 dismissPopups()에서 별도 처리)
  //
  //   [2026-09-20 수정] 이 리스너는 캡처(HTML·스크린샷) 단계까지만 살아 있어야 한다.
  //   @axe-core/playwright의 analyze()가 결과 취합용으로 같은 context에 about:blank
  //   페이지를 내부적으로 새로 여는데, 리스너가 그걸 팝업으로 오인해 닫아버려
  //   "Target page, context or browser has been closed" 오류가 났음.
  //   → 핸들러를 변수로 빼서, axe 실행 직전에 context.off()로 해제한다.
  const popupHandler = async (newPage) => {
    if (newPage === page) return;
    try {
      await newPage.waitForLoadState('domcontentloaded', { timeout: 5000 }).catch(() => {});
      console.log(`   [팝업창 감지] 새 탭/창이 열려서 자동으로 닫음: ${newPage.url()}`);
      await newPage.close();
    } catch {
      // 이미 닫혔거나 접근 불가 — 무시하고 진행
    }
  };
  context.on('page', popupHandler);

  try {
    console.log('2. 페이지 로딩 중...');
    // waitUntil: 'networkidle' — 네트워크 요청이 500ms 이상 없을 때까지 대기
    //   → SSR 페이지뿐 아니라 CSR(Vue/React 등) 초기 데이터 로딩까지 기다림
    // timeout: 60000 (60초) — 공공 사이트 일부가 로딩이 느려 넉넉히 잡음
    try {
      await page.goto(url, { waitUntil: 'load', timeout: 60000 });
    } catch { }
    await page.waitForTimeout(5000);
    
    await page.waitForFunction(() => document.readyState === 'complete', { timeout: 10000 }).catch(() => {});

    // ── 1.5) 같은 페이지 안의 레이어 팝업 닫기/숨기기 ──
    //   2026-09-16 추가: HTML/스크린샷을 캡처하기 *전에* 실행해야 의미가
    //   있음(캡처 후에 닫아봐야 이미 늦음). detectBotBlock()보다도 먼저
    //   해야, 팝업이 본문을 가려서 생기는 "본문 짧음" 오탐도 줄어든다.
    await dismissPopups(page);

    // ── 2) 렌더링된 HTML 저장 (AI 모듈용) ──
    //   page.content()는 현재 DOM의 outerHTML을 반환 — JavaScript가 실행된
    //   "최종 상태"의 HTML. text_extractor.py가 이 파일을 읽어서 분석 대상
    //   텍스트를 추출.
    //
    //   파일명 규칙: outputPath가 'result.json'이면 'result.html'로 저장.
    //   outputPath가 없으면 오늘 날짜가 붙은 기본명 사용.
    const renderedHtml = await page.content();
    const htmlOutput = (outputPath || `result_${new Date().toISOString().slice(0, 10)}`).replace('.json', '.html');
    fs.writeFileSync(htmlOutput, renderedHtml, 'utf-8');
    console.log(`3. 렌더링된 HTML 저장: ${htmlOutput}`);

    // ── 2.5) 봇 차단/빈 페이지 의심 여부 확인 ──
    //   page.goto()의 오류가 위에서 조용히 삼켜지므로, 여기서 별도로
    //   "우리가 실제로 받은 페이지가 진짜 콘텐츠인지"를 점검한다.
    const botCheck = await detectBotBlock(page, renderedHtml);
    if (botCheck.suspected) {
      console.log('   [경고] 봇 차단/빈 페이지 의심됨:');
      for (const reason of botCheck.reasons) {
        console.log(`     - ${reason}`);
      }
      console.log('     → result_api.json의 warnings 필드에 기록됩니다. 점수를 그대로 신뢰하지 마세요.');
    } else if (botCheck.reasons.length > 0) {
      // 2026-09-16 추가: 의심 판정은 아니지만 참고할 만한 신호(예: 텍스트는
      // 짧지만 정상 UI로 판단됨)가 있으면 정보성으로만 출력.
      console.log('   [참고] 본문이 짧지만 정상 페이지로 판단됨:');
      for (const reason of botCheck.reasons) {
        console.log(`     - ${reason}`);
      }
    }

    // ── 3) 스크린샷 저장 (Python CV 모듈용) ──
    //   [2026-09-27 수정] fullPage: false → true.
    //   기존에는 뷰포트(1280x720) 첫 화면만 찍혀서, 스크롤해야 보이는 하단 배너·
    //   안내문의 명암비는 CV 모듈 검사 대상에서 빠져 있었음(README의 "풀페이지
    //   스크린샷" 설명과도 불일치). 이제 페이지 전체를 한 장으로 찍는다.
    //
    //   찍기 전에 페이지를 끝까지 한 번 스크롤했다가 맨 위로 돌아온다.
    //   지연 로딩(lazy-load) 이미지는 화면에 들어와야 불러오는 경우가 많아서,
    //   스크롤 없이 fullPage로 찍으면 하단 이미지가 빈 칸으로 찍힐 수 있기 때문.
    //   무한 스크롤 페이지에서 끝없이 내려가지 않도록 최대 30회(약 21,600px)로 제한.
    await page.evaluate(async () => {
      const step = window.innerHeight;
      for (let i = 0; i < 30; i++) {
        const before = window.scrollY;
        window.scrollBy(0, step);
        await new Promise((r) => setTimeout(r, 150));
        if (window.scrollY === before) break;   // 더 내려갈 곳이 없으면 종료
      }
      window.scrollTo(0, 0);
    }).catch(() => {});
    await page.waitForTimeout(500);

    const screenshotOutput = (outputPath || `result_${new Date().toISOString().slice(0, 10)}`).replace('.json', '.png');
    await page.screenshot({ path: screenshotOutput, fullPage: true, timeout: 60000 });
    const pageHeight = await page.evaluate(() => document.documentElement.scrollHeight).catch(() => null);
    console.log(`4. 스크린샷 저장(전체 페이지${pageHeight ? `, 높이 ${pageHeight}px` : ''}): ${screenshotOutput}`);

    // ── 4) axe-core 실행 ──
    //   withTags로 검사 범위를 명시적으로 제한
    //     wcag2a, wcag2aa   : WCAG 2.0 A/AA 등급 (국내 KWCAG의 직접 기반)
    //     wcag21a, wcag21aa : WCAG 2.1 A/AA (KWCAG 2.2가 참조하는 상위 기준)
    //     wcag22aa          : WCAG 2.2 AA (국제 최신 기준 — 추가 참고용)
    //   → KWCAG 2.2와 매핑되는 핵심 규칙을 모두 커버하되, AAA(최상위) 등급은
    //      공공 서비스의 현실적 준수 수준을 고려해 제외함.
    //
    //   [규칙기반 1차 개선 — 2026-09-16]
    //   3단계 WAVE/Lighthouse 교차검증(`규칙기반_WAVE_Lighthouse_교차검증.md`)에서
    //   5개 사이트 중 3곳에서 Lighthouse만 잡아낸 위반이 있었고, `landmark-one-main`
    //   (3건)·`meta-viewport`(1건)였음.
    //
    //   실제 원인 확인 결과(로컬 axe-core 4.13 기준, axe.getRules()로 태그 직접 조회):
    //     - landmark-one-main: tags = ['cat.semantics', 'best-practice'] — WCAG 등급
    //       태그가 전혀 없어서 위 withTags() 필터에 실제로 걸러지고 있었음. ← 진짜 원인.
    //     - meta-viewport: tags에 'wcag2aa'·'wcag144'가 포함돼 있어 원래도 withTags()
    //       범위 안에 있었음. 즉 스코프/설정 문제가 아니었고, 왜 그 1개 사이트에서만
    //       놓쳤는지는 별도 원인(렌더링 시점, axe-core 버전 차이 등)을 확인해야 함 —
    //       이번 1차 개선의 스코프 밖으로 두고 아래는 방어적으로만 명시.
    //   → 이번에는 확인된 원인인 landmark-one-main만 실질적으로 고치는 것이 목표.
    //     best-practice 태그를 통째로 켜면 재검증 범위가 커지므로(문서의 권고),
    //     이 규칙만 옵션으로 개별 강제 활성화한다.
    //
    //   [주의 — AxeBuilder#options()는 병합이 아니라 교체]
    //   @axe-core/playwright의 options()는 `this.option = options`로 기존 설정을
    //   통째로 덮어쓴다. withTags(tags).options({rules: {...}}) 순서로 체이닝하면
    //   withTags()가 세팅한 runOnly가 options() 호출 시 통째로 사라져서, 태그 제한
    //   자체가 풀리고 best-practice 규칙들이 대거 새로 실행돼버리는 걸 실제로
    //   재현해서 확인함(예: region, page-has-heading-one까지 같이 켜짐).
    //   그래서 runOnly와 rules를 하나의 options() 호출에 함께 넣어야 한다.
    // 캡처가 끝났으므로 새 탭 팝업 리스너 해제 — axe가 내부적으로 여는
    // about:blank 페이지를 닫아버리지 않도록 반드시 analyze() 전에 해제할 것.
    context.off('page', popupHandler);

    console.log('5. axe-core 접근성 검사 실행 중...');
    const scanStart = Date.now();
    const axeResults = await new AxeBuilder({ page })
      .options({
        runOnly: {
          type: 'tag',
          values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'],
        },
        rules: {
          'landmark-one-main': { enabled: true },
        },
      })
      .analyze();
    const scanDuration = Date.now() - scanStart;  // 성능 측정용 (API metadata에 기록)

    // ── 5) 어댑터 변환: axe 결과 → KWCAG 33개 항목 ──
    //   axe-core는 WCAG 기준의 영어 결과를 반환하므로, 이를 KWCAG 2.2의 한국
    //   항목 번호 체계(예: 5.1.1 "대체 텍스트 제공")로 재분류해야 발표·대시보드
    //   에서 의미가 전달된다. adapter.js의 mapping.js가 이 매핑을 담당.
    console.log('6. KWCAG 매핑 변환 중...');
    const kwcagResult = convert(axeResults);

    // ── 6) 점수화 ──
    //   scorer.js: 100점 만점에서 심각도 × 가중치 배수로 감점.
    //   감점 공식: severity 기본 감점 × weight 배수 × 위반 노드 수
    //   점수는 "개선 필요성의 상대적 강도"를 전달하기 위한 신호이지,
    //   학술적으로 정교한 지수는 아님 — 발표에서도 이 한계를 선제적으로 명시.
    console.log('7. 점수 산출 중...');
    const scoreResult = score(kwcagResult);

    // ── 7) API 스펙 형태로 변환 ──
    console.log('8. API 형태로 변환 중...');
    const apiData = toApiFormat(kwcagResult, scoreResult);
    apiData.metadata.scan_duration_ms = scanDuration;  // placeholder를 실측값으로 덮어쓰기

    // 봇 차단 의심 결과를 최상위 warnings 필드로 포함.
    // run_all.py가 이 필드를 읽어서 최종 result_final.json에도 경고를 전파함.
    apiData.warnings = {
      bot_block_suspected: botCheck.suspected,
      reasons: botCheck.reasons,
      page_title: botCheck.page_title,
      body_text_length: botCheck.body_text_length,
    };

    // ── 8) 로컬 JSON 저장 ──
    //   두 종류를 모두 저장:
    //   ① 내부 형식 (kwcagResult + score 병합) — 개발·디버깅용, camelCase
    //   ② API 스펙 형식 (apiData) — 백엔드 전송용, snake_case
    //   병렬 저장의 이유: 문제 발생 시 어느 단계에서 틀어졌는지 원본/변환
    //   결과를 모두 확인할 수 있어야 함.
    kwcagResult.score = scoreResult;  // 내부 형식에 score를 덧붙여 단일 객체로 묶음
    const output = outputPath || `result_${new Date().toISOString().slice(0, 10)}.json`;
    fs.writeFileSync(output, JSON.stringify(kwcagResult, null, 2), 'utf-8');

    // API 스펙 형식은 _api 접미사를 붙인 별도 파일로 저장
    const apiOutput = output.replace('.json', '_api.json');
    fs.writeFileSync(apiOutput, JSON.stringify(apiData, null, 2), 'utf-8');

    // ── 8) 백엔드 전송 시도 (현재는 비활성화) ──
    //   TODO: request_id는 백엔드가 평가 요청 생성 시 먼저 발급해야 하는 값.
    //   현재 Phase 1 단계에서는 백엔드가 미완성이므로 주석 처리.
    //   Phase 4(통합)에서 실제 requestId를 받아 활성화할 예정.
    // await sendToBackend(requestId, apiData);

    // ── 9) 콘솔 요약 출력 (사람이 읽기 위한 것) ──
    //   JSON 파일만으로는 테스트 중 한눈에 상태 파악이 어려워, 핵심 지표를
    //   구분선과 함께 출력. 발표 시연에서도 이 콘솔 출력을 그대로 보여줄 수 있음.
    console.log('─'.repeat(50));
    console.log('검사 결과 요약');
    console.log('─'.repeat(50));
    if (botCheck.suspected) {
      console.log('  ⚠ 경고: 이 결과는 봇 차단/빈 페이지일 가능성이 있습니다.');
      console.log(`     사유: ${botCheck.reasons.join(' / ')}`);
      console.log('     아래 점수는 실제 사이트 콘텐츠를 반영하지 않을 수 있습니다.');
      console.log('');
    }
    console.log(`  URL: ${kwcagResult.meta.url}`);
    console.log(`  엔진: ${kwcagResult.meta.engine} v${kwcagResult.meta.engineVersion}`);
    console.log(`  스캔 소요: ${scanDuration}ms`);
    console.log('');

    // 점수 출력 (등급은 run_all.py의 최종 등급으로 통일 — 2026-09-27)
    console.log(`   접근성 점수: ${scoreResult.score} / ${scoreResult.maxScore}점`);
    console.log(`    총 감점: -${scoreResult.totalDeduction}점`);
    console.log('');

    // 심각도별 감점 내역
    // ※ weight 배수가 항목마다 다르므로, "N건 × M점"이 아니라
    //    심각도별 총 감점을 직접 표시 (정확한 값은 scorer가 이미 계산해 둠)
    const sb = scoreResult.severityBreakdown;
    if (sb.critical.count > 0) {
      console.log(`    Critical: ${sb.critical.count}건, 총 감점 -${sb.critical.totalDeduction}점 (기본 ${sb.critical.deductionPerNode}점 × 항목별 가중치 적용)`);
    }
    if (sb.major.count > 0) {
      console.log(`    Major:    ${sb.major.count}건, 총 감점 -${sb.major.totalDeduction}점 (기본 ${sb.major.deductionPerNode}점 × 항목별 가중치 적용)`);
    }
    if (sb.minor.count > 0) {
      console.log(`    Minor:    ${sb.minor.count}건, 총 감점 -${sb.minor.totalDeduction}점 (기본 ${sb.minor.deductionPerNode}점 × 항목별 가중치 적용)`);
    }
    console.log('');

    // 전체 위반/통과 집계
    console.log(`  전체 위반: ${kwcagResult.summary.totalViolations}개 요소`);
    console.log(`  전체 통과: ${kwcagResult.summary.totalPasses}개 요소`);
    console.log(`  KWCAG 매핑 위반: ${kwcagResult.summary.kwcagViolations}개 요소`);
    console.log(`  추가 참고 위반: ${kwcagResult.summary.unmappedViolations}개 요소`);
    console.log('');

    // KWCAG 항목별 위반 출력 (위반 건수 많은 순으로 정렬)
    //   발표에서 "이 사이트는 어떤 항목이 특히 취약한가"를 한눈에 보여주기 위함.
    //   가중치(weight) 정보도 함께 표시하여 감점 근거를 명확히 함.
    const violatedItems = Object.entries(kwcagResult.kwcag)
      .filter(([, item]) => item.violationCount > 0)
      .sort((a, b) => b[1].violationCount - a[1].violationCount);

    if (violatedItems.length > 0) {
      console.log('  위반 항목:');
      for (const [id, item] of violatedItems) {
        const itemScore = scoreResult.items[id];
        const sev = itemScore?.severity || '?';
        const wt = itemScore?.weight || '?';
        const ded = itemScore?.deduction || 0;
        console.log(`    [${sev.toUpperCase()}×${wt}] ${id} ${item.name}: ${item.violationCount}건 (-${ded}점)`);
      }
    } else {
      console.log('  KWCAG 매핑 항목에서 위반 없음');
    }

    // unmapped 위반 출력 (KWCAG에 매핑되지 않지만 axe가 발견한 위반)
    //   감추지 않고 노출하는 이유: 투명성 + 향후 KWCAG 확장 시 반영 가능.
    if (kwcagResult.unmapped.violations.length > 0) {
      console.log('');
      console.log('  추가 참고 (KWCAG 미매핑):');
      for (const v of kwcagResult.unmapped.violations) {
        const nodeCount = v.nodes ? v.nodes.length : 0;
        console.log(`    [${v.impact}] ${v.axeRuleId}: ${nodeCount}건 - ${v.help}`);
      }
    }

    console.log('');
    console.log(`결과 저장: ${path.resolve(output)}`);
    console.log(`API 형태: ${path.resolve(apiOutput)}`);
    console.log(`렌더링 HTML: ${path.resolve(htmlOutput)}`);
    console.log(`스크린샷: ${path.resolve(screenshotOutput)}`);
    console.log('─'.repeat(50));

    return kwcagResult;
  } catch (err) {
    // 페이지 로딩 실패, axe 실행 오류 등 — 메시지만 출력하고 상위로 재throw
    // (CLI 진입부에서 exit code 1로 종료)
    console.error('검사 중 오류 발생:', err.message);
    throw err;
  } finally {
    // finally 블록: try 안에서 어떤 에러가 나도 브라우저 프로세스는 반드시 종료.
    // 이게 없으면 chromium 프로세스가 좀비로 남아 메모리를 계속 점유함.
    await browser.close();
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  CLI 진입부
// ─────────────────────────────────────────────────────────────────────────────
//  process.argv 구조: [node 실행파일, run.js 경로, ...사용자 인자]
//  slice(2)로 사용자 인자만 남김.
//  인자가 없으면 사용법을 안내하고 exit code 1로 종료.
// ─────────────────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
if (args.length === 0) {
  console.log('사용법: node run.js <URL> [출력파일.json]');
  console.log('예시:   node run.js https://www.gov.kr result.json');
  process.exit(1);
}

// run()이 실패하면 exit code 1로 종료 (CI나 쉘 스크립트가 에러를 감지할 수 있도록)
run(args[0], args[1]).catch(() => process.exit(1));
