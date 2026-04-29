import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../i18n";
import { TypedConfirmDialog } from "../components/widgets/TypedConfirmDialog";

beforeAll(() => {
  i18n.addResourceBundle("en", "translation", {
    confirm: {
      cancel: "Cancel", confirm: "Confirm", working: "Working...",
      typed_confirm_input_placeholder: "Type {{phrase}} to confirm",
    },
  }, true, true);
  void i18n.changeLanguage("en");
});

describe("TypedConfirmDialog", () => {
  it("Confirm disabled until typed phrase matches", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <TypedConfirmDialog
        open
        onOpenChange={() => {}}
        title="Permanent delete"
        description="This cannot be undone"
        expectedPhrase="foo"
        phraseLabel="Type the page name"
        confirmLabel="Delete forever"
        onConfirm={onConfirm}
      />,
    );
    const confirmBtn = screen.getByRole("button", { name: /delete forever/i });
    expect(confirmBtn).toBeDisabled();

    const input = screen.getByRole("textbox");
    await user.type(input, "fo");
    expect(confirmBtn).toBeDisabled();

    await user.type(input, "o");
    expect(confirmBtn).not.toBeDisabled();

    await user.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("rejects partial / wrong phrase", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <TypedConfirmDialog
        open
        onOpenChange={() => {}}
        title="t" description="d"
        expectedPhrase="alpha"
        phraseLabel="Type the name"
        confirmLabel="Delete"
        onConfirm={onConfirm}
      />,
    );
    await user.type(screen.getByRole("textbox"), "alphabet");
    expect(screen.getByRole("button", { name: /delete/i })).toBeDisabled();
  });
});
