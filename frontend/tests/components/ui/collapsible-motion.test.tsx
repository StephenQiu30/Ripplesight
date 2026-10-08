// @vitest-environment happy-dom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import gsap from "gsap";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

const queries = new Map<
  string,
  { matches: boolean; listeners: Set<() => void> }
>();
function setMedia(query: string, matches: boolean) {
  const media = queries.get(query)!;
  act(() => {
    media.matches = matches;
    media.listeners.forEach((listener) => listener());
  });
}
beforeEach(() => {
  queries.clear();
  vi.stubGlobal("matchMedia", (query: string) => {
    if (!queries.has(query))
      queries.set(query, { matches: false, listeners: new Set() });
    const media = queries.get(query)!;
    return {
      get matches() {
        return media.matches;
      },
      addEventListener: (_: string, listener: () => void) =>
        media.listeners.add(listener),
      removeEventListener: (_: string, listener: () => void) =>
        media.listeners.delete(listener),
    };
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Disclosure() {
  return (
    <Collapsible defaultOpen>
      <CollapsibleTrigger>主题列表</CollapsibleTrigger>
      <CollapsibleContent motion="below-lg" data-testid="list">
        <input aria-label="搜索主题" defaultValue="保留输入" />
      </CollapsibleContent>
    </Collapsible>
  );
}

describe("responsive disclosure motion", () => {
  it("keeps inputs mounted through reversals and returns hidden focus to the trigger", () => {
    render(<Disclosure />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    const trigger = screen.getByRole("button");
    input.focus();
    fireEvent.click(trigger);
    expect(screen.getByTestId("list").inert).toBe(true);
    expect(document.activeElement).toBe(trigger);
    fireEvent.click(trigger);
    act(() => {
      gsap.globalTimeline.progress(1);
    });
    expect(screen.getByRole("textbox")).toBe(input);
    expect(input.value).toBe("保留输入");
    expect(screen.getByTestId("list").inert).toBe(false);
    expect(screen.getByTestId("list").hasAttribute("data-motion-hidden")).toBe(
      false,
    );
  });

  it("settles immediately when reduced motion changes and restores the closed list on desktop", () => {
    render(<Disclosure />);
    fireEvent.click(screen.getByRole("button"));
    setMedia("(prefers-reduced-motion: reduce)", true);
    const list = screen.getByTestId("list");
    expect(list.hasAttribute("data-motion-hidden")).toBe(true);
    expect(list.style.height).toBe("");
    setMedia("(min-width: 1024px)", true);
    expect(list.hasAttribute("data-motion-hidden")).toBe(false);
    expect(list.hasAttribute("aria-hidden")).toBe(false);
    expect(list.inert).toBe(false);
    expect(list.style.height).toBe("");
    expect(screen.getByRole("textbox")).toBeTruthy();
  });
});
