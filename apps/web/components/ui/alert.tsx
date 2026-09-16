import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const TONES = {
  info: { border: "border-info/30", bg: "bg-info/10", text: "text-info", Icon: Info },
  success: { border: "border-success/30", bg: "bg-success/10", text: "text-success", Icon: CheckCircle2 },
  warning: { border: "border-warning/30", bg: "bg-warning/10", text: "text-warning", Icon: AlertTriangle },
  danger: { border: "border-danger/30", bg: "bg-danger/10", text: "text-danger", Icon: ShieldAlert },
} as const;

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: keyof typeof TONES;
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const { border, bg, text, Icon } = TONES[tone];
  return (
    <div className={cn("flex gap-3 rounded-lg border p-3", border, bg, className)} role="status">
      <Icon className={cn("mt-0.5 size-4 shrink-0", text)} />
      <div className="space-y-1 text-xs leading-relaxed">
        {title ? <p className={cn("font-medium", text)}>{title}</p> : null}
        {children ? <div className="text-muted-foreground">{children}</div> : null}
      </div>
    </div>
  );
}
