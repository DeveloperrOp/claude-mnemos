import { describe, it, expect, beforeEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { apiClient } from "../api/client";
import { TrayStatusSchema } from "../types/Tray";
import { getTrayStatus, installTray, uninstallTray } from "../api/tray.api";

let mock: MockAdapter;

beforeEach(() => {
  // Mock the apiClient instance — production calls go through it.
  // baseURL is /api, so .onGet("/tray/status") matches the relative path.
  mock = new MockAdapter(apiClient);
});

describe("tray API", () => {
  it("GET /tray/status parses with zod schema", async () => {
    mock.onGet("/tray/status").reply(200, {
      platform: "windows",
      autostart_enabled: true,
      autostart_path: "C:\\X\\Mnemos.lnk",
      tray_running: true,
      tray_pid: 1234,
      daemon_pid: 5678,
    });
    const status = await getTrayStatus();
    expect(status.platform).toBe("windows");
    expect(status.autostart_enabled).toBe(true);
  });

  it("POST /tray/install returns installed=true", async () => {
    mock.onPost("/tray/install").reply(200, { installed: true });
    const res = await installTray();
    expect(res.installed).toBe(true);
  });

  it("POST /tray/uninstall returns installed=false", async () => {
    mock.onPost("/tray/uninstall").reply(200, { installed: false });
    const res = await uninstallTray();
    expect(res.installed).toBe(false);
  });

  it("TrayStatusSchema permissive: missing optional fields default", () => {
    const parsed = TrayStatusSchema.parse({
      platform: "macos",
      autostart_enabled: false,
    });
    expect(parsed.autostart_path).toBeNull();
    expect(parsed.tray_pid).toBeNull();
  });
});
