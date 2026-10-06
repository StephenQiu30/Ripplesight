import { describe, expect, it } from "vitest";
import {
  confidenceLabel,
  supportScoreValue,
} from "@/components/leaderboard/board-format";
import {
  boardHref,
  boardTabs,
  filteredBoardHref,
} from "@/components/leaderboard/board-navigation";
import { board } from "./fixtures";

describe("fixed support-index scale", () => {
  it.each([
    [0, 0],
    [69.4, 69.4],
    [100, 100],
    [-1, 0],
    [101, 100],
    [NaN, 0],
    [Infinity, 0],
  ])(
    "maps %s safely to %s without rescaling the visible leader",
    (score, expected) => {
      expect(supportScoreValue(score)).toBe(expected);
    },
  );
  it.each([
    ["HIGH", "证据覆盖较高"],
    ["MEDIUM", "证据覆盖有限"],
    ["LOW", "证据有限"],
  ] as const)(
    "labels %s evidence without confusing it with rank change",
    (confidence, label) => {
      expect(
        confidenceLabel({ ...board.entries[0], stability: null, confidence }),
      ).toBe(label);
    },
  );
  it("gives evidence sensitivity precedence", () => {
    expect(confidenceLabel({ ...board.entries[0], confidence: "HIGH" })).toBe(
      "对证据变化敏感",
    );
  });
});

describe("existing board routes and filters", () => {
  it.each(boardTabs)("keeps $key at $href", ({ key, href }) => {
    expect(boardHref(key)).toBe(href);
    expect(boardHref(key, true, true)).toBe(
      `${href}?domestic=true&open_weights=true`,
    );
  });
  it("keeps either filter and clears false values", () => {
    expect(boardHref("overall", true, false)).toBe(
      "/leaderboard?domestic=true",
    );
    expect(boardHref("coding", false, true)).toBe(
      "/leaderboard/category/coding?open_weights=true",
    );
    expect(filteredBoardHref("/leaderboard", false, false)).toBe(
      "/leaderboard",
    );
  });
});
