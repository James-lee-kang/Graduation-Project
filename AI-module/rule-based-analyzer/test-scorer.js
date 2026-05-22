/**
 * scorer.js 테스트
 */

const { score, DEDUCTION, MAX_SCORE } = require('./scorer');
const { convert } = require('./adapter');

let passed = 0;
let failed = 0;

function assert(condition, label) {
  if (condition) {
    console.log(`  ✓ ${label}`);
    passed++;
  } else {
    console.log(`  ✗ ${label}`);
    failed++;
  }
}

// ── 1. 위반 없음 → 100점 ──
console.log('\n── 1. 위반 없음 → 만점 ──');
{
  const axeResults = {
    url: 'https://example.com',
    violations: [],
    passes: [
      { id: 'image-alt', tags: ['wcag111'], description: 'ok', nodes: [{ target: ['img'], html: '<img alt="x">' }] },
    ],
    incomplete: [],
  };
  const result = score(convert(axeResults));
  assert(result.score === 100, '점수 100');
  assert(result.grade === 'A', '등급 A');
  assert(result.totalDeduction === 0, '감점 0');
}

// ── 2. critical 위반 → 건당 3점 감점 ──
console.log('\n── 2. critical 위반 감점 ──');
{
  const axeResults = {
    url: 'https://example.com',
    violations: [
      {
        id: 'image-alt',   // → 5.1.1 (critical)
        tags: ['wcag111'],
        description: 'Images must have alt',
        help: 'add alt',
        impact: 'critical',
        nodes: [
          { target: ['img.a'], html: '<img>' },
          { target: ['img.b'], html: '<img>' },
        ],
      },
    ],
    passes: [],
    incomplete: [],
  };
  const result = score(convert(axeResults));
  assert(result.score === 94, `점수 94 (100 - 3*2), got ${result.score}`);
  assert(result.severityBreakdown.critical.count === 2, 'critical 2건');
  assert(result.severityBreakdown.critical.totalDeduction === 6, 'critical 감점 6');
  assert(result.items['5.1.1'].severity === 'critical', '5.1.1 severity critical');
}

// ── 3. major 위반 → 건당 2점 감점 ──
console.log('\n── 3. major 위반 감점 ──');
{
  const axeResults = {
    url: 'https://example.com',
    violations: [
      {
        id: 'color-contrast',   // → 5.4.3 (major)
        tags: ['wcag143'],
        description: 'Contrast',
        help: 'fix contrast',
        impact: 'serious',
        nodes: [
          { target: ['p.a'], html: '<p>low</p>' },
          { target: ['p.b'], html: '<p>low</p>' },
          { target: ['p.c'], html: '<p>low</p>' },
        ],
      },
    ],
    passes: [],
    incomplete: [],
  };
  const result = score(convert(axeResults));
  assert(result.score === 94, `점수 94 (100 - 2*3), got ${result.score}`);
  assert(result.severityBreakdown.major.count === 3, 'major 3건');
  assert(result.items['5.4.3'].severity === 'major', '5.4.3 severity major');
}

// ── 4. minor 위반 → 건당 1점 감점 ──
console.log('\n── 4. minor 위반 감점 ──');
{
  const axeResults = {
    url: 'https://example.com',
    violations: [
      {
        id: 'document-title',   // → 6.4.2 (minor)
        tags: ['wcag242'],
        description: 'No title',
        help: 'add title',
        impact: 'serious',
        nodes: [
          { target: ['html'], html: '<html>' },
        ],
      },
    ],
    passes: [],
    incomplete: [],
  };
  const result = score(convert(axeResults));
  assert(result.score === 99, `점수 99 (100 - 1*1), got ${result.score}`);
  assert(result.items['6.4.2'].severity === 'minor', '6.4.2 severity minor');
}

