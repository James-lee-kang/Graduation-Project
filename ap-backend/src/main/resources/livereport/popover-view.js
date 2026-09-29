function createLivePopoverView({document, popover, popoverTags, popoverDetail, createSeverityBadge, createCodeBadge, textValue, clusterIssuesFor, presentationNoteFor, getState}) {
  const renderDetailContent = issue => {
    const severityBadge = createSeverityBadge(issue);
    const codeBadge = createCodeBadge(issue);
    popoverTags.replaceChildren();
    if (severityBadge) popoverTags.append(severityBadge);
    if (codeBadge) popoverTags.append(codeBadge);
    const title = document.createElement('h3');
    title.className = 'ap-live-popover__title';
    title.textContent = textValue(issue.title, 300) || '접근성 이슈';
    const message = document.createElement('p');
    message.className = 'ap-live-popover__message';
    message.textContent = textValue(issue.message, 1600) || '이 문제에 대한 상세 설명이 없습니다.';
    const path = document.createElement('code');
    path.className = 'ap-live-popover__path';
    path.textContent = textValue(issue.path, 2048) || '요소 경로 정보 없음';
    const noteText = presentationNoteFor(issue);
    if (noteText) {
      const note = document.createElement('p');
      note.className = 'ap-live-popover__note';
      note.textContent = noteText;
      popoverDetail.replaceChildren(title, note, message, path);
    } else popoverDetail.replaceChildren(title, message, path);
  };
  // 묶인 이슈를 < > 로 넘길 때 팝오버 크기가 출렁이지 않도록, 가장 긴 이슈 높이에 맞춰 고정
  const sizePopoverForCluster = entry => {
    popover.style.minHeight = '';
    const issues = clusterIssuesFor(entry);
    if (issues.length < 2) return;
    const previousVisibility = popover.style.visibility;
    popover.style.visibility = 'hidden';
    let tallest = 0;
    issues.forEach(issue => {
      renderDetailContent(issue);
      tallest = Math.max(tallest, popover.offsetHeight);
    });
    popover.style.visibility = previousVisibility;
    if (tallest > 0) popover.style.minHeight = `${tallest}px`;
  };
  const positionPopover = (
    documentLeft = globalThis.scrollX,
    documentTop = globalThis.scrollY
  ) => {
    const {openEntry, openTargetEntry, viewScale, viewTopInset = 0} = getState();
    if (popover.hidden || !openEntry) return;
    // 팝오버는 사용자가 가리킨 칩에 붙인다. 요소 전체를 기준으로 하면 큰 요소일수록
    // 칩에서 멀어지고, 묶인 이슈를 넘길 때마다 기준 요소가 바뀌어 팝오버가 움직인다.
    // 칩이 숨겨진 경우(마커 끄기 등)에만 대상 요소를 기준으로 한다.
    const markerVisible = openEntry.marker?.isConnected && !openEntry.marker.hidden;
    const targetEntry = openTargetEntry?.element?.isConnected ? openTargetEntry : openEntry;
    const anchor = (markerVisible ? openEntry.marker : targetEntry.element).getBoundingClientRect();
    const scale = 1 / viewScale;
    popover.style.transform = `scale(${scale})`;
    const width = popover.offsetWidth * scale;
    const height = popover.offsetHeight * scale;
    const gap = 8 * scale;
    const viewportLeft = 12;
    const viewportTop = 12 + viewTopInset / viewScale;
    const viewportRight = innerWidth - 12;
    const viewportBottom = innerHeight - 12;
    const clamp = (value, min, max) => Math.max(min, Math.min(value, Math.max(min, max)));
    const spaceBelow = viewportBottom - anchor.bottom - gap;
    const spaceAbove = anchor.top - gap - viewportTop;
    const spaceRight = viewportRight - anchor.right - gap;
    const spaceLeft = anchor.left - gap - viewportLeft;
    let left;
    let top;
    if (height <= spaceBelow || height <= spaceAbove) {
      // 칩 바로 아래, 공간이 없으면 칩 바로 위. 가로는 칩 왼쪽에 맞추고 넘치면 칩 오른쪽에 맞춘다.
      top = height <= spaceBelow ? anchor.bottom + gap : anchor.top - gap - height;
      left = anchor.left + width <= viewportRight ? anchor.left : anchor.right - width;
    } else if (width <= spaceRight || width <= spaceLeft) {
      // 위아래 모두 좁으면 칩 옆에 두고, 세로는 칩 높이에서 화면 안으로 맞춘다.
      left = width <= spaceRight ? anchor.right + gap : anchor.left - gap - width;
      top = anchor.top;
    } else {
      // 어디에도 온전히 들어가지 않으면 더 넓은 쪽에 붙인다.
      top = spaceBelow >= spaceAbove ? anchor.bottom + gap : anchor.top - gap - height;
      left = anchor.left;
    }
    left = clamp(left, viewportLeft, viewportRight - width);
    top = clamp(top, viewportTop, viewportBottom - height);
    const viewportAttached = markerVisible
      ? openEntry.markerViewportAttached === true
      : targetEntry === openEntry
        ? openEntry.markerViewportAttached === true
        : targetEntry.viewportAttached === true;
    popover.style.position = viewportAttached ? 'fixed' : 'absolute';
    popover.style.left = `${left + (viewportAttached ? 0 : documentLeft)}px`;
    popover.style.top = `${top + (viewportAttached ? 0 : documentTop)}px`;
  };
  return {renderDetailContent, sizePopoverForCluster, positionPopover};
}
