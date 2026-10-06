// @vitest-environment happy-dom
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TopicSettingsFields } from "@/components/monitors/topic-settings-fields";
afterEach(cleanup);

describe("unavailable selected source", () => {
  it("can be removed without allowing it to be selected again", () => {
    function ExistingSelection() {
      const [keys, setKeys] = useState(["retired"]);
      return (
        <TopicSettingsFields
          sourceOptions={[
            {
              sourceKey: "retired",
              displayName: "已失效来源",
              selectable: false,
              reason: "请移除已失效的来源。",
            },
          ]}
          sourceKeys={keys}
          onSourceKeysChange={setKeys}
          disabled={false}
        />
      );
    }
    render(<ExistingSelection />);
    const checkbox = screen.getByRole("switch", { name: "已失效来源" });
    expect((checkbox as HTMLButtonElement).disabled).toBe(false);
    expect(checkbox.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(checkbox);
    expect(checkbox.getAttribute("aria-checked")).toBe("false");
    expect((checkbox as HTMLButtonElement).disabled).toBe(true);
  });
});
