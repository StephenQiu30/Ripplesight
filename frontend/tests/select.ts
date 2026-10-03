import { fireEvent, screen } from "@testing-library/react";

/** Open the real Radix listbox and select an accessible option. */
export async function selectOption(
  trigger: HTMLElement,
  name: string | RegExp,
) {
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name }));
}
