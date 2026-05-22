/**
 * 어댑터 단위 테스트
 * 실행: node src/test.js
 *
 * axe-core 실행 없이 모의 데이터로 매핑 로직을 검증
 */

const { convert, extractWcagIds, resolveKwcagIds, formatWcagReference } = require('./adapter');
const { kwcagItems, axeRuleToKwcag, wcagToKwcag } = require('./mapping');

let passed = 0;
let failed = 0;

function assert(condition, testName) {
  if (condition) {
    console.log(`  ✅ ${testName}`);
    passed++;
  } else {
    console.log(`  ❌ ${testName}`);
    failed++;
  }
}

console.log('KWCAG 어댑터 단위 테스트\n');

// ── 1. 매핑 데이터 무결성 ──
console.log('1. 매핑 데이터 무결성');
assert(Object.keys(kwcagItems).length === 33, 'KWCAG 항목 33개');
assert(Object.keys(axeRuleToKwcag).length > 0, 'axe 규칙 매핑 존재');
assert(Object.keys(wcagToKwcag).length > 0, 'WCAG 역매핑 존재');

// ── 2. WCAG 태그 파싱 ──
console.log('\n2. WCAG 태그 파싱');
assert(
  JSON.stringify(extractWcagIds(['wcag2a', 'wcag111', 'cat.text-alternatives']))
    === JSON.stringify(['1.1.1']),
  'wcag111 → 1.1.1'
);
assert(
  JSON.stringify(extractWcagIds(['wcag2aa', 'wcag143']))
    === JSON.stringify(['1.4.3']),
  'wcag143 → 1.4.3'
);
assert(
  JSON.stringify(extractWcagIds(['wcag2aa', 'wcag2411']))
    === JSON.stringify(['2.4.11']),
  'wcag2411 → 2.4.11 (2자리 이상 하위번호)'
);
assert(
  extractWcagIds(['cat.color', 'best-practice']).length === 0,
  '비 WCAG 태그는 무시'
);

// ── 3. 규칙 ID 직접 매핑 ──
console.log('\n3. 규칙 ID 직접 매핑');
assert(
  resolveKwcagIds('image-alt', []).includes('5.1.1'),
  'image-alt → 5.1.1'
);
assert(
  resolveKwcagIds('color-contrast', []).includes('5.4.3'),
  'color-contrast → 5.4.3'
);
assert(
  resolveKwcagIds('aria-command-name', []).includes('8.2.1'),
  'aria-command-name → 8.2.1 (4.1.2이지만 8.1.1이 아닌 8.2.1)'
);
assert(
  resolveKwcagIds('duplicate-id', []).includes('8.1.1'),
  'duplicate-id → 8.1.1'
);

// ── 4. WCAG 태그 fallback 매핑 ──
console.log('\n4. WCAG 태그 fallback 매핑');
assert(
  resolveKwcagIds('unknown-rule-xyz', ['wcag111']).includes('5.1.1'),
  '미등록 규칙이라도 wcag111 태그 → 5.1.1'
);
assert(
  resolveKwcagIds('unknown-rule-xyz', ['best-practice']).length === 0,
  'WCAG 태그 없으면 unmapped'
);

