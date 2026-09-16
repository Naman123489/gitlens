import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AIClassificationBadge, VerificationBadge } from "@/components/status";
import { TooltipProvider } from "@/components/ui/tooltip";

function renderWithTooltips(ui: React.ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("VerificationBadge", () => {
  it("labels each status in non-accusatory language", () => {
    const { rerender } = renderWithTooltips(<VerificationBadge status="CLEAR" />);
    expect(screen.getByText("Clear")).toBeInTheDocument();

    rerender(
      <TooltipProvider>
        <VerificationBadge status="VERIFICATION_REQUIRED" />
      </TooltipProvider>,
    );
    const label = screen.getByText("Verification required");
    expect(label).toBeInTheDocument();
    // The product forbids a rejection status; the UI must not invent one.
    expect(label.textContent?.toLowerCase()).not.toContain("reject");
  });

  it("falls back to incomplete for an unknown status", () => {
    renderWithTooltips(<VerificationBadge status={"SOMETHING_ELSE" as never} />);
    expect(screen.getByText("Analysis incomplete")).toBeInTheDocument();
  });
});

describe("AIClassificationBadge", () => {
  it("renders the classification label", () => {
    renderWithTooltips(<AIClassificationBadge classification="AI_AUGMENTED" likelihood={62} />);
    expect(screen.getByText("AI-augmented")).toBeInTheDocument();
  });

  it("says nothing was assessed when there is no classification", () => {
    renderWithTooltips(<AIClassificationBadge classification={null} />);
    expect(screen.getByText("Not assessed")).toBeInTheDocument();
  });
});
