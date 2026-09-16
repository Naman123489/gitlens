import { describe, expect, it } from "vitest";

import { formatPercent, formatScore, scoreBand, titleCase } from "@/lib/utils";

describe("formatScore", () => {
  it("renders an em dash for a genuinely missing score", () => {
    // A missing score must never render as 0: unavailable and zero mean
    // different things throughout the product.
    expect(formatScore(null)).toBe("—");
    expect(formatScore(undefined)).toBe("—");
    expect(formatScore(Number.NaN)).toBe("—");
  });

  it("rounds to the requested precision", () => {
    expect(formatScore(87.456)).toBe("87");
    expect(formatScore(87.456, 1)).toBe("87.5");
    expect(formatScore(0)).toBe("0");
  });

  it("formats percentages", () => {
    expect(formatPercent(42.4)).toBe("42%");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("scoreBand", () => {
  it("bands scores consistently", () => {
    expect(scoreBand(92)).toBe("strong");
    expect(scoreBand(70)).toBe("good");
    expect(scoreBand(50)).toBe("fair");
    expect(scoreBand(20)).toBe("weak");
  });

  it("treats an absent score as unknown rather than weak", () => {
    expect(scoreBand(null)).toBe("unknown");
    expect(scoreBand(undefined)).toBe("unknown");
  });
});

describe("titleCase", () => {
  it("humanises category keys", () => {
    expect(titleCase("technical_quality")).toBe("Technical Quality");
    expect(titleCase("ai_utilization")).toBe("Ai Utilization");
    expect(titleCase("git-engineering")).toBe("Git Engineering");
  });
});
