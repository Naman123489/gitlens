"use client";

import * as React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { SCORE_BAND_HEX, scoreBand, titleCase } from "@/lib/utils";

const AXIS = { stroke: "hsl(215 14% 45%)", fontSize: 11 };
const GRID = "hsl(223 12% 20%)";

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-surface-raised px-3 py-2 text-xs shadow-lg">
      {label ? <p className="mb-1 font-medium">{titleCase(String(label))}</p> : null}
      {payload.map((entry: any) => (
        <p key={entry.dataKey} className="text-muted-foreground">
          {titleCase(String(entry.name))}:{" "}
          <span className="font-medium text-foreground">
            {typeof entry.value === "number" ? entry.value.toFixed(0) : entry.value}
          </span>
        </p>
      ))}
    </div>
  );
}

/** Engineering DNA: evidence strength per dimension. */
export function DnaRadar({ data }: { data: Record<string, number> }) {
  const points = Object.entries(data).map(([key, value]) => ({
    dimension: titleCase(key),
    value: Math.round(value),
  }));
  if (points.length === 0) return null;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={points} outerRadius="72%">
        <PolarGrid stroke={GRID} />
        <PolarAngleAxis dataKey="dimension" tick={{ ...AXIS, fontSize: 10 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        <Radar
          name="Evidence"
          dataKey="value"
          stroke="hsl(217 91% 60%)"
          fill="hsl(217 91% 60%)"
          fillOpacity={0.25}
          isAnimationActive={false}
        />
        <RechartsTooltip content={<ChartTooltip />} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

/** Category scores, coloured by band so weak dimensions are obvious. */
export function CategoryBars({
  data,
}: {
  data: { category: string; score: number | null; available: boolean }[];
}) {
  const points = data
    .filter((item) => item.available && item.score !== null)
    .map((item) => ({ category: titleCase(item.category), score: Math.round(item.score ?? 0) }));
  if (points.length === 0) return null;
  return (
    <ResponsiveContainer width="100%" height={Math.max(200, points.length * 34)}>
      <BarChart data={points} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={AXIS} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="category" width={132} tick={AXIS} axisLine={false} tickLine={false} />
        <RechartsTooltip content={<ChartTooltip />} cursor={{ fill: "hsl(223 12% 16% / 0.5)" }} />
        <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false}>
          {points.map((point) => (
            <Cell key={point.category} fill={SCORE_BAND_HEX[scoreBand(point.score)]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Commit activity over the project's lifetime. */
export function ActivityTimeline({
  data,
}: {
  data: { start: string; commits: number; lines: number }[];
}) {
  if (!data?.length) return null;
  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ left: -20, right: 8, top: 8 }}>
        <defs>
          <linearGradient id="commitFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(217 91% 60%)" stopOpacity={0.5} />
            <stop offset="100%" stopColor="hsl(217 91% 60%)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="start" tick={AXIS} axisLine={false} tickLine={false} minTickGap={32} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} width={44} />
        <RechartsTooltip content={<ChartTooltip />} />
        <Area
          type="monotone"
          dataKey="commits"
          name="Commits"
          stroke="hsl(217 91% 60%)"
          fill="url(#commitFill)"
          strokeWidth={2}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Job readiness across role archetypes. */
export function ReadinessBars({ data }: { data: { role: string; readiness: number }[] }) {
  if (!data?.length) return null;
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 40)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={AXIS} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="role" width={140} tick={AXIS} axisLine={false} tickLine={false} />
        <RechartsTooltip content={<ChartTooltip />} cursor={{ fill: "hsl(223 12% 16% / 0.5)" }} />
        <Bar dataKey="readiness" name="Readiness" radius={[0, 4, 4, 0]} barSize={16} isAnimationActive={false}>
          {data.map((point) => (
            <Cell key={point.role} fill={SCORE_BAND_HEX[scoreBand(point.readiness)]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
