import { AlertTriangle, CircleHelp, ShieldCheck, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import type { AIClassification, VerificationStatus } from "@/lib/types";

const VERIFICATION: Record<
  VerificationStatus,
  { label: string; variant: "success" | "warning" | "danger" | "default"; help: string }
> = {
  CLEAR: {
    label: "Clear",
    variant: "success",
    help: "No ownership, similarity or completeness concerns were raised by the analysis.",
  },
  REVIEW_RECOMMENDED: {
    label: "Review recommended",
    variant: "warning",
    help: "Something is worth a short conversation. This is not a negative finding.",
  },
  VERIFICATION_REQUIRED: {
    label: "Verification required",
    variant: "danger",
    help:
      "The evidence available is not sufficient to establish ownership from artefacts alone. " +
      "This asks for a conversation with the candidate — it is not a rejection and not an " +
      "accusation.",
  },
  ANALYSIS_INCOMPLETE: {
    label: "Analysis incomplete",
    variant: "default",
    help: "Too few dimensions could be computed to draw a conclusion. Re-run the analysis.",
  },
};

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const config = VERIFICATION[status] ?? VERIFICATION.ANALYSIS_INCOMPLETE;
  const Icon = status === "CLEAR" ? ShieldCheck : status === "ANALYSIS_INCOMPLETE" ? CircleHelp : AlertTriangle;
  return (
    <Tooltip content={config.help}>
      <Badge variant={config.variant} className="cursor-help">
        <Icon className="size-3" />
        {config.label}
      </Badge>
    </Tooltip>
  );
}

const AI_CLASSIFICATION: Record<AIClassification, { label: string; help: string }> = {
  AI_ASSISTED: {
    label: "AI-assisted",
    help: "Signals are consistent with AI used for support tasks, with ownership demonstrated.",
  },
  AI_AUGMENTED: {
    label: "AI-augmented",
    help: "Signals suggest generated components that the candidate integrated and maintained.",
  },
  AI_DEPENDENT: {
    label: "AI-dependent",
    help: "Assistance signals are substantial and ownership evidence is limited. A conversation is recommended.",
  },
  AI_DOMINATED: {
    label: "AI-dominated",
    help: "Evidence suggests substantial dependence on generated code with limited evidence of candidate-authored development. This is a prompt for verification, not a conclusion about the candidate.",
  },
  INSUFFICIENT_EVIDENCE: {
    label: "Insufficient evidence",
    help: "There was not enough evidence to characterise how this repository was built.",
  },
};

export function AIClassificationBadge({
  classification,
  likelihood,
}: {
  classification: AIClassification | null;
  likelihood?: number | null;
}) {
  if (!classification) return <Badge>Not assessed</Badge>;
  const config = AI_CLASSIFICATION[classification];
  const variant =
    classification === "AI_ASSISTED" || classification === "AI_AUGMENTED" ? "info" : "warning";
  return (
    <Tooltip
      content={
        <span>
          {config.help}
          {typeof likelihood === "number" ? (
            <span className="mt-1 block text-muted-foreground">
              Estimated assistance likelihood {likelihood.toFixed(0)}/100. This is a probabilistic
              estimate from repository signals, not a determination that any code was AI-generated.
            </span>
          ) : null}
        </span>
      }
    >
      <Badge variant={variant} className="cursor-help">
        <Sparkles className="size-3" />
        {config.label}
      </Badge>
    </Tooltip>
  );
}

const SEVERITY_VARIANT: Record<string, "default" | "info" | "warning" | "danger"> = {
  info: "info",
  low: "default",
  medium: "warning",
  high: "danger",
  critical: "danger",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge variant={SEVERITY_VARIANT[severity] ?? "default"}>{severity.toUpperCase()}</Badge>;
}

export function ConfidenceLabel({ value }: { value: number }) {
  const band = value >= 0.78 ? "high" : value >= 0.55 ? "medium" : value >= 0.35 ? "low" : "very low";
  return (
    <Tooltip content="Confidence in this measurement, based on how much evidence was available.">
      <span className="cursor-help text-xs text-muted-foreground">
        {band} confidence ({Math.round(value * 100)}%)
      </span>
    </Tooltip>
  );
}
