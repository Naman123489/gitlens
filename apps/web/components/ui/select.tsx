import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A native select, styled. Deliberately not a Radix listbox: a plain select is
 * keyboard- and screen-reader-correct for free and works without JavaScript.
 */
export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "h-9 w-full rounded-md border border-input bg-surface px-3 text-sm text-foreground shadow-sm",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";
