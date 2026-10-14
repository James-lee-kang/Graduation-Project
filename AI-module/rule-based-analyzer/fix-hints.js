/**
 * ============================================================
 *  fix-hints.js (2026-10-13)
 *  axe가 잰 값으로 "얼마나, 어떻게 고치면 되는지"를 계산하는 노드별 수정 안내
 * ============================================================
 *
 * [왜 필요한가]
 *   axe의 failure_summary는 "무엇이 틀렸는지"를 알려 주지만, 숫자가 걸린 규칙은
 *   "얼마나 고치면 되는지"가 없다. 명도 대비는 "4.47:1이니 부족하다"까지만 알려 주고,
 *   어떤 색으로 바꾸면 되는지는 사용자가 직접 찾아야 한다. 이 파일은 axe가 이미
 *   측정해 둔 값(색, 크기, 간격)만으로 답을 계산해 노드마다 붙인다. 추측하지 않고,
 *   계산에 필요한 값이 없으면 안내를 붙이지 않는다(null).
 *
 * [지원 규칙]
 *   color-contrast : 글자색을 바꾸는 방안과 배경색을 바꾸는 방안 각각의 추천색
 *   target-size    : 조작 대상의 현재 크기·간격과 모자란 만큼
 *
 * [color-contrast 추천색 계산]
 *   CV 모듈(cv-analyzer/contrast_analyzer.py의 suggest_fix)과 같은 방식이다. 같은 두 색을
 *   넣으면 두 모듈이 같은 추천색을 낸다(test/fix-hints.test.js에 같은 값을 고정했다).
 *   - 방향은 상대 휘도로 정한다. 글자가 배경보다 어두우면 글자는 더 어둡게/배경은 더
 *     밝게, 글자가 더 밝으면 그 반대다(다크 테마, 어두운 배너의 흰 글자).
 *   - RGB 세 채널을 같은 만큼씩 움직이며 기준(4.5:1 또는 큰 글자 3:1)에 처음 닿는 색을
 *     고른다. 흰색·검정까지 가도 모자라면 그 끝 색과 meets_target=false를 돌려주고,
 *     이때는 다른 방안(반대쪽 색)을 써야 한다.
 *   - 합격 판정은 항상 원래 값으로 한다. 표시값(new_ratio)만 소수 둘째 자리에서 버린다
 *     (4.4976:1이 4.50:1로 보여 합격처럼 읽히는 것을 막으려는 CV 모듈과 같은 규칙).
 *   - 그림자가 걸린 변형(fgOnShadowColor, shadowOnBgColor)처럼 글자색·배경색 두 값만으로
 *     설명되지 않는 경우는 안내를 만들지 않는다.
 *
 * [어디에 붙는가]
 *   adapter.js의 extractNodeInfo가 노드마다 fixHint를 계산하고, run.js의 toApiFormat이
 *   result_api.json의 노드에 fix_hint(구조화된 값)로 싣는다. 같은 내용을 사람이 읽는
 *   문장으로 failure_summary 끝에 "개선 안내" 단락으로 덧붙인다(appendFixHint).
 *   백엔드는 failure_summary를 이슈 메시지에 그대로 저장하고, 대시보드는 "개선 안내"
 *   단락을 소제목으로 나누어 보여 주는 규칙이 이미 있다. 따라서 이 파일의 문장은
 *   별도 수정 없이 DB와 JSON에 들어간다. (대시보드가 규칙 ID별 문구로 메시지 전체를
 *   바꾸는 color-contrast 등은 화면에 보이려면 대시보드 쪽 수정이 필요하다.)
 */

'use strict';

const HINT_HEADING = '개선 안내';

// 큰 글자 기준 등 axe가 알려 주는 기준값이 없을 때 쓰는 일반 텍스트 기준(KWCAG 5.4.3 AA).
const DEFAULT_REQUIRED_RATIO = 4.5;

const DIRECTION_LABEL = Object.freeze({ darken: '더 어둡게', lighten: '더 밝게' });


