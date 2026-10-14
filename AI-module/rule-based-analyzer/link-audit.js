'use strict';

// Two link checks axe-core does not run, added 2026-10-03.
//
//   uniaccess-new-window-notice  (KWCAG 7.2.1 사용자 요구에 따른 실행)
//     A link that opens a new window or tab (target="_blank", a named target
//     that is not a frame on the page, or window.open in onclick/href) must
//     say so in its text, title, aria-label, aria-describedby or image alt.
//     Screen-reader users otherwise do not know the page changed windows and
//     the Back button stops working for them.
//
//   uniaccess-ambiguous-link  (KWCAG 6.4.3 적절한 링크 텍스트)
//     A link whose whole accessible name is a generic word such as "더보기",
//     "자세히", "바로가기", "여기" or "+" does not tell where it goes when read
//     in a links list. A title or aria-describedby that names the target
//     counts as a fix. This is judged from the link alone, which is stricter
//     than WCAG 2.4.4 (that also accepts the surrounding paragraph or list
//     item) and closer to 2.4.9; Korean audits usually judge it this way.
//
// Links with no name at all are left to axe's link-name rule, so the same link
// is never deducted twice. Only links rendered at the analysis viewport are
// checked, as axe does. The results use axe's result shape so they pass
// through the same carousel merge, region exclusion (AD/DYNAMIC/POPUP),
// KWCAG mapping and scoring as axe rules. Same-origin frames and shadow DOM
// are not checked (axe checks them; these two rules look at the main document).

const NEW_WINDOW_RULE_ID = 'uniaccess-new-window-notice';
const AMBIGUOUS_LINK_RULE_ID = 'uniaccess-ambiguous-link';

const RULE_INFO = Object.freeze({
  [NEW_WINDOW_RULE_ID]: {
    impact: 'moderate',
    tags: ['uniaccess', 'kwcag721', 'wcag2aaa', 'wcag325'],
    description: '새 창(새 탭)으로 열리는 링크는 그 사실을 미리 알려야 합니다.',
    help: '새 창으로 열리는 링크에 새 창 안내가 없습니다',
  },
  [AMBIGUOUS_LINK_RULE_ID]: {
    impact: 'serious',
    tags: ['uniaccess', 'kwcag643', 'wcag2a', 'wcag244', 'wcag249'],
    description: '링크 텍스트만 듣고도 어디로 가는지 알 수 있어야 합니다.',
    help: '링크 텍스트가 "더보기"·"바로가기"처럼 목적을 알 수 없는 말뿐입니다',
  },
});

