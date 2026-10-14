/**
 * ============================================================
 *  axe-locale.js (2026-10-13)
 *  axe-core가 한국어로 말하게 하는 소스 문자열 만들기
 * ============================================================
 *
 * [왜 필요한가]
 *   axe-core는 기본적으로 영어로 설명한다("Elements must have sufficient color
 *   contrast", "Fix any of the following: ..."). 이 문장은 failure_summary로
 *   백엔드 이슈 메시지에 그대로 저장된다. 사용자(국내 공공기관 담당자)가 읽는
 *   수정 안내이므로 한국어로 나와야 한다.
 *
 * [방법]
 *   axe-core 패키지에 이미 한국어 번역(locales/ko.json, 규칙 97개)이 들어 있다.
 *   @axe-core/playwright의 AxeBuilder는 configure()를 노출하지 않지만, 생성자에
 *   axeSource를 받는다(실제로 브라우저에 주입되는 스크립트). axe 소스 뒤에
 *   `axe.configure({ locale })`를 붙인 문자열을 넘기면, 페이지와 모든 iframe에서
 *   같은 한국어 설정으로 돌아간다.
 *
 * [ko.json에 없는 것]
 *   우리 검사 범위(wcag2a~wcag22aa + landmark-one-main) 70개 규칙 중 6개, 그 규칙이
 *   쓰는 체크 83개 중 10개는 ko.json에 번역이 없다(target-size, summary-name,
 *   aria-prohibited-attr, aria-conditional-attr, aria-deprecated-role,
 *   aria-braille-equivalent 등, axe-core 4.11.4 기준). locales/ko-supplement.json이
 *   이 빈칸만 채운다. ko.json에 이미 있는 키는 건드리지 않는다(공식 번역 우선).
 *
 * [안전장치]
 *   - axe-core를 찾지 못하거나 번역 파일을 읽지 못하면 영어 기본값으로 돌아가고
 *     (undefined 반환) 경고를 한 번만 찍는다. 검사 자체는 멈추지 않는다.
 *   - axe는 모르는 규칙·체크 ID가 locale에 있으면 설정 전체를 거부하므로, 보충 번역은
 *     설치된 axe가 아는 ID만 쓴다(axe-core 버전이 바뀌어도 검사가 깨지지 않는다).
 *   - 환경변수 AXE_LOCALE=en (또는 off)이면 한국어를 끄고 axe 기본(영어)을 쓴다.
 *     영어 axe 문서와 문구를 맞춰 보고 싶을 때만 쓴다.
 *   - axe-core를 package.json에 따로 추가하지 않았다. @axe-core/playwright가 이미
 *     의존하고 npm이 최상위에 올려 두므로 그대로 쓰고, 안 보이면 @axe-core/playwright
 *     옆에서 찾는다. package-lock과 어긋나 npm ci가 깨지는 일을 피하려는 선택이다.
 *
 * [데이터 흐름 영향]
 *   바뀌는 것은 문장뿐이다. 규칙 ID·태그·노드·점수 계산은 같다. 대시보드에는
 *   help(제목 줄)와 failure_summary가 한국어로 보이고, 대시보드가 규칙 ID로 따로
 *   설명을 붙이는 10개 규칙(link-name, image-alt, list, listitem, button-name,
 *   label, color-contrast, document-title, html-has-lang, html-lang-valid)은
 *   예전처럼 대시보드 문구가 우선한다.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const SUPPLEMENT_PATH = path.join(__dirname, 'locales', 'ko-supplement.json');

// 환경변수로 한국어를 끌 때 쓰는 값(대소문자 무시).
const DISABLED_VALUES = new Set(['en', 'off', 'none', 'default']);

// 같은 실행에서 한국어 소스는 한 번만 만든다(1MB가 넘는 문자열이고, 캐러셀
// 슬라이드마다 스캔이 반복된다). 실패 경고도 한 번만 찍는다.
let cachedSource = null;
let warnedOnce = false;


/**
 * axe-core 패키지 폴더를 찾는다.
 *   1) 이 폴더에서 보이는 axe-core (npm이 최상위로 올려 둔 사본)
 *   2) 안 보이면 @axe-core/playwright가 쓰는 사본
 * 못 찾으면 null.
 */
function locateAxeCoreDir() {
  const tries = [
    () => require.resolve('axe-core'),
    () => require.resolve('axe-core', {
      paths: [path.dirname(require.resolve('@axe-core/playwright'))],
    }),
  ];
  for (const attempt of tries) {
    try {
      return path.dirname(attempt());
    } catch {
      // 다음 후보로
    }
  }
  return null;
}


/** entries 중 키가 allowed에 있는 것만 남긴다. */
function pickKnown(entries, allowed) {
  return Object.fromEntries(Object.entries(entries || {}).filter(([id]) => allowed.has(id)));
}


