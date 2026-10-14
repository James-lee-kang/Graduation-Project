'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const { AxeBuilder } = require('@axe-core/playwright');
const axeCore = require('axe-core');
const { chromium } = require('playwright');

const {
  SUPPLEMENT_PATH,
  knownIds,
  koreanAxeSource,
  locateAxeCoreDir,
  mergeLocale,
  resetAxeLocaleState,
} = require('../axe-locale');
const { AXE_OPTIONS } = require('../run');

const HANGUL = /[가-힣]/;
const supplement = JSON.parse(fs.readFileSync(SUPPLEMENT_PATH, 'utf-8'));

async function withPage(callback) {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await (await browser.newContext({ locale: 'ko-KR' })).newPage();
    return await callback(page);
  } finally {
    await browser.close();
  }
}

test('보충 번역은 공식 번역이 있는 키를 덮어쓰지 않고 빠진 키만 채운다', () => {
  const base = { lang: 'ko', rules: { a: { help: '공식 도움말' } }, checks: { c1: { pass: '공식 통과' } } };
  const extra = {
    rules: { a: { help: '보충 도움말' }, b: { help: '보충 B' } },
    checks: { c1: { pass: '보충 통과' }, c2: { pass: '보충 C2' } },
  };
  const merged = mergeLocale(base, extra);
  assert.equal(merged.lang, 'ko');
  assert.equal(merged.rules.a.help, '공식 도움말');
  assert.equal(merged.rules.b.help, '보충 B');
  assert.equal(merged.checks.c1.pass, '공식 통과');
  assert.equal(merged.checks.c2.pass, '보충 C2');
});

test('설치된 axe가 모르는 규칙·체크는 보충 번역에서 뺀다 (axe는 모르는 ID가 있으면 설정을 거부한다)', () => {
  const base = { lang: 'ko', rules: {}, checks: {} };
  const extra = {
    rules: { known: { help: 'x' }, gone: { help: 'y' } },
    checks: { known: { pass: 'x' }, gone: { pass: 'y' } },
  };
  const merged = mergeLocale(base, extra, { rules: new Set(['known']), checks: new Set(['known']) });
  assert.deepEqual(Object.keys(merged.rules), ['known']);
  assert.deepEqual(Object.keys(merged.checks), ['known']);

  // 실제 axe로 확인: 모르는 ID가 들어간 locale은 거부된다
  assert.throws(() => axeCore.configure({ locale: { lang: 'ko', rules: { 'no-such-rule': { help: 'x', description: 'y' } }, checks: {} } }),
    /unknown rule/);
  const ids = knownIds(axeCore);
  assert.ok(ids.rules.has('image-alt') && ids.checks.has('color-contrast'));
});

test('보충 번역의 모든 규칙·체크가 설치된 axe에 실제로 있다 (오타 방지)', () => {
  const ids = knownIds(axeCore);
  for (const id of Object.keys(supplement.rules)) assert.ok(ids.rules.has(id), `규칙 ${id}`);
  for (const id of Object.keys(supplement.checks)) assert.ok(ids.checks.has(id), `체크 ${id}`);
});

test('AXE_LOCALE=en·off이면 한국어를 끄고 axe 기본 소스를 쓰게 한다', () => {
  assert.equal(koreanAxeSource({ env: { AXE_LOCALE: 'en' } }), undefined);
  assert.equal(koreanAxeSource({ env: { AXE_LOCALE: ' OFF ' } }), undefined);
  assert.equal(typeof koreanAxeSource({ env: {} }), 'string');
  assert.equal(typeof koreanAxeSource({ env: { AXE_LOCALE: 'ko' } }), 'string');
});

