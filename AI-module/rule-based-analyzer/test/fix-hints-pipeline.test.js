'use strict';

// run()을 처음부터 끝까지 돌려서, 한국어 메시지와 노드별 수정 안내가 result_api.json에
// 제대로 실리는지, 그리고 언어를 영어로 바꿔도 점수가 같은지 확인한다.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { run } = require('../run');

const IMAGE = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';
const TINY = 'width:10px;height:10px;padding:0;border:1px solid #000';

const PAGE = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>수정 안내 시험</title></head><body>
  <main><h1>시정 소식</h1>
    <p>시청 홈페이지 본문입니다. 민원 신청, 공지사항, 자료실 서비스를 안내합니다.</p>
    <p id="low" style="color:#777777;background:#ffffff">회색 글자의 대비가 부족한 안내 문장입니다. 민원 서류 발급 안내.</p>
    <div id="dark" style="background:#808080;color:#ffffff;padding:4px">회색 바탕 위의 흰 글자 안내 문구입니다.</div>
    <button id="t1" aria-label="이전" style="${TINY}"></button><button id="t2" aria-label="다음" style="${TINY}"></button>
    <img id="noalt" src="${IMAGE}" width="20" height="20">
  </main></body></html>`;

// run()은 진행 로그를 console.log로 많이 찍는다. 테스트 출력이 길어지면 읽기 어렵고
// node:test 러너의 파일 간 통신(표준출력 공유)이 드물게 깨지는 원인이 되므로 이 파일에서는 끈다.
async function quietly(task) {
  const original = console.log;
  console.log = () => {};
  try {
    return await task();
  } finally {
    console.log = original;
  }
}

async function scan(env) {
  const server = http.createServer((request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end(PAGE);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'fix-hints-test-'));
  const previous = process.env.AXE_LOCALE;
  if (env.AXE_LOCALE === undefined) delete process.env.AXE_LOCALE; else process.env.AXE_LOCALE = env.AXE_LOCALE;
  try {
    await quietly(() => run(`http://127.0.0.1:${server.address().port}/`, path.join(directory, 'result.json'),
      { settleMs: 0, contentGraceMs: 0, compareLoad: false }));
    return JSON.parse(fs.readFileSync(path.join(directory, 'result_api.json'), 'utf8'));
  } finally {
    if (previous === undefined) delete process.env.AXE_LOCALE; else process.env.AXE_LOCALE = previous;
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function nodesOf(api, ruleId) {
  const found = [];
  for (const item of api.violations) {
    for (const rule of item.rules) if (rule.axe_rule_id === ruleId) found.push(...rule.nodes);
  }
  return found;
}

function summary(api) {
  return {
    score: api.score.score,
    rules: api.violations.map(item => [item.kwcag_id, item.violation_count,
      item.rules.map(rule => [rule.axe_rule_id, rule.nodes.length])]),
  };
}

test('결과 JSON: 한국어 failure_summary에 대비 추천색과 조작 대상 크기 안내가 붙고, 영어로 돌려도 점수가 같다', async () => {
  const korean = await scan({});

  const contrast = nodesOf(korean, 'color-contrast');
  const low = contrast.find(node => node.selector === '#low');
  assert.ok(low, `#low 노드 (실제: ${contrast.map(node => node.selector).join(', ')})`);
  assert.match(low.failure_summary, /^다음 중 하나를 해결하세요:\n  엘리먼트가 4\.47 /);
  assert.ok(low.failure_summary.endsWith(
    '\n\n개선 안내\n• 글자색을 바꾼다면: #777777 → #767676 (더 어둡게, 명도 대비 4.54:1 / 기준 4.5:1)'),
  low.failure_summary);
  assert.equal(low.fix_hint.kind, 'color-contrast');
  assert.equal(low.fix_hint.text_color.suggested_hex, '#767676');
  assert.equal(low.fix_hint.contrast_ratio, 4.47);

  // 회색 배경의 흰 글자: 글자는 더 밝아질 수 없으니 배경을 어둡게 하라고 안내한다
  const dark = contrast.find(node => node.selector === '#dark');
  assert.ok(dark);
  assert.equal(dark.fix_hint.text_is_lighter, true);
  assert.equal(dark.fix_hint.text_color.meets_target, false);
  assert.equal(dark.fix_hint.background_color.suggested_hex, '#767676');
  assert.match(dark.failure_summary, /개선 안내\n• 배경색을 바꾼다면: #808080 → #767676 \(더 어둡게, 명도 대비 4\.54:1 \/ 기준 4\.5:1\)$/);
  assert.doesNotMatch(dark.failure_summary, /글자색을 바꾼다면/);

  // 조작 대상 크기: 공식 번역이 없던 규칙도 한국어로 나온다
  const targets = nodesOf(korean, 'target-size');
  assert.ok(targets.length >= 2, '붙어 있는 작은 버튼 둘');
  assert.equal(targets[0].fix_hint.kind, 'target-size');
  assert.deepEqual(
    [targets[0].fix_hint.size.width, targets[0].fix_hint.size.height, targets[0].fix_hint.size.short_width],
    [10, 10, 14],
  );
  assert.match(targets[0].failure_summary, /조작 대상의 크기가 부족합니다/);
  assert.match(targets[0].failure_summary, /\n\n개선 안내\n• 크기를 키운다면: 현재 10px × 10px → 최소 24px × 24px \(가로 14px, 세로 14px 더 필요\)/);

  // 계산할 값이 없는 규칙은 한국어 설명만 있고 fix_hint는 null이다
  const image = nodesOf(korean, 'image-alt')[0];
  assert.ok(image);
  assert.equal(image.fix_hint, null);
  assert.match(image.failure_summary, /alt 어트리뷰트가 없습니다/);
  assert.doesNotMatch(image.failure_summary, /개선 안내/);

  // 같은 페이지를 영어로 돌려도 점수와 위반 규칙·개수는 달라지지 않는다
  const english = await scan({ AXE_LOCALE: 'en' });
  assert.deepEqual(summary(english), summary(korean));
  assert.match(nodesOf(english, 'image-alt')[0].failure_summary, /^Fix any of the following:/);
});
