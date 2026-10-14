'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { chromium } = require('playwright');

const {
  AMBIGUOUS_LINK_RULE_ID,
  NEW_WINDOW_RULE_ID,
  appendLinkViolations,
  auditLinks,
} = require('../link-audit');
const { run } = require('../run');

const IMAGE = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';
const SR_ONLY = 'position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)';

const CASES = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>링크 검사</title></head><body><main>
  <h1>시청</h1>
  <nav>
    <a id="nw-plain" href="https://www.bokjiro.go.kr" target="_blank">복지로</a>
    <a id="nw-title" href="https://example.org" target="_blank" title="새 창 열림">국민신문고</a>
    <a id="nw-title-short" href="https://example.org" target="_blank" title="창열림">블로그</a>
    <a id="nw-sronly" href="https://example.org" target="_blank">정부24<span style="${SR_ONLY}">(새창)</span></a>
    <a id="nw-alt" href="https://example.org" target="_blank"><img src="${IMAGE}" alt="학교 알리미 새창" width="20" height="20"></a>
    <a id="nw-frame" href="/inner" target="innerFrame">내부 화면</a>
    <a id="nw-named" href="/popup" target="popup">우편번호 찾기</a>
    <a id="nw-onclick" href="#" onclick="window.open('/print'); return false;">인쇄하기</a>
    <a id="nw-hidden" href="https://example.org" target="_blank" style="display:none">모바일 메뉴</a>
    <a id="nw-empty" href="https://example.org" target="_blank"><img src="${IMAGE}" alt="" width="20" height="20"></a>
    <a id="self" href="/about" target="_self">기관 소개</a>
  </nav>
  <iframe name="innerFrame" title="내부" width="10" height="10"></iframe>
  <section><h2>공지사항</h2><ul><li>추석 연휴 민원실 운영 안내</li></ul>
    <a id="am-notice" href="/notice">더보기</a></section>
  <section><h2>자주 찾는 서비스</h2>
    <a id="am-arialabel" href="/svc" aria-label="자주 찾는 서비스 더보기">더보기</a>
    <a id="am-title" href="/svc" title="자주 찾는 서비스 더보기">더보기</a>
    <a id="am-sronly" href="/svc">더보기<span style="${SR_ONLY}">자주 찾는 서비스</span></a>
    <a id="am-plus" href="/svc">+</a>
    <a id="am-more" href="/svc">MORE +</a>
    <a id="am-newwin" href="/svc" target="_blank" title="새창">더보기</a>
    <a id="am-titleonly" href="/svc" title="바로가기"><img src="${IMAGE}" alt="" width="20" height="20"></a>
  </section>
  <a id="skip" href="#main">본문 바로가기</a>
  <div id="popup"><a id="pop-more" href="/event">자세히 보기</a></div>
