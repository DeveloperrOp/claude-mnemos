import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "../stores/ui.store";
import { useNotificationsStore } from "../stores/notifications.store";

beforeEach(() => {
  // Reset stores to initial state before each test
  useUIStore.setState({
    sidebarCollapsed: false,
    locale: "uk",
    theme: "light",
  });
  useNotificationsStore.setState({ toasts: [] });
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

describe("notifications store", () => {
  it("push adds a toast and returns its id", () => {
    const id = useNotificationsStore.getState().push({
      kind: "info",
      title: "Hello",
      description: "world",
    });
    const { toasts } = useNotificationsStore.getState();
    expect(toasts).toHaveLength(1);
    expect(toasts[0]?.id).toBe(id);
    expect(toasts[0]?.kind).toBe("info");
    expect(toasts[0]?.title).toBe("Hello");
    expect(toasts[0]?.description).toBe("world");
  });

  it("dismiss removes the toast with the given id", () => {
    const id1 = useNotificationsStore.getState().push({ kind: "success", title: "A" });
    const id2 = useNotificationsStore.getState().push({ kind: "error", title: "B" });
    expect(useNotificationsStore.getState().toasts).toHaveLength(2);

    useNotificationsStore.getState().dismiss(id1);
    const { toasts } = useNotificationsStore.getState();
    expect(toasts).toHaveLength(1);
    expect(toasts[0]?.id).toBe(id2);
  });
});
