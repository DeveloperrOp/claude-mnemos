import { describe, it, expect, vi, afterEach } from "vitest";

// Mock HttpBackend so i18n never makes real HTTP requests.
vi.mock("i18next-http-backend", () => ({
  default: {
    type: "backend" as const,
    init: vi.fn(),
    read: vi.fn((_lng: string, _ns: string, callback: (err: null, data: null) => void) => {
      callback(null, null);
    }),
  },
}));

afterEach(() => {
  localStorage.removeItem("mnemos:locale");
});

describe("i18n cold start", () => {
  it("seeds the initial language synchronously from the localStorage cache", async () => {
    // FOUC regression: seeding via changeLanguage() after init let uk.json
    // win the fetch race and paint Ukrainian first on a saved-RU profile.
    // This is the file's FIRST ../i18n import, so init() sees the cache —
    // exactly like a browser cold start.
    localStorage.setItem("mnemos:locale", "ru");
    const { default: i18n } = await import("../i18n");
    if (!i18n.isInitialized) {
      await new Promise<void>((resolve) => i18n.on("initialized", () => resolve()));
    }
    expect(i18n.language).toBe("ru");
  });

  it("falls back to uk when no cache exists", async () => {
    const { initialLng } = await import("../i18n");
    expect(initialLng()).toBe("uk");
  });

  it("ignores junk cache values", async () => {
    const { initialLng } = await import("../i18n");
    localStorage.setItem("mnemos:locale", "de");
    expect(initialLng()).toBe("uk");
  });
});
