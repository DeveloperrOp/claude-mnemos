import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "../stores/ui.store";

beforeEach(() => {
  // Reset stores to initial state before each test
  useUIStore.setState({
    sidebarCollapsed: false,
    locale: "uk",
    theme: "light",
  });
});

describe("ui store", () => {
  it("toggleSidebar flips sidebarCollapsed", () => {
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it("setLocale updates locale", () => {
    expect(useUIStore.getState().locale).toBe("uk");
    useUIStore.getState().setLocale("en");
    expect(useUIStore.getState().locale).toBe("en");
    useUIStore.getState().setLocale("ru");
    expect(useUIStore.getState().locale).toBe("ru");
  });
});
