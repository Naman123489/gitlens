import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidencePanel, LimitationsPanel } from "@/components/evidence-panel";
import type { Evidence } from "@/lib/types";

const evidence: Evidence[] = [
  {
    evidence_id: "ev_1",
    category: "testing",
    claim: "No integration test suite was detected",
    severity: "medium",
    confidence: 0.75,
    supports: "weakness",
    tags: [],
    details: [
      { detail: "no test path matching integration naming conventions", file: "tests/" },
    ],
    analyzer: "testing",
  },
  {
    evidence_id: "ev_2",
    category: "ai_utilization",
    claim: "Style discontinuity between files",
    severity: "low",
    confidence: 0.4,
    supports: "neutral",
    tags: ["signal_only"],
    details: [{ detail: "app/x.py deviates 2.1σ from the repository baseline" }],
    analyzer: "ai_usage",
  },
];

describe("EvidencePanel", () => {
  it("shows every claim with its confidence", () => {
    render(<EvidencePanel evidence={evidence} />);
    expect(screen.getByText("No integration test suite was detected")).toBeInTheDocument();
    expect(screen.getByText("75% confidence")).toBeInTheDocument();
  });

  it("marks signal-only evidence so it is not read as proof", () => {
    render(<EvidencePanel evidence={evidence} />);
    expect(screen.getByText("signal, not proof")).toBeInTheDocument();
  });

  it("reveals the underlying observations when a claim is expanded", () => {
    render(<EvidencePanel evidence={evidence} />);
    const detail = "no test path matching integration naming conventions";
    expect(screen.queryByText(detail)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("No integration test suite was detected"));
    expect(screen.getByText(detail)).toBeInTheDocument();
    expect(screen.getByText("tests/")).toBeInTheDocument();
  });

  it("renders an empty state rather than nothing", () => {
    render(<EvidencePanel evidence={[]} />);
    expect(screen.getByText("No evidence")).toBeInTheDocument();
  });
});

describe("LimitationsPanel", () => {
  it("renders limitations and de-duplicates repeats", () => {
    render(
      <LimitationsPanel
        limitations={[
          { scope: "coverage", detail: "Line coverage is not measured." },
          { scope: "coverage", detail: "Line coverage is not measured." },
          { scope: "ai_detection", detail: "This figure is a probabilistic estimate." },
        ]}
      />,
    );
    expect(screen.getAllByText("Line coverage is not measured.")).toHaveLength(1);
    expect(screen.getByText("This figure is a probabilistic estimate.")).toBeInTheDocument();
  });

  it("renders nothing when there are no limitations", () => {
    const { container } = render(<LimitationsPanel limitations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