// ── 5. 전체 변환 (모의 axe-core 결과) ──
console.log('\n5. 전체 변환 테스트');
const mockAxeResult = {
  url: 'https://test.example.com',
  timestamp: '2026-03-25T12:00:00.000Z',
  testEngine: { name: 'axe-core', version: '4.9.0' },
  violations: [
    {
      id: 'image-alt',
      impact: 'critical',
      tags: ['wcag2a', 'wcag111', 'cat.text-alternatives'],
      description: 'Images must have alternate text',
      help: 'Images must have alternate text',
      helpUrl: 'https://dequeuniversity.com/rules/axe/4.9/image-alt',
      nodes: [
        { target: ['img.logo'], html: '<img class="logo" src="logo.png">', impact: 'critical', failureSummary: 'Fix: add alt attribute' },
        { target: ['img.banner'], html: '<img class="banner" src="banner.jpg">', impact: 'critical', failureSummary: 'Fix: add alt attribute' },
      ],
    },
    {
      id: 'color-contrast',
      impact: 'serious',
      tags: ['wcag2aa', 'wcag143'],
      description: 'Elements must meet minimum color contrast ratio thresholds',
      help: 'Elements must have sufficient color contrast',
      helpUrl: 'https://dequeuniversity.com/rules/axe/4.9/color-contrast',
      nodes: [
        { target: ['p.intro'], html: '<p class="intro" style="color:#999">text</p>', impact: 'serious', failureSummary: 'Fix: increase contrast' },
      ],
    },
    {
      // KWCAG에 매핑되지 않는 규칙 (추가 참고 카테고리로 가야 함)
      id: 'some-best-practice-rule',
      impact: 'minor',
      tags: ['best-practice'],
      description: 'Some best practice rule',
      help: 'Follow best practice',
      helpUrl: '',
      nodes: [
        { target: ['div.widget'], html: '<div class="widget"></div>', impact: 'minor', failureSummary: '' },
      ],
    },
  ],
  passes: [
    {
      id: 'html-has-lang',
      tags: ['wcag2a', 'wcag311'],
      description: 'html element must have a lang attribute',
      nodes: [
        { target: ['html'], html: '<html lang="ko">' },
      ],
    },
  ],
  incomplete: [],
};

const result = convert(mockAxeResult);

assert(result.meta.url === 'https://test.example.com', '메타정보: URL');
assert(result.meta.engineVersion === '4.9.0', '메타정보: 엔진 버전');

assert(result.kwcag['5.1.1'].violationCount === 2, '5.1.1 위반 2개 요소');
assert(result.kwcag['5.1.1'].violations.length === 1, '5.1.1 위반 1개 규칙');
assert(result.kwcag['5.1.1'].violations[0].axeRuleId === 'image-alt', '5.1.1 규칙 ID = image-alt');

assert(result.kwcag['5.4.3'].violationCount === 1, '5.4.3 위반 1개 요소');
assert(result.kwcag['5.4.3'].violations[0].impact === 'serious', '5.4.3 impact = serious');

assert(result.kwcag['7.1.1'].passCount === 1, '7.1.1 통과 1개 요소');

assert(result.unmapped.violations.length === 1, 'unmapped 위반 1개 규칙');
assert(result.unmapped.violations[0].axeRuleId === 'some-best-practice-rule', 'unmapped = best-practice 규칙');

assert(result.summary.kwcagViolations === 3, '요약: KWCAG 위반 3개 요소');
assert(result.summary.unmappedViolations === 1, '요약: unmapped 위반 1개 요소');
assert(result.summary.totalViolations === 4, '요약: 전체 위반 4개 요소');

// ── 6. 출력 JSON 구조 확인 ──
console.log('\n6. 출력 JSON 구조');
assert('meta' in result, 'meta 존재');
assert('kwcag' in result, 'kwcag 존재');
assert('unmapped' in result, 'unmapped 존재');
assert('summary' in result, 'summary 존재');
assert(Object.keys(result.kwcag).length === 33, 'kwcag 33개 항목 전부 포함');

// ── 7. formatWcagReference 함수 ──
console.log('\n7. formatWcagReference 함수');
assert(
  formatWcagReference(['1.4.4']) === 'WCAG 1.4.4 기준',
  'WCAG 태그 1개 → "WCAG 1.4.4 기준"'
);
assert(
  formatWcagReference(['1.4.4', '1.4.10']) === 'WCAG 1.4.4, 1.4.10 기준',
  'WCAG 태그 여러 개 → 쉼표 연결'
);
assert(
  formatWcagReference([]) === 'WCAG 기준 미확인',
  '빈 배열 → "WCAG 기준 미확인"'
);
assert(
  formatWcagReference(null) === 'WCAG 기준 미확인',
  'null → "WCAG 기준 미확인"'
);
assert(
  formatWcagReference(undefined) === 'WCAG 기준 미확인',
  'undefined → "WCAG 기준 미확인"'
);

