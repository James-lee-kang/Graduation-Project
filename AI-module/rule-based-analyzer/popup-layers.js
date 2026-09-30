'use strict';

// Layer popups (notice/event overlays that public sites open over the page on
// arrival) cover the page's own content. Left open, they hide the content from
// the CV screenshot and the live report, and their text is read as page text.
// They are still content the site made, so they are not silently dropped:
//   1) findPopupLayers marks each popup with POPUP_ATTRIBUTE while it is open,
//      so its own violations can be scanned and reported under reason POPUP;
//   2) hidePopupLayers then clicks the popup's own close control (so the site's
//      "do not show today" cookie logic runs) and always hides it as well,
//      because close controls without a handler or with a slow animation were
//      seen to leave the popup on screen.
// The page is then analyzed as a visitor sees it after closing the popup.
// This is a heuristic: popup markup differs by site and not every popup is
// found. A missed popup stays in the analysis exactly as before.

const POPUP_ATTRIBUTE = 'data-ua-popup';

// A popup covers at least this share of the viewport. Smaller fixed elements
// (sticky headers, chat buttons, cookie bars) are ordinary page UI.
const POPUP_MIN_VIEWPORT_SHARE = 0.2;
// Page UI such as headers rarely stacks above this; popups nearly always do.
const POPUP_MIN_Z_INDEX = 100;
const POPUP_CLOSE_PATTERN_SOURCE = '(닫기|close|오늘\\s*하루|다시\\s*보지|안\\s*보기|그만\\s*보기|×|✕)';

function findPopupsInPage({ attribute, minShare, minZIndex }) {
  const viewportArea = window.innerWidth * window.innerHeight;
  const found = [];
  for (const element of document.querySelectorAll('body *')) {
    if (found.some((popup) => popup.contains(element))) continue;
    const style = window.getComputedStyle(element);
    if (style.position !== 'fixed' && style.position !== 'absolute') continue;
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
    const zIndex = parseInt(style.zIndex, 10);
    if (!zIndex || zIndex < minZIndex) continue;
    const rect = element.getBoundingClientRect();
    if (Math.max(0, rect.width) * Math.max(0, rect.height) < viewportArea * minShare) continue;
    if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
    element.setAttribute(attribute, String(found.length));
    found.push(element);
  }
  return found.map((element) => {
    const rect = element.getBoundingClientRect();
    return {
      index: Number(element.getAttribute(attribute)),
      tag: element.tagName.toLowerCase(),
      id: element.id || null,
      x: Math.round(rect.left + window.scrollX),
      y: Math.round(rect.top + window.scrollY),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    };
  });
}

function hidePopupsInPage({ attribute, closePatternSource }) {
  const closePattern = new RegExp(closePatternSource, 'i');
  const results = [];
  for (const popup of document.querySelectorAll(`[${attribute}]`)) {
    let clickedClose = false;
    for (const control of popup.querySelectorAll('a, button, span, div, img, i')) {
      const label = `${control.textContent || ''} ${control.getAttribute('aria-label') || ''} `
        + `${control.getAttribute('alt') || ''} ${control.className || ''} ${control.id || ''}`;
      if (closePattern.test(label)) {
        control.click();
        clickedClose = true;
        break;
      }
    }
    // The click may already have removed the popup; otherwise hide it.
    if (popup.isConnected) popup.style.setProperty('display', 'none', 'important');
    results.push({ index: Number(popup.getAttribute(attribute)), clicked_close: clickedClose });
  }
  return results;
}

// Marks the open popups and returns their document rectangles.
async function findPopupLayers(page) {
  return page.evaluate(findPopupsInPage, {
    attribute: POPUP_ATTRIBUTE,
    minShare: POPUP_MIN_VIEWPORT_SHARE,
    minZIndex: POPUP_MIN_Z_INDEX,
  }).catch(() => []);
}

// Closes and hides the marked popups. Returns, per popup, whether its own
// close control was clicked.
async function hidePopupLayers(page) {
  const results = await page.evaluate(hidePopupsInPage, {
    attribute: POPUP_ATTRIBUTE,
    closePatternSource: POPUP_CLOSE_PATTERN_SOURCE,
  }).catch(() => []);
  // Some modals only close from the keyboard.
  await page.keyboard.press('Escape').catch(() => {});
  if (results.length > 0) await page.waitForTimeout(500);
  return results;
}

module.exports = {
  POPUP_ATTRIBUTE,
  findPopupLayers,
  hidePopupLayers,
};
