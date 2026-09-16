import { FileQuestion } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="rounded-full border border-border bg-surface p-3">
        <FileQuestion className="size-5 text-muted-foreground" />
      </div>
      <div>
        <h1 className="text-lg font-semibold">Page not found</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          The page you are looking for does not exist or you do not have access to it.
        </p>
      </div>
      <Button asChild>
        <Link href="/">Back to RepoLens</Link>
      </Button>
    </div>
  );
}
