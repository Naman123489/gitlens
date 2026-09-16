import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryScoreRow, ScoreDial, StatTile } from "@/components/score-card";
import { TooltipProvider } from "@/components/ui/tooltip";

describe("ScoreDial", () => {
  it("renders the score with an accessible label", () => {
    render(<ScoreDial value={87} label="Overall score" />);
    expect(screen.getByLabelText("Overall score: 87")).toBeInTheDocument();
  });

  it("renders an em dash when the score is unavailable", () => {
    render(<ScoreDial value={null} label="Overall score" />);
    expect(screen.getByLabelText("Overall score: —")).toBeInTheDocument();
  });
});

describe("StatTile", () => {
  it("renders a value with its suffix", () => {
    render(
      <TooltipProvider>
        <StatTile label="Ownership" value={88} suffix="%" />
      </TooltipProvider>,
    );
    expect(screen.getByText("Ownership")).toBeInTheDocument();
    expect(screen.getByText("88")).toBeInTheDocument();
  });
});

describe("CategoryScoreRow", () => {
  it("shows the weight and the confidence", () => {
    render(
      <CategoryScoreRow
        category="technical_quality"
        score={84}
        weight={0.2}
        confidence={0.9}
        available
      />,
    );
    expect(screen.getByText("Technical Quality")).toBeInTheDocument();
    expect(screen.getByText("20% weight")).toBeInTheDocument();
    expect(screen.getByText("90% confidence")).toBeInTheDocument();
  });

  it("explains why a dimension is unavailable instead of showing zero", () => {
    render(
      <CategoryScoreRow
        category="security"
        score={null}
        weight={0.05}
        confidence={0}
        available={false}
        unavailableReason="The security scanner timed out."
      />,
    );
    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.getByText("The security scanner timed out.")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
