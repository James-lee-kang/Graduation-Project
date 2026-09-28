import { describe, expect, it } from "vitest";

import { getLocatorExplanation } from "./locator-explanation";
import { getLocatorLabel } from "./locator-labels";

describe("locator labels", () => {
  it.each([
    [undefined, "위치 확인 중"],
    [{ status: "CONNECTED" }, "현재 화면에서 찾음"],
    [{ status: "OFFSCREEN", reason: "OUTSIDE_VIEWPORT_OR_CLIPPED" }, "화면 밖의 요소"],
    [{ status: "HIDDEN_STATE", reason: "DISPLAY_NONE", recoverable: true }, "다른 슬라이드의 요소"],
    [{ status: "HIDDEN_STATE", reason: "DISPLAY_NONE", recoverable: false }, "현재 숨겨진 요소"],
    [{ status: "UNAVAILABLE", reason: "LOCATOR_MISSING" }, "요소 경로 없음"],
    [{ status: "UNAVAILABLE", reason: "INVALID_SELECTOR" }, "요소 경로 오류"],
    [{ status: "UNAVAILABLE", reason: "FRAME_UNSUPPORTED" }, "내부 프레임의 요소"],
    [{ status: "UNAVAILABLE", reason: "ISSUE_LIMIT_EXCEEDED" }, "표시 한도 초과"],
    [{ status: "HIDDEN_STATE", reason: "SOMETHING_NEW" }, "현재 숨겨진 요소"],
    [{ status: "UNAVAILABLE", reason: "toString" }, "위치를 확인하지 못함"],
    [{ status: "UNAVAILABLE" }, "위치를 확인하지 못함"]
  ] as const)("classifies %o as %s in the rail and the details", (state, label) => {
    expect(getLocatorLabel(state)).toBe(label);
    expect(getLocatorExplanation(state).label).toBe(label);
    expect(getLocatorExplanation(state).description.length).toBeGreaterThan(0);
  });
});
