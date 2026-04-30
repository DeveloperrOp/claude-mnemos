import { describe, it, expect, beforeAll, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import axios from "axios";
import i18n from "../i18n";
import { DirectoryPicker } from "../components/picker/DirectoryPicker";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    picker: {
      title: "Choose folder",
      path_placeholder: "Type or paste path",
      filter_placeholder: "Filter folders…",
      recent: "Recent",
      loading: "Loading…",
      empty: "No subfolders",
      truncated: "Showing first 100 — refine filter to narrow",
      new_folder: "New folder",
      folder_name: "Folder name",
      create: "Create",
      cancel: "Cancel",
      select: "Select this folder",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

let mock: MockAdapter;

beforeEach(() => {
  mock = new MockAdapter(axios);
  localStorage.clear();
});

const TEST_HOME = "C:\\Users\\test";

function setupMock() {
  mock.onGet("/fs/home").reply(200, { home: TEST_HOME });
  mock.onGet(/\/fs\/browse/).reply((config) => {
    const path = (config.params as { path: string }).path;
    if (path === TEST_HOME) {
      return [
        200,
        {
          cwd: TEST_HOME,
          parent: "C:\\Users",
          entries: [
            { name: "code", path: `${TEST_HOME}\\code` },
            { name: "Documents", path: `${TEST_HOME}\\Documents` },
          ],
          truncated: false,
        },
      ];
    }
    if (path === `${TEST_HOME}\\code`) {
      return [
        200,
        {
          cwd: `${TEST_HOME}\\code`,
          parent: TEST_HOME,
          entries: [
            { name: "claude-mnemos", path: `${TEST_HOME}\\code\\claude-mnemos` },
          ],
          truncated: false,
        },
      ];
    }
    return [400, { detail: "path does not exist" }];
  });
}

// Entry buttons render as `📁 {name}`, so combined textContent is `📁 code`
// (with a leading emoji + space). Use a regex that matches a trailing folder
// name to query them via testing-library, which compares against textContent.
const folderEntry = (name: string) => new RegExp(`📁\\s*${name}$`);

describe("DirectoryPicker", () => {
  it("opens at home and lists entries", async () => {
    setupMock();
    const onSelect = vi.fn();
    render(<DirectoryPicker open onSelect={onSelect} onClose={() => {}} />);
    expect(await screen.findByText(folderEntry("code"))).toBeInTheDocument();
    expect(screen.getByText(folderEntry("Documents"))).toBeInTheDocument();
  });

  it("navigates into folder on click", async () => {
    setupMock();
    render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} />);
    const codeFolder = await screen.findByText(folderEntry("code"));
    await userEvent.click(codeFolder);
    expect(await screen.findByText(folderEntry("claude-mnemos"))).toBeInTheDocument();
  });

  it("calls onSelect with current cwd when Select clicked", async () => {
    setupMock();
    const onSelect = vi.fn();
    render(<DirectoryPicker open onSelect={onSelect} onClose={() => {}} />);
    await screen.findByText(folderEntry("code"));
    await userEvent.click(screen.getByRole("button", { name: /Select|Выбрать/i }));
    expect(onSelect).toHaveBeenCalledWith(TEST_HOME);
  });

  it("filters entries via FilterInput", async () => {
    setupMock();
    render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} />);
    await screen.findByText(folderEntry("code"));
    const filter = screen.getByPlaceholderText(/Filter|Поиск|Пошук/i);
    await userEvent.type(filter, "doc");
    expect(screen.queryByText(folderEntry("code"))).not.toBeInTheDocument();
    expect(screen.getByText(folderEntry("Documents"))).toBeInTheDocument();
  });

  it("creates new folder via NewFolder button", async () => {
    setupMock();
    mock.onPost("/fs/mkdir").reply((config) => {
      const body = JSON.parse(config.data as string);
      expect(body.path).toBe(`${TEST_HOME}\\test_new`);
      return [200, { path: `${TEST_HOME}\\test_new` }];
    });
    render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} allowCreate />);
    await screen.findByText(folderEntry("code"));
    await userEvent.click(screen.getByRole("button", { name: /New folder|Новая|Нова папка/i }));
    const input = await screen.findByPlaceholderText(/folder name|имя папки/i);
    await userEvent.type(input, "test_new");
    await userEvent.click(screen.getByRole("button", { name: /^Create|Создать|Створити/i }));
    await waitFor(() => {
      expect(mock.history.post.length).toBeGreaterThan(0);
    });
  });

  it("recent paths shown when present in localStorage", async () => {
    localStorage.setItem("mnemos_recent_paths", JSON.stringify(["/tmp/a", "/tmp/b"]));
    setupMock();
    render(<DirectoryPicker open onSelect={() => {}} onClose={() => {}} />);
    expect(await screen.findByText("/tmp/a")).toBeInTheDocument();
    expect(screen.getByText("/tmp/b")).toBeInTheDocument();
  });

  it("calls onClose when Cancel clicked", async () => {
    setupMock();
    const onClose = vi.fn();
    render(<DirectoryPicker open onSelect={() => {}} onClose={onClose} />);
    await screen.findByText(folderEntry("code"));
    await userEvent.click(screen.getByRole("button", { name: /Cancel|Отмена|Скасувати/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