/**
 * 공식 ko.json 위에 보충 번역을 얹는다. 공식 번역에 있는 키는 그대로 두고 빠진
 * 규칙·체크만 채운다(공식 번역이 나중에 늘어도 보충분이 덮어쓰지 않는다).
 *
 * axe는 자기가 모르는 규칙·체크 ID가 locale에 있으면 "Locale provided for unknown
 * rule/check" 오류로 설정 전체를 거부한다. axe-core를 올리거나 내려서 보충 번역의
 * 규칙이 사라져도 검사가 깨지지 않도록, known이 주어지면 axe가 아는 ID의 보충분만 쓴다.
 *
 * @param {Object} base        axe-core의 locales/ko.json
 * @param {Object} supplement  locales/ko-supplement.json
 * @param {{rules: Set<string>, checks: Set<string>}|null} [known]  설치된 axe가 아는 규칙·체크 ID
 * @returns {Object} axe.configure({ locale })에 넘길 객체
 */
function mergeLocale(base, supplement, known = null) {
  const extraRules = known ? pickKnown(supplement.rules, known.rules) : (supplement.rules || {});
  const extraChecks = known ? pickKnown(supplement.checks, known.checks) : (supplement.checks || {});
  return {
    ...base,
    rules: { ...extraRules, ...(base.rules || {}) },
    checks: { ...extraChecks, ...(base.checks || {}) },
  };
}


/**
 * 설치된 axe가 아는 규칙·체크 ID. axe._audit은 내부 속성이라 읽지 못하면 null을
 * 돌려주고(걸러내지 않고 보충분 전체를 쓴다), 부른 쪽에서 오류로 알게 된다.
 */
function knownIds(axe) {
  try {
    return {
      rules: new Set(axe.getRules().map(rule => rule.ruleId)),
      checks: new Set(Object.keys(axe._audit.checks)),
    };
  } catch {
    return null;
  }
}


/**
 * 한국어 locale 객체를 만든다.
 * @param {string} axeDir  axe-core 패키지 폴더 (locales/ko.json이 있는 곳의 상위)
 * @param {Object} [axe]   같은 폴더의 axe-core 모듈 (아는 규칙·체크 ID를 읽는 데 쓴다)
 */
function buildKoreanLocale(axeDir, axe = null) {
  const base = JSON.parse(fs.readFileSync(path.join(axeDir, 'locales', 'ko.json'), 'utf-8'));
  const supplement = JSON.parse(fs.readFileSync(SUPPLEMENT_PATH, 'utf-8'));
  return mergeLocale(base, supplement, axe ? knownIds(axe) : null);
}


/**
 * AxeBuilder({ page, axeSource })에 넘길 한국어 axe 소스를 돌려준다.
 * 한국어를 끄거나 만들 수 없으면 undefined (AxeBuilder가 기본 영어 소스를 쓴다).
 *
 * @param {Object} [options]
 * @param {Object} [options.env]    환경변수 객체 (테스트용, 기본 process.env)
 * @param {string} [options.axeDir] axe-core 폴더 (테스트용, 기본은 자동 탐색)
 * @param {Function} [options.warn] 경고 출력 함수 (테스트용, 기본 console.warn)
 * @returns {string|undefined}
 */
function koreanAxeSource(options = {}) {
  const env = options.env || process.env;
  const warn = options.warn || console.warn;
  const choice = String(env.AXE_LOCALE || 'ko').trim().toLowerCase();
  if (DISABLED_VALUES.has(choice)) return undefined;

  try {
    const axeDir = options.axeDir || locateAxeCoreDir();
    if (!axeDir) throw new Error('axe-core를 찾을 수 없습니다');
    if (cachedSource && cachedSource.axeDir === axeDir) return cachedSource.source;

    // axe.source는 AxeBuilder가 기본으로 주입하는 것과 같은 스크립트다.
    const axe = require(path.join(axeDir, 'axe.js'));
    const locale = buildKoreanLocale(axeDir, axe);
    const source = `${axe.source};axe.configure({locale:${JSON.stringify(locale)}});`;
    cachedSource = { axeDir, source };
    return source;
  } catch (error) {
    if (!warnedOnce) {
      warnedOnce = true;
      warn(`   [axe 한국어] 영어 메시지로 검사합니다: ${error.message}`);
    }
    return undefined;
  }
}


/** 테스트용: 캐시와 경고 기록을 지운다. */
function resetAxeLocaleState() {
  cachedSource = null;
  warnedOnce = false;
}


module.exports = {
  koreanAxeSource,
  buildKoreanLocale,
  knownIds,
  mergeLocale,
  locateAxeCoreDir,
  resetAxeLocaleState,
  SUPPLEMENT_PATH,
};
