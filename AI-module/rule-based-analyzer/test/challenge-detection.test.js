'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { chromium } = require('playwright');

const {
  challengeSignals,
  detectCrossOriginBotChallenge,
  isSecurityGateUrl,
  usableInitialHtml,
} = require('../run');

test('routes only an active same-document BotManager shell to the initial HTML fallback', async () => {
  const url = 'about:blank';
  const initialSnapshot = {
    url,
    status: 200,
    contentType: 'text/html; charset=utf-8',
    html: `<!doctype html><html lang="ko"><head><title>실제 초기 페이지</title></head>
      <body><main><h1>대학교 홈페이지</h1><p>사용자에게 제공되는 실제 초기 페이지 본문입니다.</p>
      <nav aria-label="주요 메뉴"><a href="/admission">입학 안내</a></nav></main></body></html>`,
  };
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });

  try {
    await page.setContent(`<!doctype html><html><head><style>
      #bm-wait-background, #loading-overlay { position: fixed; inset: 0; }
    </style></head><body>
      <div id="bm-wait-background"></div>
      <div id="loading-overlay" role="status"></div>
    </body></html>`);

    const activeChallenge = await detectCrossOriginBotChallenge(page, url);
    assert.deepEqual(activeChallenge.signals, ['BOT_MANAGER_WAIT_OVERLAY']);
    assert.equal(activeChallenge.detected, true);
    assert.equal(usableInitialHtml(initialSnapshot), true);

    await page.setContent(`<!doctype html><html><head><style>
      #bm-wait-background, #loading-overlay { display: none; }
    </style></head><body>
      <main><h1>정상 페이지</h1><p>사용자에게 보이는 실제 본문입니다.</p></main>
      <div id="bm-wait-background"></div>
      <div id="loading-overlay" role="status"></div>
    </body></html>`);

    const dormantChallenge = await detectCrossOriginBotChallenge(page, url);
    assert.equal(dormantChallenge.signals.includes('BOT_MANAGER_WAIT_OVERLAY'), false);
    assert.equal(dormantChallenge.detected, false);
  } finally {
    await browser.close();
  }
});

test('does not treat ordinary loading UI or a partial BotManager marker as a challenge', () => {
  const ordinaryLoadingHtml = `<!doctype html><html><body>
    <main>대시보드를 불러오는 중입니다.</main>
    <div id="loading-overlay" role="status">Loading</div>
  </body></html>`;
  const partialMarkerHtml = '<html><body><div id="bm-wait-background"></div></body></html>';

  assert.deepEqual(challengeSignals({ html: ordinaryLoadingHtml }), []);
  assert.deepEqual(challengeSignals({ html: partialMarkerHtml }), []);

  const dormantMarkerPair = `<html><body><main>정상 본문</main>
    <div id="bm-wait-background" hidden></div>
    <div id="loading-overlay" hidden></div></body></html>`;
  assert.deepEqual(challengeSignals({ html: dormantMarkerPair }), []);
});

test('recognises the government MBuster redirect, Cloudflare and vendor markers', () => {
  assert.deepEqual(challengeSignals({ url: 'https://plus.gov.kr/mbuster?returnUrl=%2F' }), ['MBUSTER']);
  assert.deepEqual(challengeSignals({ url: 'https://www.gov.kr/portal/main' }), []);
  assert.deepEqual(challengeSignals({ url: 'https://www.example.go.kr/deny/index.html' }), ['CHALLENGE_URL']);
  assert.deepEqual(challengeSignals({
    title: 'Just a moment...',
    html: '<script>window._cf_chl_opt = {};</script><div id="cf-chl-widget"></div>',
  }), ['CLOUDFLARE']);
  // PerimeterX(px-captcha)·DataDome(captcha-delivery.com) block pages are
  // already covered by the generic CAPTCHA marker.
  assert.deepEqual(challengeSignals({ html: '<div id="px-captcha"></div>' }), ['CAPTCHA']);
  assert.deepEqual(challengeSignals({ html: '<iframe src="https://geo.captcha-delivery.com/captcha/"></iframe>' }), ['CAPTCHA']);
});