</main></body></html>`;

async function withPage(html, callback) {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.setContent(html);
    return await callback(page);
  } finally {
    await browser.close();
  }
}

const idsOf = (rules, ruleId) => (rules.find((rule) => rule.id === ruleId)?.nodes || [])
  .map((node) => (node.html.match(/id="([^"]+)"/) || [])[1]);

test('flags new-window links without a notice and generic link texts', async () => {
  await withPage(CASES, async (page) => {
    const rules = await auditLinks(page);

    assert.deepEqual(idsOf(rules, NEW_WINDOW_RULE_ID).sort(),
      ['nw-named', 'nw-onclick', 'nw-plain'],
      'title, screen-reader-only text and image alt all count as a notice; frames, hidden and nameless links are skipped');
    assert.deepEqual(idsOf(rules, AMBIGUOUS_LINK_RULE_ID).sort(),
      ['am-more', 'am-newwin', 'am-notice', 'am-plus', 'am-titleonly', 'pop-more'],
      'aria-label, a target-naming title or hidden text fix it; "새창" alone does not');

    const notice = rules.find((rule) => rule.id === AMBIGUOUS_LINK_RULE_ID).nodes
      .find((node) => node.html.includes('am-notice'));
    assert.match(notice.failureSummary, /"공지사항 더보기"/, 'suggests the nearest heading');
    for (const rule of rules) {
      assert.ok(rule.help && rule.description && rule.tags.includes('uniaccess'));
      for (const node of rule.nodes) {
        const selected = await page.evaluate((selector) => document.querySelector(selector)?.id, node.target[0]);
        assert.equal(selected, (node.html.match(/id="([^"]+)"/) || [])[1], `${node.target[0]} selects the link`);
      }
    }
  });
});

test('limits the check to a scope such as the open popups', async () => {
  await withPage(CASES, async (page) => {
    const rules = await auditLinks(page, { scope: '#popup' });
    assert.deepEqual(rules.flatMap((rule) => rule.nodes.map((node) => node.target[0])), ['#pop-more']);
  });
});

test('appends to axe results, merging into an existing rule entry', () => {
  const axe = { violations: [{ id: AMBIGUOUS_LINK_RULE_ID, nodes: [{ target: ['#a'] }] }] };
  appendLinkViolations(axe, [
    { id: AMBIGUOUS_LINK_RULE_ID, nodes: [{ target: ['#b'] }] },
    { id: NEW_WINDOW_RULE_ID, nodes: [{ target: ['#c'] }] },
  ]);
  assert.deepEqual(axe.violations.map((rule) => [rule.id, rule.nodes.length]),
    [[AMBIGUOUS_LINK_RULE_ID, 2], [NEW_WINDOW_RULE_ID, 1]]);
  assert.equal(appendLinkViolations(null, []), null);
});

const SITE = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>테스트 시청</title></head><body>
  <main><h1>시정 소식</h1>
    <p>시청 홈페이지 본문입니다. 민원 신청, 공지사항, 자료실 서비스를 안내합니다.</p>
    <section><h2>공지사항</h2><a id="main-more" href="/notice">더보기</a></section>
    <a id="main-blank" href="https://www.bokjiro.go.kr" target="_blank">복지로</a>
  </main>
  <div id="layerPopup" style="position:fixed;top:60px;left:200px;width:800px;height:500px;background:#fff;z-index:1000">
    <p>[공지] 추석 연휴 민원실 운영 안내</p>
    <a href="/event" id="pop-more">자세히</a>
    <a href="#" id="pop-today">오늘 하루 보지 않기</a></div>
</body></html>`;

test('maps the rules to KWCAG 6.4.3 and 7.2.1, scores them, and keeps popup links outside the score', async () => {
  const server = http.createServer((request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end(SITE);
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'link-audit-test-'));
  try {
    await run(`http://127.0.0.1:${server.address().port}/`, path.join(directory, 'result.json'),
      { settleMs: 0, contentGraceMs: 0, compareLoad: false });
    const api = JSON.parse(fs.readFileSync(path.join(directory, 'result_api.json'), 'utf8'));

    const item = (id) => api.violations.find((violation) => violation.kwcag_id === id);
    const ruleNodes = (violation, ruleId) => violation?.rules.find((rule) => rule.axe_rule_id === ruleId)?.nodes || [];
    assert.deepEqual(ruleNodes(item('6.4.3'), AMBIGUOUS_LINK_RULE_ID).map((node) => node.selector), ['#main-more']);
    assert.match(ruleNodes(item('6.4.3'), AMBIGUOUS_LINK_RULE_ID)[0].failure_summary, /공지사항 더보기/);
    assert.equal(ruleNodes(item('7.2.1'), NEW_WINDOW_RULE_ID).length, 1);
    assert.equal(api.score.items['7.2.1'].deduction, 2, 'major × medium = 2 points per link');
    assert.equal(api.score.items['6.4.3'].deduction, 2);

    const popup = api.excluded_violations.find((group) => group.reason === 'POPUP');
    assert.ok(popup, 'the popup link is reported under POPUP');
    assert.deepEqual(popup.violations.flatMap((violation) => violation.rules)
      .filter((rule) => rule.axe_rule_id === AMBIGUOUS_LINK_RULE_ID)
      .flatMap((rule) => rule.nodes.map((node) => (node.html.match(/id="([^"]+)"/) || [])[1])), ['pop-more']);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
