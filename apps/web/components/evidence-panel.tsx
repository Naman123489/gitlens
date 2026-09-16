"use client";

import { ChevronDown, FileCode2, Minus, ThumbsDown, ThumbsUp } from "lucide-react";
import * as React from "react";

import { SeverityBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import type { Evidence } from "@/lib/types";
import { cn, titleCase } from "@/lib/utils";

/**
 * Renders the evidence behind a score. Every claim is expandable to its raw
 * observations, because a score a reviewer cannot check is not usable.
 */
export function EvidencePanel({
  evidence,
  emptyMessage = "No evidence was recorded for this dimension.",
  defaultOpen = false,
}: {
  evidence: Evidence[];
  emptyMessage?: string;
  defaultOpen?: boolean;
}) {
  if (evidence.length === 0) {
    return <EmptyState icon={FileCode2} title="No evidence" description={emptyMessage} />;
  }
  return (
    <ul className="space-y-2">
      {evidence.map((item) => (
        <EvidenceItem key={item.evidence_id} item={item} defaultOpen={defaultOpen} />
      ))}
    </ul>
  );
}

function EvidenceItem({ item, defaultOpen }: { item: Evidence; defaultOpen: boolean }) {
  const [open, setOpen] = React.useState(defaultOpen);
  const Icon = item.supports === "strength" ? ThumbsUp : item.supports === "weakness" ? ThumbsDown : Minus;
  const tone =
    item.supports === "strength"
      ? "text-success"
      : item.supports === "weakness"
        ? "text-warning"
        : "text-muted-foreground";

  return (
    <li className="panel-raised overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40"
      >
        <Icon className={cn("mt-0.5 size-4 shrink-0", tone)} />
        <span className="flex-1 space-y-1">
          <span className="block text-sm leading-snug">{item.claim}</span>
          <span className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{titleCase(item.category)}</Badge>
            {item.severity !== "info" ? <SeverityBadge severity={item.severity} /> : null}
            <span className="text-[11px] text-muted-foreground">
              {Math.round(item.confidence * 100)}% confidence
            </span>
            {item.tags.includes("signal_only") ? (
              <Badge variant="outline" className="text-[10px]">
                signal, not proof
              </Badge>
            ) : null}
          </span>
        </span>
        <ChevronDown
          className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <div className="border-t border-border bg-surface px-4 py-3">
          {item.details.length === 0 ? (
            <p className="text-xs text-muted-foreground">No further detail was recorded.</p>
          ) : (
            <ul className="space-y-2">
              {item.details.map((detail, index) => (
                <li key={index} className="text-xs leading-relaxed">
                  <span className="text-foreground">{detail.detail}</span>
                  {detail.file ? (
                    <span className="ml-1 font-mono text-[11px] text-muted-foreground">
                      {detail.file}
                      {detail.line ? `:${detail.line}` : ""}
                    </span>
                  ) : null}
                  {detail.snippet ? (
                    <pre className="mt-1 overflow-x-auto rounded border border-border bg-background px-2 py-1 font-mono text-[11px] text-muted-foreground">
                      {detail.snippet}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[10px] uppercase tracking-wide text-muted-foreground">
            analyzer: {item.analyzer || "unknown"}
          </p>
        </div>
      ) : null}
    </li>
  );
}

/** Limitations must be visible wherever scores are, not buried in a footer. */
export function LimitationsPanel({
  limitations,
}: {
  limitations: { scope: string; detail: string; analyzer?: string }[];
}) {
  if (limitations.length === 0) return null;
  const unique = Array.from(new Map(limitations.map((l) => [l.detail, l])).values());
  return (
    <div className="space-y-2">
      {unique.map((limitation, index) => (
        <div key={index} className="rounded-md border border-border bg-surface px-3 py-2">
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {titleCase(limitation.scope)}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{limitation.detail}</p>
        </div>
      ))}
    </div>
  );
}