test('does not treat vendor tags on an ordinary page as a challenge', () => {
  // Cloudflare injects challenge-platform scripts and DataDome injects its tag
  // on normal pages too; neither alone may route a page to the fallback.
  const ordinary = `<html><head><script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>
    <script src="https://js.datadome.co/tags.js"></script></head><body><main>정상 본문</main></body></html>`;
  assert.deepEqual(challengeSignals({ title: '기관 홈페이지', html: ordinary }), []);
});

test('detects a cross-origin redirect to the MBuster block page', async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await page.route('https://plus.gov.kr/**', (route) => route.fulfill({
      status: 200,
      contentType: 'text/html; charset=utf-8',
      body: '<!doctype html><html lang="ko"><head><title>정부24</title></head><body><p>잠시 후 다시 이용해 주세요.</p></body></html>',
    }));
    await page.goto('https://plus.gov.kr/mbuster?returnUrl=%2F');
    const challenge = await detectCrossOriginBotChallenge(page, 'https://www.gov.kr/');
    assert.equal(challenge.detected, true);
    assert.deepEqual(challenge.signals, ['MBUSTER']);
  } finally {
    await browser.close();
  }
});

test('detects a same-origin MBuster gate (plus.gov.kr → plus.gov.kr/mbuster/Mbuster_T)', async () => {
  // 2026-10-14 동작검증: 같은 사이트 안의 관문이라 출처 비교에 걸리지 않고 95.6점으로 채점됐다.
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await page.route('https://plus.gov.kr/**', (route) => route.fulfill({
      status: 200,
      contentType: 'text/html; charset=utf-8',
      body: '<!doctype html><html lang="ko"><head><title>정부24</title></head><body><p>잠시 후 다시 이용해 주세요.</p></body></html>',
    }));
    await page.goto('https://plus.gov.kr/mbuster/Mbuster_T');
    const challenge = await detectCrossOriginBotChallenge(page, 'https://plus.gov.kr/');
    assert.equal(challenge.detected, true);
    assert.deepEqual(challenge.signals, ['MBUSTER']);
  } finally {
    await browser.close();
  }
});

test('does not treat an ordinary same-origin page as a gate', async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await page.route('https://plus.gov.kr/**', (route) => route.fulfill({
      status: 200,
      contentType: 'text/html; charset=utf-8',
      body: '<!doctype html><html lang="ko"><head><title>정부24</title></head><body><main><h1>민원 서비스</h1></main></body></html>',
    }));
    await page.goto('https://plus.gov.kr/main/index');
    const challenge = await detectCrossOriginBotChallenge(page, 'https://plus.gov.kr/');
    assert.equal(challenge.detected, false);
  } finally {
    await browser.close();
  }
});

test('never replays an initial response that is itself the MBuster gate', () => {
  const gateHtml = `<!doctype html><html lang="ko"><head><title>정부24</title></head>
    <body><p>자동 접근이 감지되어 잠시 후 다시 이용해 주세요. 이 문장은 100자를 넘기기 위한 채움 문장입니다.</p></body></html>`;
  const base = { status: 200, contentType: 'text/html; charset=utf-8', html: gateHtml };
  assert.equal(usableInitialHtml({ ...base, url: 'https://plus.gov.kr/mbuster/Mbuster_T' }), false);
  assert.equal(usableInitialHtml({ ...base, url: 'https://plus.gov.kr/mbuster?returnUrl=%2F' }), false);
  assert.equal(usableInitialHtml({ ...base, url: 'https://plus.gov.kr/' }), true);
  assert.equal(isSecurityGateUrl('https://plus.gov.kr/mbuster/Mbuster_T'), true);
  assert.equal(isSecurityGateUrl('https://plus.gov.kr/mbusterguide'), false);
  assert.equal(isSecurityGateUrl(''), false);
});

