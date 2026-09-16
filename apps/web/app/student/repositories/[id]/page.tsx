"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";

import { Button } from "@/components/ui/button";
import { RepositoryDetail } from "@/features/repository-detail";

export default function StudentRepositoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" asChild className="-ml-2">
        <Link href="/student/repositories">
          <ArrowLeft className="size-4" />
          All repositories
        </Link>
      </Button>
      <RepositoryDetail repositoryId={id} />
    </div>
  );
}
