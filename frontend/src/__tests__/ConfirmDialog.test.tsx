import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../i18n";
import { ConfirmDialog } from "../components/widgets/ConfirmDialog";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    confirm: { cancel: "Cancel", confirm: "Confirm", working: "Working..." },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("ConfirmDialog", () => {
  it("renders title + description when open", () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Restore page?"
        description="This will move the page back to wiki/"
        confirmLabel="Restore"
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByText("Restore page?")).toBeInTheDocument();
    expect(screen.getByText(/This will move/)).toBeInTheDocument();
  });

  it("calls onConfirm on Confirm click", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="t" description="d"
        confirmLabel="Restore"
        onConfirm={onConfirm}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Restore" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onOpenChange(false) on Cancel", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="t" description="d"
        confirmLabel="Restore"
        onConfirm={() => {}}
      />,
    );
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("disables Confirm when isPending", () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="t" description="d"
        confirmLabel="Restore"
        onConfirm={() => {}}
        isPending
      />,
    );
    expect(screen.getByRole("button", { name: /working/i })).toBeDisabled();
  });
});
