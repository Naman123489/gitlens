"use client";

import { AlertTriangle } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  React.useEffect(() => {
    // eslint-disable-next-line no-console
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="rounded-full border border-danger/30 bg-danger/10 p-3">
        <AlertTriangle className="size-5 text-danger" />
      </div>
      <div>
        <h1 className="text-lg font-semibold">Something went wrong</h1>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">
          {error.message || "An unexpected error occurred while rendering this page."}
        </p>
        {error.digest ? (
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">digest {error.digest}</p>
        ) : null}
      </div>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