// Runs in the page. Kept free of outer variables because page.evaluate
// serializes it.
function auditLinksInPage({ scope, newWindowRuleId, ambiguousRuleId }) {
  const NOTICE_SOURCE = '새\\s*창|새\\s*탭|새로운\\s*창|창\\s*열림|창\\s*열기|팝업|new\\s*(window|tab)|opens?\\s+in\\s+(a\\s+)?new';
  const NOTICE = new RegExp(NOTICE_SOURCE, 'i');
  const NOTICE_ALL = new RegExp(`(${NOTICE_SOURCE})(으로|로)?\\s*(열림|이동|열기)?`, 'gi');
  const AMBIGUOUS = new Set([
    '더보기', '자세히', '자세히보기', '상세보기', '상세', '바로가기', '바로보기', '보기', '이동',
    '클릭', '여기', '이곳', '여기를클릭', '여기클릭', '이곳을클릭', '클릭하세요', '링크', '더알아보기',
    'more', 'readmore', 'viewmore', 'moreview', 'seemore', 'click', 'clickhere', 'here', 'go', 'link',
  ]);
  const SYMBOLS = /[\s +＋>›»→▶▷▸►<‹«←◀◁·•.…:()[\]{}\-_|/\\]+/g;
  const compact = value => String(value || '').replace(/\s+/g, ' ').trim();
  const normalize = value => compact(value).toLowerCase().replace(SYMBOLS, '');

  const isRendered = element => {
    if (element.closest('[aria-hidden="true"]')) return false;
    if (element.tagName === 'AREA') {
      const map = element.closest('map');
      const name = map && map.getAttribute('name');
      if (!name) return false;
      const image = document.querySelector(`img[usemap="#${CSS.escape(name)}"]`);
      return Boolean(image && isRendered(image));
    }
    if (element.getClientRects().length === 0) return false;
    const style = getComputedStyle(element);
    return style.visibility !== 'hidden' && style.visibility !== 'collapse';
  };

  const textOfIds = ids => compact(String(ids || '').split(/\s+/).filter(Boolean)
    .map(id => document.getElementById(id)?.textContent || '').join(' '));

  const pseudoText = (element, which) => {
    const content = getComputedStyle(element, which).content;
    const match = /^["'](.*)["']$/.exec(content || '');
    return match ? match[1] : '';
  };

  // Text a screen reader announces for the link's content: text nodes, image
  // alt, svg titles and screen-reader-only text; hidden children are skipped.
  const subtreeText = node => {
    let out = '';
    for (const child of node.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) {
        out += ` ${child.textContent}`;
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) continue;
      if (child.getAttribute('aria-hidden') === 'true') continue;
      const style = getComputedStyle(child);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      const label = child.getAttribute('aria-label');
      if (label && label.trim()) { out += ` ${label}`; continue; }
      const tag = child.tagName;
      if (tag === 'IMG' || (tag === 'INPUT' && child.type === 'image')) {
        out += ` ${child.getAttribute('alt') || ''}`;
      } else if (tag === 'svg' || tag === 'SVG') {
        out += ` ${child.querySelector('title')?.textContent || ''}`;
      } else {
        out += ` ${subtreeText(child)}`;
      }
    }
    return compact(out);
  };

  const accessibleName = element => {
    const labelledBy = textOfIds(element.getAttribute('aria-labelledby'));
    if (labelledBy) return labelledBy;
    const label = compact(element.getAttribute('aria-label'));
    if (label) return label;
    if (element.tagName === 'AREA') return compact(element.getAttribute('alt'));
    return compact(`${pseudoText(element, '::before')} ${subtreeText(element)} ${pseudoText(element, '::after')}`);
  };

  const uniqueSelector = element => {
    const escape = value => CSS.escape(value);
    if (element.id && document.querySelectorAll(`#${escape(element.id)}`).length === 1) {
      return `#${escape(element.id)}`;
    }
    const parts = [];
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE && current !== document.documentElement) {
      if (current !== element && current.id
        && document.querySelectorAll(`#${escape(current.id)}`).length === 1) {
        parts.unshift(`#${escape(current.id)}`);
        break;
      }
      const tag = current.tagName.toLowerCase();
      const parent = current.parentElement;
      if (!parent) { parts.unshift(tag); break; }
      const sameTag = Array.from(parent.children).filter(child => child.tagName === current.tagName);
      parts.unshift(sameTag.length > 1 ? `${tag}:nth-of-type(${sameTag.indexOf(current) + 1})` : tag);
      current = parent;
    }
    if (current === document.documentElement) parts.unshift('html');
    return parts.join(' > ');
  };

  const outerHtml = element => {
    const html = element.outerHTML;
    return html.length > 300 ? `${html.slice(0, 300)}...` : html;
  };

  // Nearest heading that comes before the link inside its section, used to
  // suggest a concrete text such as "공지사항 더보기".
  const contextHeading = element => {
    let ancestor = element.parentElement;
    for (let depth = 0; ancestor && ancestor !== document.body && depth < 6; depth += 1) {
      const headings = Array.from(ancestor.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]'))
        .filter(heading => !heading.contains(element)
          && (heading.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING));
      for (let index = headings.length - 1; index >= 0; index -= 1) {
        const text = compact(subtreeText(headings[index]) || headings[index].textContent);
        if (text) return text.length > 30 ? `${text.slice(0, 30)}…` : text;
      }
      ancestor = ancestor.parentElement;
    }
    return '';
  };

  const opensNewWindow = element => {
    const target = compact(element.getAttribute('target')).toLowerCase();
    if (target && !['_self', '_parent', '_top'].includes(target)) {
      const frame = document.querySelector(
        `iframe[name="${CSS.escape(element.getAttribute('target').trim())}"],`
        + `frame[name="${CSS.escape(element.getAttribute('target').trim())}"]`,
      );
      if (!frame) return true;
    }
    const script = `${element.getAttribute('onclick') || ''} ${
      /^\s*javascript:/i.test(element.getAttribute('href') || '') ? element.getAttribute('href') : ''}`;
    return /window\.open\s*\(/.test(script);
  };

  const newWindowNodes = [];
  const ambiguousNodes = [];
  for (const element of document.querySelectorAll('a[href], area[href]')) {
    if (scope && !element.closest(scope)) continue;
    if (!isRendered(element)) continue;
    const name = accessibleName(element);
    const title = compact(element.getAttribute('title'));
    const described = textOfIds(element.getAttribute('aria-describedby'));
    if (!name && !title) continue;  // axe link-name reports links without a name
    const shown = name || title;

    if (opensNewWindow(element) && !NOTICE.test(`${name} ${title} ${described}`)) {
      newWindowNodes.push({
        target: [uniqueSelector(element)],
        html: outerHtml(element),
        impact: 'moderate',
        failureSummary: `"${shown.slice(0, 40)}" 링크는 새 창으로 열리지만 링크 텍스트·title·`
          + '대체 텍스트 어디에도 새 창 안내가 없습니다. '
          + '예: title="새 창 열림" 또는 화면에 숨긴 글 "(새 창)"을 링크 안에 넣으세요.',
      });
    }

    // The name (or the title when it is the only name) is generic, and no
    // title/aria-describedby adds what the target is. A new-window notice
    // alone ("새 창") does not say where the link goes.
    const normalized = normalize(shown);
    const genericName = normalized === '' || AMBIGUOUS.has(normalized);
    const namesTarget = text => {
      const rest = normalize(String(text || '').replace(NOTICE_ALL, ' '));
      return rest !== '' && rest !== normalized && !AMBIGUOUS.has(rest);
    };
    const supplements = name ? [title, described] : [described];
    if (genericName && !supplements.some(namesTarget)) {
      const heading = contextHeading(element);
      const example = heading ? `"${heading} ${shown}"` : '"공지사항 더보기"처럼 대상을 밝힌 글';
      ambiguousNodes.push({
        target: [uniqueSelector(element)],
        html: outerHtml(element),
        impact: 'serious',
        failureSummary: `링크 텍스트 "${shown}"만으로는 어디로 가는지 알 수 없습니다. `
          + `예: ${example}${heading ? ` (가까운 제목 "${heading}" 기준)` : ''}. `
          + '보이는 글을 바꾸기 어렵다면 aria-label이나 숨김 글로 대상을 함께 알려 주세요.',
        contextHeading: heading || null,
      });
    }
  }
  return [
    { id: newWindowRuleId, nodes: newWindowNodes },
    { id: ambiguousRuleId, nodes: ambiguousNodes },
  ];
}