// 2026-10-17 재측정: 홍익대는 본문 확인 뒤 axe 검사 도중 다른 출처의 봇 확인 화면으로
// 넘어가 "Execution context was destroyed"로 끝났다(분석 실패, 종료 코드 1).
// 검사 도중 차단 화면으로 바뀐 것은 대상 페이지 아님(BLOCKED, 종료 코드 2)이어야 한다.
test('a page that turns into a cross-origin bot check during the axe scan is BLOCKED, not a failure', async () => {
  const http = require('node:http');
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const { TargetPageUnavailableError, run } = require('../run');

  // 127.0.0.1과 localhost는 출처가 다르다. 본문 페이지는 axe가 주입되는 순간
  // (window.axe가 생기는 순간) 다른 출처의 봇 확인 화면으로 이동한다.
  const server = http.createServer((request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    if (request.url.startsWith('/challenge')) {
      response.end(`<!doctype html><html lang="ko"><head><title>BotManager</title></head><body>
        <div id="bm">stclab botmanager challenge</div></body></html>`);
      return;
    }
    const port = server.address().port;
    response.end(`<!doctype html><html lang="ko"><head><title>대학교</title></head><body>
      <main><h1>대학교 홈페이지</h1><p>입학 안내와 학사 공지를 확인하세요.</p>
      <a href="/notice">공지사항</a></main>
      <script>
        const timer = setInterval(() => {
          if (window.axe) {
            clearInterval(timer);
            location.href = 'http://localhost:${port}/challenge/index.html';
          }
        }, 1);
      </script></body></html>`);
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mid-scan-challenge-'));
  try {
    const origin = `http://127.0.0.1:${server.address().port}`;
    const output = path.join(directory, 'result.json');
    await assert.rejects(
      run(`${origin}/`, output, { settleMs: 0, contentGraceMs: 0, compareLoad: false, carouselAudit: false }),
      (error) => error instanceof TargetPageUnavailableError,
    );
    const marker = JSON.parse(fs.readFileSync(path.join(directory, 'result_api.json'), 'utf8'));
    assert.equal(marker.metadata.url, `${origin}/`);
    assert.equal(marker.metadata.document_health.status, 'BLOCKED');
    assert.equal(marker.score, undefined, 'the marker must not carry a score');
    assert.equal(fs.existsSync(output), false);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

// 반대로 같은 사이트의 평범한 페이지로 넘어간 것은 차단이 아니다. 원래 오류 그대로
// 분석 실패(종료 코드 1)로 남아야 한다.
test('a mid-scan move to an ordinary same-site page stays an analysis failure', async () => {
  const http = require('node:http');
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const { TargetPageUnavailableError, run } = require('../run');

  const server = http.createServer((request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    if (request.url.startsWith('/other')) {
      response.end(`<!doctype html><html lang="ko"><head><title>다른 안내</title></head><body>
        <main><h1>다른 안내 페이지</h1><p>평범한 본문입니다.</p></main></body></html>`);
      return;
    }
    response.end(`<!doctype html><html lang="ko"><head><title>대학교</title></head><body>
      <main><h1>대학교 홈페이지</h1><p>입학 안내와 학사 공지를 확인하세요.</p></main>
      <script>
        const timer = setInterval(() => {
          if (window.axe) { clearInterval(timer); location.href = '/other'; }
        }, 1);
      </script></body></html>`);
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mid-scan-move-'));
  try {
    const output = path.join(directory, 'result.json');
    await assert.rejects(
      run(`http://127.0.0.1:${server.address().port}/`, output,
        { settleMs: 0, contentGraceMs: 0, compareLoad: false, carouselAudit: false }),
      (error) => !(error instanceof TargetPageUnavailableError) && /Execution context was destroyed/.test(error.message),
    );
    assert.equal(fs.existsSync(path.join(directory, 'result_api.json')), false);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