// ── 색 계산 (WCAG 2.x 공식, cv-analyzer/contrast_analyzer.py와 같은 식) ──────────

/** '#rrggbb' → [r, g, b], 형식이 다르면 null. axe는 항상 6자리 소문자 hex를 준다. */
function parseHex(hex) {
  const match = /^#?([0-9a-f]{6})$/i.exec(String(hex ?? '').trim());
  if (!match) return null;
  return [0, 2, 4].map(offset => parseInt(match[1].slice(offset, offset + 2), 16));
}

/** [r, g, b] → '#RRGGBB' (CV 모듈과 같은 대문자 표기). */
function toHex(rgb) {
  return `#${rgb.map(channel => channel.toString(16).padStart(2, '0')).join('').toUpperCase()}`;
}

function srgbToLinear(channel) {
  const s = channel / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(rgb) {
  return 0.2126 * srgbToLinear(rgb[0]) + 0.7152 * srgbToLinear(rgb[1]) + 0.0722 * srgbToLinear(rgb[2]);
}

function contrastRatio(colorA, colorB) {
  const a = relativeLuminance(colorA);
  const b = relativeLuminance(colorB);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/**
 * 표시·저장용 명암비: 소수 둘째 자리에서 버린다(반올림하지 않는다).
 * 4.4976:1을 4.50:1로 반올림하면 기준을 충족한 것처럼 읽히기 때문이다.
 * toFixed는 4.56*100=455.999… 같은 부동소수점 오차로 한 단계 더 버려지는 것을 막는다.
 */
function displayedRatio(ratio) {
  return Math.floor(Number((ratio * 100).toFixed(6))) / 100;
}

/**
 * 색을 RGB 세 채널에서 1씩 밝게(lighten)/어둡게(darken) 움직이며 ratioOf(후보)가
 * 목표에 처음 닿는 색을 찾는다. 255단계까지 가도 못 찾으면 그쪽 끝 색(흰색·검정)을
 * 돌려준다. 그 색이 목표를 충족하는지는 부른 쪽이 다시 계산한다(meets_target).
 */
function shiftToTarget(color, ratioOf, target, direction) {
  const sign = direction === 'lighten' ? 1 : -1;
  let candidate = color;
  for (let step = 0; step < 256; step += 1) {
    candidate = color.map(channel => Math.min(255, Math.max(0, channel + sign * step)));
    if (ratioOf(candidate) >= target) return candidate;
  }
  return candidate;
}

/**
 * 글자색 fg, 배경색 bg의 명암비가 target 미만일 때 두 가지 방안(글자색을 바꾸기 /
 * 배경색을 바꾸기)의 추천색을 계산한다. 이미 충족하면 null.
 * 키 이름은 CV 결과의 fix_suggestion과 같다(text_color, background_color).
 */
function suggestContrastFix(fg, bg, target = DEFAULT_REQUIRED_RATIO) {
  const current = contrastRatio(fg, bg);
  if (current >= target) return null;

  const textIsLighter = relativeLuminance(fg) > relativeLuminance(bg);
  const textDirection = textIsLighter ? 'lighten' : 'darken';
  const backgroundDirection = textIsLighter ? 'darken' : 'lighten';

  const adjustedFg = shiftToTarget(fg, color => contrastRatio(color, bg), target, textDirection);
  const adjustedBg = shiftToTarget(bg, color => contrastRatio(fg, color), target, backgroundDirection);
  const fgRatio = contrastRatio(adjustedFg, bg);
  const bgRatio = contrastRatio(fg, adjustedBg);

  const option = (kind, direction, original, adjusted, ratio) => ({
    direction,
    description: `${kind}을 ${DIRECTION_LABEL[direction]}`,
    original_color: original,
    suggested_color: adjusted,
    suggested_hex: toHex(adjusted),
    new_ratio: displayedRatio(ratio),
    meets_target: ratio >= target,
  });

  return {
    current_ratio: displayedRatio(current),
    required_ratio: target,
    text_is_lighter: textIsLighter,
    text_color: option('글자색', textDirection, fg, adjustedFg, fgRatio),
    background_color: option('배경색', backgroundDirection, bg, adjustedBg, bgRatio),
  };
}


// ── 문장 만들기 ────────────────────────────────────────────────────────────

/** 소수 첫째 자리까지만 쓰고 불필요한 .0은 없앤다 (24 → '24', 17.6 → '17.6'). */
function formatNumber(value) {
  return String(Number(Number(value).toFixed(1)));
}

function contrastMessage(fix) {
  const lines = [];
  const required = formatNumber(fix.required_ratio);
  for (const [label, option] of [['글자색', fix.text_color], ['배경색', fix.background_color]]) {
    if (!option.meets_target) continue;
    lines.push(
      `• ${label}을 바꾼다면: ${toHex(option.original_color)} → ${option.suggested_hex} `
      + `(${DIRECTION_LABEL[option.direction]}, 명도 대비 ${option.new_ratio}:1 / 기준 ${required}:1)`,
    );
  }
  if (lines.length === 0) {
    lines.push(`• 글자색이나 배경색 한쪽만 바꿔서는 기준 ${required}:1에 닿기 어렵습니다. 두 색을 함께 조정하세요.`);
  }
  return lines.join('\n');
}


// ── axe 노드에서 값 꺼내기 ─────────────────────────────────────────────────

/** 노드의 any/all/none 안에서 checkId인 체크를 찾아 data를 돌려준다. 없으면 null. */
function findCheckData(node, checkId) {
  for (const group of ['any', 'all', 'none']) {
    const checks = Array.isArray(node?.[group]) ? node[group] : [];
    const hit = checks.find(check => check?.id === checkId);
    if (hit) return hit.data ?? null;
  }
  return null;
}

/** "4.5:1" · "3:1" · 4.5 → 숫자. 읽을 수 없으면 null. */
function parseRequiredRatio(value) {
  const parsed = Number.parseFloat(String(value ?? ''));
  return Number.isFinite(parsed) && parsed > 1 && parsed <= 21 ? parsed : null;
}

function isNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}


// ── 규칙별 안내 ────────────────────────────────────────────────────────────

/**
 * color-contrast 노드의 추천색. 글자색·배경색·기준을 모두 읽을 수 있고, 일반적인
 * 두 색 비교(messageKey 없음)이며, 정수 hex 색으로 보면 아직 기준 미달일 때만 만든다.
 */
function contrastHint(node) {
  const data = findCheckData(node, 'color-contrast');
  if (!data || data.messageKey) return null;

  const fg = parseHex(data.fgColor);
  const bg = parseHex(data.bgColor);
  const required = data.expectedContrastRatio === undefined
    ? DEFAULT_REQUIRED_RATIO
    : parseRequiredRatio(data.expectedContrastRatio);
  if (!fg || !bg || required === null) return null;

  const fix = suggestContrastFix(fg, bg, required);
  if (!fix) return null;  // axe는 미달로 봤지만 hex로 줄이면 충족(알파 혼합의 반올림 차이): 안내할 값이 없다

  return {
    kind: 'color-contrast',
    message: contrastMessage(fix),
    // 현재 명암비는 axe가 잰 값을 우선한다(표시용). 없으면 hex로 계산한 값.
    contrast_ratio: isNumber(data.contrastRatio) ? data.contrastRatio : fix.current_ratio,
    required_ratio: fix.required_ratio,
    text_is_lighter: fix.text_is_lighter,
    text_color: stripOriginal(fix.text_color),
    background_color: stripOriginal(fix.background_color),
  };
}

/** 결과 JSON에는 CV fix_suggestion과 같은 키만 싣는다(original_color는 문장 만들기용). */
function stripOriginal(option) {
  const { original_color: _original, ...rest } = option;
  return rest;
}

/**
 * target-size 노드의 현재 크기·간격과 모자란 만큼. axe는 "크기가 24px 이상이거나,
 * 이웃 대상과 24px 간격이 있거나" 둘 중 하나면 통과시키므로(any) 두 방안을 모두 적는다.
 * 일부가 가려진 경우 등(messageKey가 있는 변형)은 값의 뜻이 달라 안내하지 않는다.
 */
function targetSizeHint(node) {
  const size = findCheckData(node, 'target-size');
  const offset = findCheckData(node, 'target-offset');
  const sizeOk = size && !size.messageKey
    && isNumber(size.minSize) && isNumber(size.width) && isNumber(size.height);
  const offsetOk = offset && !offset.messageKey
    && isNumber(offset.minOffset) && isNumber(offset.closestOffset);
  if (!sizeOk && !offsetOk) return null;

  const hint = { kind: 'target-size', message: '' };
  const lines = [];

  if (sizeOk) {
    const shortWidth = Math.max(0, size.minSize - size.width);
    const shortHeight = Math.max(0, size.minSize - size.height);
    const shortParts = [];
    if (shortWidth > 0) shortParts.push(`가로 ${formatNumber(shortWidth)}px`);
    if (shortHeight > 0) shortParts.push(`세로 ${formatNumber(shortHeight)}px`);
    hint.size = {
      width: size.width,
      height: size.height,
      min_size: size.minSize,
      short_width: Number(shortWidth.toFixed(1)),
      short_height: Number(shortHeight.toFixed(1)),
    };
    if (shortParts.length > 0) {
      lines.push(
        `• 크기를 키운다면: 현재 ${formatNumber(size.width)}px × ${formatNumber(size.height)}px → `
        + `최소 ${formatNumber(size.minSize)}px × ${formatNumber(size.minSize)}px (${shortParts.join(', ')} 더 필요)`,
      );
    }
  }

  if (offsetOk) {
    const shortOffset = Math.max(0, offset.minOffset - offset.closestOffset);
    hint.spacing = {
      closest_offset: offset.closestOffset,
      min_offset: offset.minOffset,
      short_offset: Number(shortOffset.toFixed(1)),
    };
    if (shortOffset > 0) {
      lines.push(
        `• 간격을 넓힌다면: 이웃한 조작 대상과의 안전 영역 지름 ${formatNumber(offset.closestOffset)}px → `
        + `최소 ${formatNumber(offset.minOffset)}px (${formatNumber(shortOffset)}px 더 필요)`,
      );
    }
  }

  if (lines.length === 0) return null;
  hint.message = lines.join('\n');
  return hint;
}

const HINT_BUILDERS = Object.freeze({
  'color-contrast': contrastHint,
  'target-size': targetSizeHint,
});


/**
 * 규칙 ID와 axe 노드로 수정 안내를 만든다. 지원하지 않는 규칙이거나 계산에 필요한
 * 값이 없으면 null.
 *
 * @param {string} ruleId  axe 규칙 ID
 * @param {Object} node    axe 결과의 위반 노드(any/all/none 체크 결과 포함)
 * @returns {Object|null}  { kind, message, ...규칙별 값 }
 */
function buildFixHint(ruleId, node) {
  const build = Object.prototype.hasOwnProperty.call(HINT_BUILDERS, ruleId)
    ? HINT_BUILDERS[ruleId]
    : null;
  return build ? build(node) : null;
}

/**
 * failure_summary 끝에 "개선 안내" 단락으로 안내 문장을 덧붙인다. 안내가 없으면
 * failure_summary를 그대로 돌려준다. 대시보드가 빈 줄로 단락을 나누고 "개선 안내"를
 * 소제목으로 알아보므로 앞에 빈 줄을 한 줄 둔다.
 */
function appendFixHint(failureSummary, hint) {
  const summary = failureSummary || '';
  if (!hint || !hint.message) return summary;
  const section = `${HINT_HEADING}\n${hint.message}`;
  const base = summary.trimEnd();
  return base ? `${base}\n\n${section}` : section;
}


module.exports = {
  buildFixHint,
  appendFixHint,
  suggestContrastFix,
  contrastRatio,
  relativeLuminance,
  displayedRatio,
  parseHex,
  toHex,
  HINT_HEADING,
};
