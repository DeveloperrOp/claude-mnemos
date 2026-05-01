import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { apiClient } from "../api/client";
import i18n from "../i18n";
import { CwdBuilder } from "../components/onboarding/CwdBuilder";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    cwd_builder: {
      add: "Add folder",
      remove: "Remove",
      recursive: "Include subfolders",
      empty: "No folders added — sessions must be ingested manually",
    },
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
  mock = new MockAdapter(apiClient);
  mock.onGet("/fs/home").reply(200, { home: "/home" });
  mock.onGet(/\/fs\/browse/).reply(200, {
    cwd: "/home",
    parent: null,
    entries: [{ name: "code", path: "/home/code" }],
    truncated: false,
  });
});

describe("CwdBuilder", () => {
  it("renders empty list when no patterns", () => {
    render(<CwdBuilder patterns={[]} onChange={() => {}} />);
    expect(screen.getByText(/Add folder|Добавить папку|Додати папку/i)).toBeInTheDocument();
  });

  it("renders existing patterns with recursive flag", () => {
    render(<CwdBuilder patterns={["/home/code/*", "/tmp"]} onChange={() => {}} />);
    expect(screen.getByText(/📁\s*\/home\/code$/)).toBeInTheDocument();
    expect(screen.getByText(/📁\s*\/tmp$/)).toBeInTheDocument();
  });

  it("removes pattern when × clicked", async () => {
    const onChange = vi.fn();
    render(<CwdBuilder patterns={["/home/code/*"]} onChange={onChange} />);
    const removeBtn = screen.getByRole("button", { name: /Remove|Удалить|Видалити/i });
    await userEvent.click(removeBtn);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("toggles recursive — appends or strips trailing /*", async () => {
    const onChange = vi.fn();
    render(<CwdBuilder patterns={["/home/code/*"]} onChange={onChange} />);
    const checkbox = screen.getByRole("checkbox");
    await userEvent.click(checkbox);  // turn off recursive
    expect(onChange).toHaveBeenCalledWith(["/home/code"]);
  });

  it("opens DirectoryPicker on Add folder click", async () => {
    render(<CwdBuilder patterns={[]} onChange={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /Add folder/i }));
    expect(await screen.findByText(/📁\s*code$/)).toBeInTheDocument();  // picker rendered
  });
});
