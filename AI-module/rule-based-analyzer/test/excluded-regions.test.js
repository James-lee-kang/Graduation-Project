'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { run } = require('../run');

const IMAGE = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';

// Every request serves different headlines and a carousel that starts on a
// different slide, like a portal home page.
function portalPage(load) {
  const headlines = [1, 2, 3].map((item) => `<li><a href="/news/${load}-${item}">오늘의 뉴스 ${load}-${item} 제목입니다</a></li>`).join('');
  const slides = load % 2 ? ['첫 번째 캠페인', '두 번째 캠페인'] : ['두 번째 캠페인', '첫 번째 캠페인'];
  return `<!doctype html><html lang="ko"><head><title>포털</title>
    <style>.swiper{width:400px;overflow:hidden}.swiper-wrapper{display:flex}.swiper-slide{flex:0 0 400px;height:60px}</style></head>
    <body>
      <header><img id="logo" src="${IMAGE}" width="120" height="40"><h1>포털 서비스</h1></header>
      <main>
        <section id="news"><h2>뉴스</h2><ul>${headlines}</ul><img id="news-photo" src="${IMAGE}" width="80" height="60"></section>
        <div id="ad-area"><ins class="adsbygoogle" style="display:block;width:300px;height:100px">
          <img id="ad-image" src="${IMAGE}" width="300" height="100"></ins></div>
        <div class="swiper"><div class="swiper-wrapper">
          ${slides.map((text) => `<div class="swiper-slide"><p>${text}</p><img src="${IMAGE}" width="40" height="40"></div>`).join('')}
        </div></div>
        <p>변하지 않는 서비스 안내 문구입니다. 이 영역은 계속 검사합니다.</p>
        <div style="height:2400px">A portal page is much taller than one widget.</div>
      </main>
    </body></html>`;
}

async function analyzePortal(options = {}) {
  let load = 0;
  const server = http.createServer((request, response) => {
    load += 1;
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end(portalPage(load));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'excluded-regions-test-'));
  try {
    await run(`http://127.0.0.1:${server.address().port}/`, path.join(directory, 'result.json'),
      { settleMs: 0, contentGraceMs: 0, ...options });
    return {
      api: JSON.parse(fs.readFileSync(path.join(directory, 'result_api.json'), 'utf8')),
      html: fs.readFileSync(path.join(directory, 'result.html'), 'utf8'),
    };
  } finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

const imageAltSelectors = (violations) => violations
  .filter((violation) => violation.kwcag_id === '5.1.1')
  .flatMap((violation) => violation.rules.flatMap((rule) => rule.nodes.map((node) => node.selector)));

test('excludes ads and content that changed between loads, and keeps stable content and carousels', async () => {
  const { api, html } = await analyzePortal();

  const scored = imageAltSelectors(api.violations);
  assert.ok(scored.some((selector) => selector.includes('logo')), 'the stable banner is still checked');
  assert.ok(scored.every((selector) => !/news-photo|ad-image/.test(selector)), 'excluded images are not scored');
  assert.equal(scored.filter((selector) => /swiper|slide/.test(selector)).length >= 1, true,
    'carousel slides that rotate between loads stay in the analysis');

  const byReason = Object.fromEntries(api.excluded_violations.map((group) => [group.reason, group]));
  assert.deepEqual(Object.keys(byReason).sort(), ['AD', 'DYNAMIC']);
  assert.ok(imageAltSelectors(byReason.AD.violations).some((selector) => selector.includes('ad-image')));
  assert.ok(imageAltSelectors(byReason.DYNAMIC.violations).some((selector) => selector.includes('news-photo')));

  const reasons = api.metadata.excluded_regions.map((region) => region.reason);
  assert.ok(reasons.includes('AD') && reasons.includes('DYNAMIC'));
  for (const region of api.metadata.excluded_regions) {
    assert.ok(region.width > 0 && region.height > 0);
  }
  // The text analyzer reads these marks from the DOM snapshot.
  assert.match(html, /data-ua-excluded-region="DYNAMIC"/);
  assert.match(html, /data-ua-excluded-region="AD"/);
  assert.doesNotMatch(html, /swiper-slide"[^>]*data-ua-excluded-region/);
});

test('still excludes ads when the comparison load is disabled', async () => {
  const { api } = await analyzePortal({ compareLoad: false });
  assert.deepEqual(api.excluded_violations.map((group) => group.reason), ['AD']);
  assert.ok(imageAltSelectors(api.violations).some((selector) => selector.includes('news-photo')),
    'without a comparison load nothing is treated as dynamic');
});
