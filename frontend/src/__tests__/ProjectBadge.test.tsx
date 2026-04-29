import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { ProjectBadge } from "../components/widgets/ProjectBadge";

describe("ProjectBadge", () => {
  it("renders project name", () => {
    render(
      <MemoryRouter>
        <ProjectBadge name="alpha" />
      </MemoryRouter>,
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });

  it("links to project view by default", () => {
    render(
      <MemoryRouter>
        <ProjectBadge name="alpha" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "alpha" })).toHaveAttribute(
      "href",
      "/project/alpha",
    );
  });

  it("renders as plain span when linkTo=false", () => {
    render(<ProjectBadge name="alpha" linkTo={false} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });
});
