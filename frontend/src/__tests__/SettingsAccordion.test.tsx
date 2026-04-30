import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../i18n";
import { SettingsAccordion } from "../components/settings/SettingsAccordion";

beforeAll(() => {
  i18n.addResourceBundle(
    "en",
    "translation",
    {
      settings: {
        save: "Save",
        saving: "Saving...",
      },
    },
    true,
    true,
  );
  void i18n.changeLanguage("en");
});

describe("SettingsAccordion", () => {
  it("renders title and toggles content", async () => {
    render(
      <SettingsAccordion title="Test section" dirty={false} saving={false} onSave={() => {}}>
        <div>body content</div>
      </SettingsAccordion>,
    );
    expect(screen.getByText("Test section")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /Test section/ });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("Save button disabled when not dirty", () => {
    render(
      <SettingsAccordion title="X" dirty={false} saving={false} onSave={() => {}}>
        <div />
      </SettingsAccordion>,
    );
    const save = screen.getByRole("button", { name: /Save|Сохранить|Зберегти/i });
    expect(save).toBeDisabled();
  });

  it("Save button enabled when dirty, calls onSave", async () => {
    const onSave = vi.fn();
    render(
      <SettingsAccordion title="X" dirty={true} saving={false} onSave={onSave}>
        <div />
      </SettingsAccordion>,
    );
    const save = screen.getByRole("button", { name: /Save|Сохранить|Зберегти/i });
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(onSave).toHaveBeenCalled();
  });

  it("Save button shows saving state", () => {
    render(
      <SettingsAccordion title="X" dirty={true} saving={true} onSave={() => {}}>
        <div />
      </SettingsAccordion>,
    );
    const save = screen.getByRole("button", { name: /Saving|Сохранение|Збереження/i });
    expect(save).toBeDisabled();
  });
});
