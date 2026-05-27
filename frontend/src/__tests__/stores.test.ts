import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "../stores/ui.store";

beforeEach(() => {
  useUIStore.setState({ sidebarCollapsed: false, theme: "light" });
});

describe("ui store", () => {
  it("toggleSidebar flips sidebarCollapsed", () => {
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it("setTheme updates theme", () => {
    expect(useUIStore.getState().theme).toBe("light");
    useUIStore.getState().setTheme("dark");
    expect(useUIStore.getState().theme).toBe("dark");
  });
});