function withRuleInfo(rule) {
  const info = RULE_INFO[rule.id];
  return {
    id: rule.id,
    impact: info.impact,
    tags: [...info.tags],
    description: info.description,
    help: info.help,
    helpUrl: '',
    nodes: rule.nodes.map(node => ({ any: [], all: [], none: [], ...node })),
  };
}

// Returns the two rules' violations in axe's shape. `scope` limits the check to
// links inside elements matching that selector (used for open popups).
async function auditLinks(page, { scope = null } = {}) {
  const rules = await page.evaluate(auditLinksInPage, {
    scope,
    newWindowRuleId: NEW_WINDOW_RULE_ID,
    ambiguousRuleId: AMBIGUOUS_LINK_RULE_ID,
  }).catch((error) => {
    console.warn(`   링크 검사 실패: ${error.message}`);
    return [];
  });
  return rules.filter(rule => rule.nodes.length > 0).map(withRuleInfo);
}

// Adds link-audit violations to axe results (in place) and returns them.
function appendLinkViolations(axeResults, linkViolations) {
  if (!axeResults) return axeResults;
  axeResults.violations = axeResults.violations || [];
  for (const rule of linkViolations || []) {
    const existing = axeResults.violations.find(candidate => candidate.id === rule.id);
    if (existing) {
      existing.nodes.push(...rule.nodes);
    } else {
      axeResults.violations.push(rule);
    }
  }
  return axeResults;
}

module.exports = {
  AMBIGUOUS_LINK_RULE_ID,
  NEW_WINDOW_RULE_ID,
  appendLinkViolations,
  auditLinks,
};
