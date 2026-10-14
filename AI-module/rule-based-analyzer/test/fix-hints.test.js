'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  HINT_HEADING,
  appendFixHint,
  buildFixHint,
  contrastRatio,
  displayedRatio,
  parseHex,
  suggestContrastFix,
  toHex,
} = require('../fix-hints');

// axe가 color-contrast 위반 노드에 싣는 모양 그대로 (axe-core 4.11, 2026-10-13 실측)
function contrastNode(data) {
  return {
    any: [{
      id: 'color-contrast',
      data: {
        fontSize: '12.0pt (16px)', fontWeight: 'normal', messageKey: null, expectedContrastRatio: '4.5:1', ...data,
      },
    }],
    all: [],
    none: [],
  };
}

function targetNode(sizeData, offsetData) {
  return {
    any: [
      { id: 'target-size', data: sizeData },
      { id: 'target-offset', data: offsetData },
    ],
    all: [],
    none: [],
  };
}

// 명세(WCAG 2.x 상대 휘도)대로 따로 계산한 값. 구현의 공식과 독립적으로 검증하려고 테스트 안에 다시 쓴다.
function referenceRatio(a, b) {
  const lin = c => ((c / 255) <= 0.04045 ? (c / 255) / 12.92 : (((c / 255) + 0.055) / 1.055) ** 2.4);
  const lum = ([r, g, bl]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(bl);
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test('hex 변환은 6자리 색만 받고 대문자로 돌려준다', () => {
  assert.deepEqual(parseHex('#767676'), [118, 118, 118]);
  assert.deepEqual(parseHex('FFFFFF'), [255, 255, 255]);
  assert.equal(parseHex('#fff'), null);
  assert.equal(parseHex(undefined), null);
  assert.equal(toHex([118, 118, 118]), '#767676');
  assert.equal(toHex([0, 10, 255]), '#000AFF');
});

test('명암비 표시값은 반올림하지 않고 소수 둘째 자리에서 버린다', () => {
  assert.equal(displayedRatio(4.4976), 4.49);
  assert.equal(displayedRatio(4.56), 4.56);   // 4.56*100=455.999… 오차로 4.55가 되면 안 된다
  assert.equal(displayedRatio(21), 21);
  assert.equal(contrastRatio([255, 255, 255], [0, 0, 0]), 21);
});

test('어두운 글자가 밝은 배경 위에 있으면 글자는 더 어둡게, 배경은 더 밝게 추천한다', () => {
  const fix = suggestContrastFix([119, 119, 119], [255, 255, 255], 4.5);
  assert.equal(fix.text_is_lighter, false);
  assert.equal(fix.current_ratio, 4.47);
  assert.deepEqual(
    [fix.text_color.direction, fix.text_color.suggested_hex, fix.text_color.new_ratio, fix.text_color.meets_target],
    ['darken', '#767676', 4.54, true],
  );
  // 배경은 이미 흰색이라 더 밝게 할 수 없다: 끝 색과 meets_target=false
  assert.deepEqual(
    [fix.background_color.direction, fix.background_color.suggested_hex, fix.background_color.meets_target],
    ['lighten', '#FFFFFF', false],
  );
});

test('밝은 글자가 어두운 배경 위에 있으면 방향이 뒤집힌다 (회색 배경의 흰 글자)', () => {
  const fix = suggestContrastFix([255, 255, 255], [128, 128, 128], 4.5);
  assert.equal(fix.text_is_lighter, true);
  assert.equal(fix.current_ratio, 3.94);
  assert.deepEqual(
    [fix.text_color.direction, fix.text_color.suggested_hex, fix.text_color.meets_target],
    ['lighten', '#FFFFFF', false],   // 흰 글자는 더 밝아질 수 없다
  );
  assert.deepEqual(
    [fix.background_color.direction, fix.background_color.suggested_hex, fix.background_color.new_ratio, fix.background_color.meets_target],
    ['darken', '#767676', 4.54, true],
  );
});

// cv-analyzer/contrast_analyzer.py의 suggest_fix가 같은 입력에서 낸 값을 그대로 고정했다.
// (tests/test_cv_measurement.py에도 같은 벡터가 있다. 두 모듈의 추천색이 어긋나면 한쪽이 실패한다.)
const SHARED_VECTORS = [
  { fg: [119, 119, 119], bg: [255, 255, 255], target: 4.5, text: ['#767676', 4.54, true], bg_opt: ['#FFFFFF', 4.47, false] },
  { fg: [255, 255, 255], bg: [128, 128, 128], target: 4.5, text: ['#FFFFFF', 3.94, false], bg_opt: ['#767676', 4.54, true] },
  { fg: [85, 85, 85], bg: [0, 0, 0], target: 4.5, text: ['#757575', 4.55, true], bg_opt: ['#000000', 2.81, false] },
  { fg: [153, 153, 153], bg: [255, 255, 255], target: 3.0, text: ['#949494', 3.03, true], bg_opt: ['#FFFFFF', 2.84, false] },
  { fg: [127, 127, 127], bg: [128, 128, 128], target: 4.5, text: ['#171717', 4.53, true], bg_opt: ['#FFFFFF', 4, false] },
];

for (const vector of SHARED_VECTORS) {
  test(`CV 모듈과 같은 추천색: ${toHex(vector.fg)} / ${toHex(vector.bg)} (기준 ${vector.target})`, () => {
    const fix = suggestContrastFix(vector.fg, vector.bg, vector.target);
    assert.deepEqual(
      [fix.text_color.suggested_hex, fix.text_color.new_ratio, fix.text_color.meets_target], vector.text);
    assert.deepEqual(
      [fix.background_color.suggested_hex, fix.background_color.new_ratio, fix.background_color.meets_target], vector.bg_opt);
  });
}

test('이미 기준을 충족하는 색에는 추천을 만들지 않는다', () => {
  assert.equal(suggestContrastFix([0, 0, 0], [255, 255, 255], 4.5), null);
  assert.equal(suggestContrastFix([118, 118, 118], [255, 255, 255], 4.5), null);   // 4.54:1
});

test('meets_target=true인 추천은 독립 계산으로도 기준을 넘고, new_ratio는 그 값을 버린 값이다', () => {
  // 고정 시드 난수(재현 가능). 흰색·검정·회색 배경을 섞어 양쪽 끝 색 경우도 지나가게 한다.
  let seed = 20261013;
  const next = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  const channel = () => Math.floor(next() * 256);
  let checked = 0;
  for (let i = 0; i < 400; i += 1) {
    const fg = [channel(), channel(), channel()];
    const bg = i % 7 === 0 ? [255, 255, 255] : i % 11 === 0 ? [0, 0, 0] : [channel(), channel(), channel()];
    const target = [3, 4.5, 7][i % 3];
    const fix = suggestContrastFix(fg, bg, target);
    if (!fix) {
      assert.ok(referenceRatio(fg, bg) >= target, 'null은 이미 충족일 때만');
      continue;
    }
    for (const [option, ratio] of [
      [fix.text_color, referenceRatio(option_color(fix.text_color), bg)],
      [fix.background_color, referenceRatio(fg, option_color(fix.background_color))],
    ]) {
      assert.equal(option.meets_target, ratio >= target, `meets_target 일치 (${toHex(fg)}/${toHex(bg)}/${target})`);
      assert.equal(option.new_ratio, Math.floor(Number((ratio * 100).toFixed(6))) / 100);
      checked += 1;
    }
  }
  assert.ok(checked > 400);
});

function option_color(option) {
  return option.suggested_color;
}

test('color-contrast 노드: 구조화된 값과 한국어 문장을 만든다', () => {
  const hint = buildFixHint('color-contrast', contrastNode({ fgColor: '#777777', bgColor: '#ffffff', contrastRatio: 4.47 }));
  assert.equal(hint.kind, 'color-contrast');
  assert.equal(hint.contrast_ratio, 4.47);   // axe가 잰 현재 값
  assert.equal(hint.required_ratio, 4.5);
  assert.equal(hint.text_is_lighter, false);
  assert.deepEqual(Object.keys(hint.text_color).sort(),
    ['description', 'direction', 'meets_target', 'new_ratio', 'suggested_color', 'suggested_hex']);
  assert.equal(hint.text_color.description, '글자색을 더 어둡게');
  assert.equal(
    hint.message,
    '• 글자색을 바꾼다면: #777777 → #767676 (더 어둡게, 명도 대비 4.54:1 / 기준 4.5:1)',
  );   // 기준에 못 미치는 배경색 방안은 문장에서 뺀다
});

test('color-contrast 노드: 두 방안이 모두 가능하면 둘 다 적는다', () => {
  // 중간 밝기 글자(#6b6b6b)가 중간 밝기 배경(#a0a0a0) 위: 글자를 더 어둡게도, 배경을 더 밝게도 기준에 닿는다.
  const fix = suggestContrastFix([107, 107, 107], [160, 160, 160], 4.5);
  assert.ok(fix.text_color.meets_target && fix.background_color.meets_target);
  const hint = buildFixHint('color-contrast', contrastNode({ fgColor: '#6b6b6b', bgColor: '#a0a0a0', contrastRatio: 2.4 }));
  const lines = hint.message.split('\n');
  assert.equal(lines.length, 2);
  assert.match(lines[0], /^• 글자색을 바꾼다면: #6B6B6B → #[0-9A-F]{6} \(더 어둡게, 명도 대비 [\d.]+:1 \/ 기준 4\.5:1\)$/);
  assert.match(lines[1], /^• 배경색을 바꾼다면: #A0A0A0 → #[0-9A-F]{6} \(더 밝게, 명도 대비 [\d.]+:1 \/ 기준 4\.5:1\)$/);
});

test('color-contrast 노드: 큰 글자 기준(3:1)을 따른다', () => {
  const hint = buildFixHint('color-contrast', contrastNode({
    fgColor: '#999999', bgColor: '#ffffff', contrastRatio: 2.84, expectedContrastRatio: '3:1',
  }));
  assert.equal(hint.required_ratio, 3);
  assert.equal(hint.text_color.suggested_hex, '#949494');
  assert.match(hint.message, /기준 3:1\)$/);
});

test('color-contrast 노드: 한쪽 색만 바꿔서는 기준에 못 닿으면 두 색을 함께 조정하라고 알려 준다', () => {
  // 실제 axe 기준(3:1, 4.5:1)에서는 두 방안이 모두 실패하는 색 조합이 사실상 없다(둘 중 하나는 흰색·검정
  // 쪽으로 끝까지 가면 닿는다). 이 갈래를 시험하려고 21:1이라는 도달 불가능한 기준을 일부러 준다.
  const hint = buildFixHint('color-contrast', contrastNode({
    fgColor: '#c8c8c8', bgColor: '#bebebe', contrastRatio: 1.05, expectedContrastRatio: '21:1',
  }));
  assert.equal(hint.text_color.meets_target, false);
  assert.equal(hint.background_color.meets_target, false);
  assert.equal(hint.message, '• 글자색이나 배경색 한쪽만 바꿔서는 기준 21:1에 닿기 어렵습니다. 두 색을 함께 조정하세요.');
});

test('color-contrast 노드: 값을 믿을 수 없으면 안내를 만들지 않는다', () => {
  const base = { fgColor: '#777777', bgColor: '#ffffff', contrastRatio: 4.47 };
  // 그림자가 걸린 변형은 글자색·배경색 두 값으로 설명되지 않는다
  assert.equal(buildFixHint('color-contrast', contrastNode({ ...base, messageKey: 'fgOnShadowColor' })), null);
  assert.equal(buildFixHint('color-contrast', contrastNode({ ...base, messageKey: 'shadowOnBgColor' })), null);
  // 색이 없거나 hex가 아님
  assert.equal(buildFixHint('color-contrast', contrastNode({ ...base, fgColor: undefined })), null);
  assert.equal(buildFixHint('color-contrast', contrastNode({ ...base, bgColor: 'rgb(255,255,255)' })), null);
  // 기준값을 읽을 수 없음
  assert.equal(buildFixHint('color-contrast', contrastNode({ ...base, expectedContrastRatio: 'strong' })), null);
  // axe는 미달로 봤지만(알파 혼합 등) 정수 hex로 줄이면 이미 충족: 안내할 색이 없다
  assert.equal(buildFixHint('color-contrast', contrastNode({ fgColor: '#767676', bgColor: '#ffffff', contrastRatio: 4.49 })), null);
  // 체크 결과 자체가 없음
  assert.equal(buildFixHint('color-contrast', { any: [], all: [], none: [] }), null);
  assert.equal(buildFixHint('color-contrast', {}), null);
});

test('target-size 노드: 모자란 가로·세로와 간격을 계산한다', () => {
  const hint = buildFixHint('target-size', targetNode(
    { minSize: 24, width: 10, height: 10 },
    { closestOffset: 18, minOffset: 24 },
  ));
  assert.equal(hint.kind, 'target-size');
  assert.deepEqual(hint.size, { width: 10, height: 10, min_size: 24, short_width: 14, short_height: 14 });
  assert.deepEqual(hint.spacing, { closest_offset: 18, min_offset: 24, short_offset: 6 });
  assert.equal(hint.message, [
    '• 크기를 키운다면: 현재 10px × 10px → 최소 24px × 24px (가로 14px, 세로 14px 더 필요)',
    '• 간격을 넓힌다면: 이웃한 조작 대상과의 안전 영역 지름 18px → 최소 24px (6px 더 필요)',
  ].join('\n'));
});

test('target-size 노드: 한 방향만 모자라고 소수 값이면 모자란 쪽만 적는다', () => {
  const hint = buildFixHint('target-size', targetNode(
    { minSize: 24, width: 30, height: 10.5 },
    { closestOffset: 17.6, minOffset: 24 },
  ));
  assert.equal(hint.size.short_width, 0);
  assert.equal(hint.size.short_height, 13.5);
  assert.match(hint.message, /\(세로 13\.5px 더 필요\)/);
  assert.doesNotMatch(hint.message, /가로/);
  assert.match(hint.message, /17\.6px → 최소 24px \(6\.4px 더 필요\)/);
});

test('target-size 노드: 일부가 가려진 변형이나 값이 없으면 만들지 않는다', () => {
  assert.equal(buildFixHint('target-size', targetNode(
    { minSize: 24, width: 10, height: 10, messageKey: 'partiallyObscured' },
    { closestOffset: 18, minOffset: 24, messageKey: 'nonTabbableNeighbor' },
  )), null);
  assert.equal(buildFixHint('target-size', { any: [], all: [], none: [] }), null);
  // 크기 체크만 있어도 그 줄은 만든다
  const sizeOnly = buildFixHint('target-size', { any: [{ id: 'target-size', data: { minSize: 24, width: 20, height: 24 } }] });
  assert.equal(sizeOnly.message, '• 크기를 키운다면: 현재 20px × 24px → 최소 24px × 24px (가로 4px 더 필요)');
  assert.equal(sizeOnly.spacing, undefined);
});

test('지원하지 않는 규칙은 null이고, 객체 기본 속성 이름으로도 걸리지 않는다', () => {
  assert.equal(buildFixHint('image-alt', contrastNode({ fgColor: '#777777', bgColor: '#ffffff' })), null);
  assert.equal(buildFixHint('constructor', {}), null);
  assert.equal(buildFixHint('toString', {}), null);
  assert.equal(buildFixHint(undefined, {}), null);
});

test('failure_summary 끝에 "개선 안내" 단락으로 붙인다', () => {
  const hint = { message: '• 글자색을 바꾼다면: #777777 → #767676' };
  assert.equal(HINT_HEADING, '개선 안내');
  assert.equal(
    appendFixHint('다음 중 하나를 해결하세요:\n  엘리먼트가 4.47', hint),
    '다음 중 하나를 해결하세요:\n  엘리먼트가 4.47\n\n개선 안내\n• 글자색을 바꾼다면: #777777 → #767676',
  );
  assert.equal(appendFixHint('끝 공백 정리  \n', hint), '끝 공백 정리\n\n개선 안내\n• 글자색을 바꾼다면: #777777 → #767676');
  assert.equal(appendFixHint('', hint), '개선 안내\n• 글자색을 바꾼다면: #777777 → #767676');
  assert.equal(appendFixHint('원문 그대로', null), '원문 그대로');
  assert.equal(appendFixHint(undefined, null), '');
  assert.equal(appendFixHint('원문', { message: '' }), '원문');
});