// ── 8. unmapped 항목의 WCAG 참조 정보 ──
console.log('\n8. unmapped WCAG 참조 테스트');

// 8-1. WCAG 태그 없는 unmapped violation → wcagReference = 'WCAG 기준 미확인'
assert(
  result.unmapped.violations[0].wcagReference === 'WCAG 기준 미확인',
  'best-practice 규칙 → wcagReference = "WCAG 기준 미확인"'
);

// 8-2. WCAG 태그가 있지만 KWCAG 매핑이 없는 violation
const mockWithWcagUnmapped = {
  url: 'https://test2.go.kr',
  violations: [
    {
      id: 'unknown-wcag-rule',
      impact: 'moderate',
      tags: ['wcag2aa', 'wcag144', 'wcag1410'],
      description: 'Unknown rule with WCAG tags',
      help: 'Help text',
      helpUrl: 'https://example.com',
      nodes: [
        { target: ['span.text'], html: '<span class="text">test</span>', impact: 'moderate', failureSummary: 'Fix it' },
      ],
    },
  ],
  passes: [
    {
      id: 'unknown-pass-rule',
      tags: ['wcag2aa', 'wcag144'],
      description: 'Unknown pass with WCAG tags',
      nodes: [
        { target: ['button.ok'], html: '<button class="ok">OK</button>' },
      ],
    },
  ],
  incomplete: [],
};

const result2 = convert(mockWithWcagUnmapped);

// wcag144 (1.4.4)는 KWCAG에 매핑 없음 → unmapped로 가되 WCAG 정보 보존
// 단, wcag1410 (1.4.10)도 매핑 없음
assert(
  result2.unmapped.violations.length === 1,
  'WCAG 태그 있지만 KWCAG 매핑 없는 규칙 → unmapped'
);
assert(
  result2.unmapped.violations[0].wcagTags.includes('1.4.4'),
  'unmapped violation에 wcagTags 보존 (1.4.4)'
);
assert(
  result2.unmapped.violations[0].wcagTags.includes('1.4.10'),
  'unmapped violation에 wcagTags 보존 (1.4.10)'
);
assert(
  result2.unmapped.violations[0].wcagReference === 'WCAG 1.4.4, 1.4.10 기준',
  'unmapped violation wcagReference = "WCAG 1.4.4, 1.4.10 기준"'
);

// 8-3. unmapped passes에도 wcagReference 존재
assert(
  result2.unmapped.passes.length > 0,
  'unmapped passes 존재'
);
assert(
  'wcagReference' in result2.unmapped.passes[0],
  'unmapped pass에 wcagReference 필드 존재'
);
assert(
  'wcagTags' in result2.unmapped.passes[0],
  'unmapped pass에 wcagTags 필드 존재'
);

// 8-4. KWCAG에 매핑되는 violation은 wcagReference가 없어야 함 (불필요)
const mockMapped = {
  url: 'https://test3.go.kr',
  violations: [
    {
      id: 'image-alt',
      impact: 'critical',
      tags: ['wcag2a', 'wcag111'],
      description: 'Images must have alternate text',
      help: 'Help',
      helpUrl: '',
      nodes: [{ target: ['img'], html: '<img>', impact: 'critical', failureSummary: '' }],
    },
  ],
  passes: [],
  incomplete: [],
};

const result3 = convert(mockMapped);
assert(
  result3.kwcag['5.1.1'].violations[0].wcagReference === undefined,
  'KWCAG 매핑된 violation에는 wcagReference 없음'
);
assert(
  result3.unmapped.violations.length === 0,
  'KWCAG 매핑 성공 시 unmapped에 안 들어감'
);

// ── 결과 ──
console.log('\n' + '─'.repeat(40));
console.log(`결과: ${passed}개 통과, ${failed}개 실패`);
if (failed === 0) {
  console.log('모든 테스트 통과!\n');
} else {
  console.log('실패한 테스트를 확인하세요.\n');
  process.exit(1);
}
