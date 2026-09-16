import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format a 0-100 score, or an em dash when it is genuinely unavailable. */
export function formatScore(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

/** Score bands drive colour everywhere, so they are defined once. */
export type ScoreBand = "strong" | "good" | "fair" | "weak" | "unknown";

export function scoreBand(value: number | null | undefined): ScoreBand {
  if (value === null || value === undefined || Number.isNaN(value)) return "unknown";
  if (value >= 80) return "strong";
  if (value >= 65) return "good";
  if (value >= 45) return "fair";
  return "weak";
}

export const SCORE_BAND_TEXT: Record<ScoreBand, string> = {
  strong: "text-success",
  good: "text-info",
  fair: "text-warning",
  weak: "text-danger",
  unknown: "text-muted-foreground",
};

export const SCORE_BAND_BG: Record<ScoreBand, string> = {
  strong: "bg-success",
  good: "bg-info",
  fair: "bg-warning",
  weak: "bg-danger",
  unknown: "bg-muted-foreground",
};

export const SCORE_BAND_HEX: Record<ScoreBand, string> = {
  strong: "#2bbd7e",
  good: "#38bdf8",
  fair: "#f5a524",
  weak: "#ef4444",
  unknown: "#94a3b8",
};

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "never";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "unknown";
  const seconds = Math.round((Date.now() - then) / 1000);
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"], [60, "minute"], [24, "hour"], [7, "day"], [4.345, "week"], [12, "month"],
  ];
  let amount = seconds;
  let unit: Intl.RelativeTimeFormatUnit = "second";
  for (const [size, nextUnit] of units) {
    if (Math.abs(amount) < size) break;
    amount = Math.round(amount / size);
    unit = nextUnit;
  }
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(-amount, unit);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
