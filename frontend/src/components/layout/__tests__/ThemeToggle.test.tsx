import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "next-themes";
import { ThemeToggle } from "../ThemeToggle";

beforeEach(() => {
  // next-themes uses localStorage; clean between tests.
  localStorage.clear();
});

function wrap(ui: React.ReactNode) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      {ui}
    </ThemeProvider>
  );
}

describe("ThemeToggle", () => {
  it("renders an aria-labeled toggle button", () => {
    render(wrap(<ThemeToggle />));
    expect(screen.getByRole("button", { name: /theme/i })).toBeInTheDocument();
  });

  it("cycles light → dark → system on click", async () => {
    const user = userEvent.setup();
    render(wrap(<ThemeToggle />));
    const btn = screen.getByRole("button", { name: /theme/i });
    // initial = system; click → light
    await user.click(btn);
    expect(localStorage.getItem("theme")).toBe("light");
    await user.click(btn);
    expect(localStorage.getItem("theme")).toBe("dark");
    await user.click(btn);
    expect(localStorage.getItem("theme")).toBe("system");
  });
});
