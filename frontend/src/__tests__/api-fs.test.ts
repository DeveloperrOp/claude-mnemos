import { describe, it, expect, beforeEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import { browseDirectory, listDrives, mkdir, getHome } from "../api/fs.api";

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
});

describe("fs API", () => {
  it("getHome returns absolute path", async () => {
    mock.onGet("/fs/home").reply(200, { home: "C:\\Users\\test" });
    const result = await getHome();
    expect(result.home).toBe("C:\\Users\\test");
  });

  it("browseDirectory returns entries + parent", async () => {
    mock.onGet(/\/fs\/browse/).reply(200, {
      cwd: "C:\\code",
      parent: "C:\\",
      entries: [
        { name: "claude-mnemos", path: "C:\\code\\claude-mnemos" },
        { name: "test", path: "C:\\code\\test" },
      ],
      truncated: false,
    });
    const result = await browseDirectory("C:\\code");
    expect(result.entries).toHaveLength(2);
    expect(result.parent).toBe("C:\\");
    expect(result.truncated).toBe(false);
  });

  it("browseDirectory passes path as query param", async () => {
    mock.onGet(/\/fs\/browse/).reply((config) => {
      expect(config.params).toEqual({ path: "/tmp/x" });
      return [200, { cwd: "/tmp/x", parent: "/tmp", entries: [], truncated: false }];
    });
    await browseDirectory("/tmp/x");
  });

  it("mkdir POSTs path and returns resolved path", async () => {
    mock.onPost("/fs/mkdir").reply((config) => {
      expect(JSON.parse(config.data as string)).toEqual({ path: "/tmp/new" });
      return [200, { path: "/tmp/new" }];
    });
    const result = await mkdir("/tmp/new");
    expect(result.path).toBe("/tmp/new");
  });

  it("browseDirectory schema permissive — truncated defaults to false", async () => {
    mock.onGet(/\/fs\/browse/).reply(200, {
      cwd: "/tmp",
      parent: null,
      entries: [],
    });
    const result = await browseDirectory("/tmp");
    expect(result.truncated).toBe(false);
    expect(result.parent).toBeNull();
  });

  it("listDrives returns array of drives", async () => {
    mock.onGet("/fs/drives").reply(200, {
      drives: [
        { name: "C:", path: "C:\\" },
        { name: "D:", path: "D:\\" },
      ],
    });
    const result = await listDrives();
    expect(result.drives).toHaveLength(2);
    expect(result.drives[0].path).toBe("C:\\");
  });

  it("browseDirectory passes include_files=true when opts.includeFiles", async () => {
    mock.onGet(/\/fs\/browse/).reply((config) => {
      expect(config.params).toEqual({ path: "/tmp", include_files: true });
      return [200, { cwd: "/tmp", parent: null, entries: [], truncated: false }];
    });
    await browseDirectory("/tmp", { includeFiles: true });
  });
});
