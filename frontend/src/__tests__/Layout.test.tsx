import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { Layout } from "../components/layout/Layout";

describe("Layout", () => {
  it("renders TopBar slot, Sidebar slot, and Outlet content", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<div>page-body</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("banner")).toBeInTheDocument(); // TopBar = <header>
    expect(screen.getByRole("navigation")).toBeInTheDocument(); // Sidebar = <nav>
    expect(screen.getByText("page-body")).toBeInTheDocument();
  });
});