test('한국어 소스는 axe 소스 뒤에 locale 설정을 붙인 것이고, 한 번 만든 것을 다시 쓴다', () => {
  resetAxeLocaleState();
  const source = koreanAxeSource({ env: {} });
  assert.ok(source.startsWith(axeCore.source), 'AxeBuilder 기본 소스와 같은 axe로 시작');
  assert.match(source.slice(axeCore.source.length), /^;axe\.configure\(\{locale:\{"lang":"ko"/);
  assert.match(source, /다음 중 하나를 해결하세요/);
  assert.match(source, /조작 대상\(터치·클릭 대상\)/, '보충 번역이 들어 있다');
  assert.equal(koreanAxeSource({ env: {} }), source);
  assert.ok(locateAxeCoreDir());
});

test('axe-core를 읽지 못하면 영어로 돌아가고 경고는 한 번만 낸다', () => {
  resetAxeLocaleState();
  const warnings = [];
  const warn = message => warnings.push(message);
  assert.equal(koreanAxeSource({ env: {}, axeDir: '/no/such/axe-core', warn }), undefined);
  assert.equal(koreanAxeSource({ env: {}, axeDir: '/no/such/axe-core', warn }), undefined);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /영어 메시지로 검사합니다/);
  resetAxeLocaleState();
});

test('검사 범위의 모든 규칙·체크가 한국어로 나온다 (axe 번역 + 보충 번역)', async t => {
  const report = await withPage(async page => {
    await page.setContent('<html><body></body></html>');
    await page.evaluate(koreanAxeSource({ env: {} }));
    return page.evaluate(({ tags, extraRules }) => {
      const audit = axe._audit;
      const inScope = audit.rules.filter(rule => rule.tags.some(tag => tags.includes(tag)) || extraRules.includes(rule.id));
      const leaves = message => (typeof message === 'string'
        ? [message]
        : message && typeof message === 'object' ? Object.values(message).flatMap(leaves) : []);
      const hangul = /[가-힣]/;
      const result = { rules: inScope.length, checks: 0, missingRules: [], missingFail: [], untranslatedOther: {} };
      const seen = new Set();
      for (const rule of inScope) {
        const text = audit.data.rules[rule.id];
        if (!text || !hangul.test(text.help) || !hangul.test(text.description)) result.missingRules.push(rule.id);
        for (const group of ['any', 'all', 'none']) {
          for (const check of rule[group] || []) {
            const id = typeof check === 'string' ? check : check.id;
            if (seen.has(id)) continue;
            seen.add(id);
            const messages = audit.data.checks[id].messages;
            // 위반 노드의 failure_summary에 실리는 것은 fail 문구다. 통과 또는 보류만 돌려주는
            // 체크(exists, caption 등)는 fail 문구가 아예 없으므로 건너뛴다.
            if (messages.fail !== undefined) {
              const fail = leaves(messages.fail);
              if (fail.length === 0 || !fail.every(line => hangul.test(line))) result.missingFail.push(id);
            }
            const others = leaves(messages.pass).concat(leaves(messages.incomplete)).filter(line => !hangul.test(line));
            if (others.length) result.untranslatedOther[id] = others;
          }
        }
      }
      result.checks = seen.size;
      return result;
    }, { tags: AXE_OPTIONS.runOnly.values, extraRules: Object.keys(AXE_OPTIONS.rules) });
  });

  assert.ok(report.rules >= 70 && report.checks >= 83, `범위 확인 (규칙 ${report.rules}, 체크 ${report.checks})`);
  assert.deepEqual(report.missingRules, [], 'axe를 올린 뒤 이 줄이 실패하면 새 규칙을 locales/ko-supplement.json에 추가한다');
  assert.deepEqual(report.missingFail, [], 'axe를 올린 뒤 이 줄이 실패하면 새 체크를 locales/ko-supplement.json에 추가한다');
  // pass·incomplete 문구는 결과 JSON으로 나가지 않는다(보류 항목은 API에 싣지 않는다). 영어가 남아 있어도
  // 실패시키지 않고 무엇이 남았는지만 기록한다.
  const leftovers = Object.keys(report.untranslatedOther);
  t.diagnostic(`pass·incomplete 문구에 영어가 남은 체크: ${leftovers.join(', ') || '없음'}`);
});

test('보충 번역의 자리표시자(${data.xxx})와 문구 구조가 영어 원문과 같다', async () => {
  const english = await withPage(async page => {
    await page.setContent('<html><body></body></html>');
    await page.evaluate(axeCore.source);   // 한국어 설정을 붙이지 않은 기본 소스
    return page.evaluate(ids => Object.fromEntries(ids.map(id => [id, axe._audit.data.checks[id].messages])),
      Object.keys(supplement.checks));
  });

  const placeholders = text => [...String(text).matchAll(/\$\{[^}]+\}/g)].map(match => match[0]).sort();
  const compare = (korean, source, where) => {
    if (typeof source === 'string') {
      assert.equal(typeof korean, 'string', `${where}: 문자열이어야 함`);
      assert.deepEqual(placeholders(korean), placeholders(source), `${where}: 자리표시자`);
      assert.match(korean, HANGUL, `${where}: 한국어`);
      return;
    }
    assert.equal(typeof korean, 'object', `${where}: 객체여야 함`);
    assert.deepEqual(Object.keys(korean).sort(), Object.keys(source).sort(), `${where}: 문구 종류`);
    for (const key of Object.keys(source)) compare(korean[key], source[key], `${where}.${key}`);
  };
  for (const [id, messages] of Object.entries(supplement.checks)) compare(messages, english[id], `checks.${id}`);
});

test('실제 검사: 위반 설명이 한국어로 나오고, 영어로 돌려도 위반 규칙과 개수가 같다', async () => {
  // target-size는 "크기가 24px 이상이거나 이웃과 24px 간격" 중 하나만 지키면 통과한다.
  // 위반이 나오려면 작은 대상이 서로 바짝 붙어 있어야 한다.
  const html = `<!doctype html><html><head><title>t</title></head><body><main>
    <img src="x.png">
    <button id="t1" aria-label="이전" style="width:10px;height:10px;padding:0;border:1px solid #000"></button><button id="t2" aria-label="다음" style="width:10px;height:10px;padding:0;border:1px solid #000"></button>
  </main></body></html>`;
  const scan = async (page, axeSource) => {
    const results = await new AxeBuilder({ page, axeSource }).options(AXE_OPTIONS).analyze();
    return results.violations;
  };

  await withPage(async page => {
    await page.setContent(html);
    const korean = await scan(page, koreanAxeSource({ env: {} }));
    const english = await scan(page, undefined);

    assert.deepEqual(
      korean.map(rule => [rule.id, rule.nodes.length]),
      english.map(rule => [rule.id, rule.nodes.length]),
      '언어를 바꿔도 위반 규칙·노드 수는 같아야 한다',
    );
    const rule = id => korean.find(violation => violation.id === id);

    assert.equal(rule('image-alt').help, '이미지는 반드시 대체텍스트를 가져야 합니다.');
    assert.match(rule('image-alt').nodes[0].failureSummary, /^다음 중 하나를 해결하세요:/);
    assert.match(rule('image-alt').nodes[0].failureSummary, /alt 어트리뷰트가 없습니다/);

    // axe 공식 번역에 없던 규칙은 보충 번역으로 나온다
    const targetSize = rule('target-size');
    assert.ok(targetSize, `target-size 위반이 있어야 한다 (실제: ${korean.map(violation => violation.id).join(', ')})`);
    assert.match(targetSize.help, /조작 대상은 24px 이상/);
    assert.match(targetSize.nodes[0].failureSummary, /조작 대상의 크기가 부족합니다 \(10px × 10px, 최소 24px × 24px 필요\)/);
    assert.match(targetSize.nodes[0].failureSummary, /안전하게 클릭할 수 있는 영역의 지름이 \d+px/);
    assert.doesNotMatch(targetSize.nodes[0].failureSummary, /Target has insufficient/);
  });
});