// ── 5. 복합 위반 ──
console.log('\n── 5. 복합 위반 (critical + major + minor) ──');
{
  const axeResults = {
    url: 'https://example.com',
    violations: [
      {
        id: 'image-alt',         // critical, 2 nodes
        tags: ['wcag111'],
        description: 'alt',
        help: 'alt',
        impact: 'critical',
        nodes: [
          { target: ['img.1'], html: '<img>' },
          { target: ['img.2'], html: '<img>' },
        ],
      },
      {
        id: 'color-contrast',   // major, 1 node
        tags: ['wcag143'],
        description: 'contrast',
        help: 'contrast',
        impact: 'serious',
        nodes: [
          { target: ['p.1'], html: '<p>' },
        ],
      },
      {
        id: 'document-title',   // minor, 1 node
        tags: ['wcag242'],
        description: 'title',
        help: 'title',
        impact: 'serious',
        nodes: [
          { target: ['html'], html: '<html>' },
        ],
      },
    ],
    passes: [],
    incomplete: [],
  };
  const result = score(convert(axeResults));
  // critical: 2*3=6, major: 1*2=2, minor: 1*1=1 → 총 9 → 91점
  assert(result.score === 91, `점수 91, got ${result.score}`);
  assert(result.totalDeduction === 9, `총감점 9, got ${result.totalDeduction}`);
  assert(result.grade === 'B', `등급 B, got ${result.grade}`);
}

// ── 6. unmapped → minor 취급 ──
console.log('\n── 6. unmapped 위반 minor 취급 ──');
{
  const axeResults = {
    url: 'https://example.com',
    violations: [
      {
        id: 'totally-unknown-rule',
        tags: ['best-practice'],
        description: 'Unknown rule',
        help: 'Unknown',
        impact: 'minor',
        nodes: [
          { target: ['div.x'], html: '<div>' },
          { target: ['div.y'], html: '<div>' },
        ],
      },
    ],
    passes: [],
    incomplete: [],
  };
  const result = score(convert(axeResults));
  assert(result.score === 98, `점수 98 (100 - 1*2), got ${result.score}`);
  assert(result.unmapped.violationNodes === 2, 'unmapped 2건');
  assert(result.unmapped.deduction === 2, 'unmapped 감점 2');
}

// ── 7. 최저 0점 보장 ──
console.log('\n── 7. 대량 위반 시 최저 0점 ──');
{
  const nodes = [];
  for (let i = 0; i < 50; i++) {
    nodes.push({ target: [`img.${i}`], html: '<img>' });
  }
  const axeResults = {
    url: 'https://example.com',
    violations: [
      {
        id: 'image-alt',   // critical, 50 nodes → 150점 감점
        tags: ['wcag111'],
        description: 'alt',
        help: 'alt',
        impact: 'critical',
        nodes,
      },
    ],
    passes: [],
    incomplete: [],
  };
  const result = score(convert(axeResults));
  assert(result.score === 0, `최저 0점, got ${result.score}`);
  assert(result.totalDeduction === 150, `총감점 150, got ${result.totalDeduction}`);
  assert(result.grade === 'F', `등급 F, got ${result.grade}`);
}

// ── 8. 등급 경계 테스트 ──
console.log('\n── 8. 등급 경계 ──');
{
  // 정확히 95점 → A
  const r95 = score({
    kwcag: Object.fromEntries(
      Object.keys(require('./mapping').kwcagItems).map(id => [id, { violationCount: 0, violations: [], passCount: 0 }])
    ),
    unmapped: { violations: [{ nodes: new Array(5).fill({}) }] },
  });
  assert(r95.score === 95, `95점 → A, got ${r95.score}`);
  assert(r95.grade === 'A', `등급 A, got ${r95.grade}`);
}

// ── 9. items에 severity 정보 포함 확인 ──
console.log('\n── 9. items severity 정보 ──');
{
  const axeResults = {
    url: 'https://example.com',
    violations: [
      {
        id: 'label',   // → 7.3.2 (critical)
        tags: ['wcag332'],
        description: 'label',
        help: 'label',
        impact: 'critical',
        nodes: [{ target: ['input'], html: '<input>' }],
      },
    ],
    passes: [],
    incomplete: [],
  };
  const result = score(convert(axeResults));
  assert(result.items['7.3.2'].severity === 'critical', '7.3.2 critical');
  assert(result.items['7.3.2'].deductionPerNode === 3, '건당 3점');
  assert(result.items['7.3.2'].deduction === 3, '감점 3');
}

// ── 결과 ──
console.log('\n' + '─'.repeat(40));
console.log(`결과: ${passed}개 통과, ${failed}개 실패`);
if (failed === 0) {
  console.log('모든 테스트 통과!\n');
} else {
  console.log('실패한 테스트를 확인하세요.\n');
  process.exit(1);
}
