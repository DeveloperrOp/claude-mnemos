import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "../i18n";
import { apiClient } from "../api/client";
import { SnapshotTrashSection } from "../components/widgets/SnapshotTrashSection";

const TRASH_ITEM = {
  name: "daily-2026-04-26",
  kind: "daily",
  timestamp: "2026-04-26T00:00:00+00:00",
  op_id: null,
  op_type: null,
  label: null,
  size_bytes: 2048,
  path: ".backups/_trash-daily-2026-04-26",
};

beforeEach(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      confirm: { cancel: "Cancel", working: "Working…" },
      snapshots: {
        kind: { daily: "Daily", manual: "Manual", "pre-op": "Pre-op" },
        trash: {
          title: "Snapshot trash",
          hint: "Deleted snapshots live here.",
          restore_button: "Restore",
          purge_button: "Delete forever",
          restore_modal_title: "Restore snapshot?",
          restore_modal_desc: "Returns it to the list.",
          purge_modal_title: "Delete snapshot forever?",
          purge_modal_desc: "Gone for good.",
          purge_typed_label: "Type the name",
          restored_toast: "Restored",
          purged_toast: "Purged",
        },
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
  vi.spyOn(apiClient, "get");
  vi.spyOn(apiClient, "post");
  vi.spyOn(apiClient, "delete");
});
afterEach(() => {
  vi.restoreAllMocks();
});

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function stubTrash(items: unknown[]) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/trash")) return { data: { snapshots: items } };
    throw new Error(`unexpected GET ${url}`);
  });
}

describe("SnapshotTrashSection", () => {
  it("renders nothing when trash is empty", async () => {
    stubTrash([]);
    const { container } = wrap(<SnapshotTrashSection project="p1" />);
    // Give the query a tick; section must stay absent.
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
    expect(container.querySelector("button")).toBeNull();
  });

  it("shows count, expands, and restore POSTs restore-from-trash", async () => {
    stubTrash([TRASH_ITEM]);
    vi.mocked(apiClient.post).mockResolvedValue({ data: { restored: TRASH_ITEM.name } });
    wrap(<SnapshotTrashSection project="p1" />);

    const header = await screen.findByRole("button", {
      name: /Snapshot trash \(1\)/i,
    });
    await userEvent.click(header);

    // Row "Restore" button (only one at this point) opens the confirm dialog.
    await userEvent.click(
      await screen.findByRole("button", { name: /^Restore$/i }),
    );
    // Now there are two "Restore" buttons (row + dialog action); the dialog
    // action is the last one and triggers the mutation.
    const restoreBtns = await screen.findAllByRole("button", {
      name: /^Restore$/i,
    });
    await userEvent.click(restoreBtns[restoreBtns.length - 1]);

    await waitFor(() =>
      expect(apiClient.post).toHaveBeenCalledWith(
        "/snapshots/p1/daily-2026-04-26/restore-from-trash",
      ),
    );
  });

  it("purge requires typing the name then DELETEs /purge", async () => {
    stubTrash([TRASH_ITEM]);
    vi.mocked(apiClient.delete).mockResolvedValue({ data: { purged: TRASH_ITEM.name } });
    wrap(<SnapshotTrashSection project="p1" />);

    const header = await screen.findByRole("button", {
      name: /Snapshot trash \(1\)/i,
    });
    await userEvent.click(header);

    await userEvent.click(
      await screen.findByRole("button", { name: /Delete forever/i }),
    );
    // Typed-confirm gate: type the exact name to enable the action.
    const input = await screen.findByRole("textbox");
    await userEvent.type(input, TRASH_ITEM.name);
    const confirmBtns = screen.getAllByRole("button", { name: /Delete forever/i });
    // The dialog action is the last "Delete forever" button.
    await userEvent.click(confirmBtns[confirmBtns.length - 1]);

    await waitFor(() =>
      expect(apiClient.delete).toHaveBeenCalledWith(
        "/snapshots/p1/daily-2026-04-26/purge",
      ),
    );
  });
});
