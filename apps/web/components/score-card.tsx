import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import * as React from "react";

import { Progress } from "@/components/ui/progress";
import { Tooltip } from "@/components/ui/tooltip";
import { cn, formatScore, SCORE_BAND_BG, SCORE_BAND_TEXT, scoreBand, titleCase } from "@/lib/utils";

export function ScoreDial({
  value,
  label,
  size = 120,
  suffix = "",
}: {
  value: number | null;
  label?: string;
  size?: number;
  suffix?: string;
}) {
  const band = scoreBand(value);
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const fraction = value === null ? 0 : Math.max(0, Math.min(100, value)) / 100;

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} role="img" aria-label={`${label ?? "Score"}: ${formatScore(value)}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={8}
          className="stroke-muted"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className={cn("transition-[stroke-dashoffset] duration-700", {
            "stroke-success": band === "strong",
            "stroke-info": band === "good",
            "stroke-warning": band === "fair",
            "stroke-danger": band === "weak",
            "stroke-muted-foreground": band === "unknown",
          })}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="middle"
          textAnchor="middle"
          className={cn("fill-current font-semibold", SCORE_BAND_TEXT[band])}
          style={{ fontSize: size / 3.6 }}
        >
          {formatScore(value)}
          {value !== null ? suffix : ""}
        </text>
      </svg>
      {label ? <p className="text-xs text-muted-foreground">{label}</p> : null}
    </div>
  );
}

export function StatTile({
  label,
  value,
  suffix,
  help,
  trend,
  footer,
}: {
  label: string;
  value: number | string | null;
  suffix?: string;
  help?: string;
  trend?: "up" | "down" | "flat";
  footer?: React.ReactNode;
}) {
  const numeric = typeof value === "number" ? value : null;
  const band = scoreBand(numeric);
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;

  const content = (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {trend ? <TrendIcon className="size-3.5 text-muted-foreground" /> : null}
      </div>
      <p className={cn("mt-2 text-2xl font-semibold tabular-nums", numeric !== null ? SCORE_BAND_TEXT[band] : "")}>
        {typeof value === "number" ? formatScore(value) : (value ?? "—")}
        {value !== null && value !== undefined && suffix ? (
          <span className="ml-0.5 text-sm font-normal text-muted-foreground">{suffix}</span>
        ) : null}
      </p>
      {footer ? <div className="mt-2 text-xs text-muted-foreground">{footer}</div> : null}
    </div>
  );

  return help ? <Tooltip content={help}>{content}</Tooltip> : content;
}

export function CategoryScoreRow({
  category,
  score,
  weight,
  confidence,
  available,
  unavailableReason,
  onClick,
  active,
}: {
  category: string;
  score: number | null;
  weight: number;
  confidence: number;
  available: boolean;
  unavailableReason?: string | null;
  onClick?: () => void;
  active?: boolean;
}) {
  const band = scoreBand(available ? score : null);
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        "w-full rounded-md px-3 py-2.5 text-left transition-colors",
        onClick ? "hover:bg-muted/50" : "cursor-default",
        active && "bg-muted/60",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{titleCase(category)}</span>
        <span className="flex items-baseline gap-2">
          <span className="text-[11px] text-muted-foreground">{Math.round(weight * 100)}% weight</span>
          <span className={cn("text-sm font-semibold tabular-nums", SCORE_BAND_TEXT[band])}>
            {available ? formatScore(score) : "n/a"}
          </span>
        </span>
      </div>
      <Progress
        value={available && score !== null ? score : 0}
        className="mt-2"
        indicatorClassName={SCORE_BAND_BG[band]}
        label={`${titleCase(category)} score`}
      />
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        {available
          ? `${Math.round(confidence * 100)}% confidence`
          : (unavailableReason ?? "Not available for this repository.")}
      </p>
    </button>
  );
}
