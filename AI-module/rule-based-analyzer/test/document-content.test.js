'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { DocumentContentUnavailableError, run } = require('../run');

const pages = {
  // The saved HTML in the reported failure had only head metadata.
  '/head-only': '<!doctype html><html lang="ko"><head><title>제목만 있는 문서</title><meta name="description" content="설정"></head></html>',
  '/late-body': `<!doctype html><html lang="ko"><head><title>늦게 채워지는 본문</title></head><body>
    <script>setTimeout(() => {
      document.body.insertAdjacentHTML('beforeend', '<main><h1>늦게 도착한 본문</h1><p>본문 내용이 스크립트로 채워졌습니다.</p></main>');
    }, 1200);</script></body></html>`,
  '/image-only': `<!doctype html><html lang="ko"><head><title>이미지 페이지</title></head><body>
    <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" width="120" height="80"></body></html>`,
};

async function withServer(callback) {
  const server = http.createServer((request, response) => {
    const html = pages[request.url];
    response.writeHead(html ? 200 : 404, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end(html ?? 'not found');
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'document-content-test-'));
  try {
    await callback(`http://127.0.0.1:${server.address().port}`, directory);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));

test('does not score a document whose body never arrived', async () => {
  await withServer(async (origin, directory) => {
    const output = path.join(directory, 'result.json');
    await assert.rejects(
      run(`${origin}/head-only`, output, { settleMs: 0, contentGraceMs: 300 }),
      (error) => error instanceof DocumentContentUnavailableError,
    );
    const marker = readJson(path.join(directory, 'result_api.json'));
    assert.equal(marker.metadata.url, `${origin}/head-only`);
    assert.deepEqual(marker.metadata.document_health, {
      status: 'EMPTY', has_body: true, visible_text_length: 0, visible_content_count: 0,
    });
    assert.equal(marker.score, undefined, 'the marker must not carry a score');
    assert.equal(fs.existsSync(output), false);
    assert.equal(fs.existsSync(path.join(directory, 'result.html')), false);
  });
});

test('waits for a body that streams in after load before scanning', async () => {
  await withServer(async (origin, directory) => {
    const output = path.join(directory, 'result.json');
    await run(`${origin}/late-body`, output, { settleMs: 0, contentGraceMs: 5000 });
    const api = readJson(path.join(directory, 'result_api.json'));
    assert.equal(api.metadata.document_health.status, 'MEANINGFUL');
    assert.ok(api.metadata.document_health.visible_text_length >= 20);
    assert.equal(typeof api.score.score, 'number');
    assert.match(fs.readFileSync(path.join(directory, 'result.html'), 'utf8'), /늦게 도착한 본문/);
  });
});

test('treats visible media without text as analyzable content', async () => {
  await withServer(async (origin, directory) => {
    const output = path.join(directory, 'result.json');
    await run(`${origin}/image-only`, output, { settleMs: 0, contentGraceMs: 0 });
    const api = readJson(path.join(directory, 'result_api.json'));
    assert.equal(api.metadata.document_health.status, 'MEANINGFUL');
    assert.equal(api.metadata.document_health.visible_content_count, 1);
    // The unlabeled image is still reported as a violation.
    assert.ok(api.violations.some((violation) => violation.kwcag_id === '5.1.1'));
  });
});
