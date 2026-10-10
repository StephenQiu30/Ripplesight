import { existsSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";

it("uses slash hierarchy in static page paths and retires the Codex statistics pages", () => {
  const root = resolve("src/app");
  const pages = readdirSync(root, { recursive: true })
    .map(String)
    .filter((path) => path.endsWith("/page.tsx"));
  for (const page of pages) {
    const staticSegments = page
      .split("/")
      .slice(0, -1)
      .filter(
        (segment) => !segment.startsWith("[") && !segment.startsWith("("),
      );
    expect(
      staticSegments.filter((segment) => segment.includes("-")),
      page,
    ).toEqual([]);
  }
  expect(existsSync(resolve(root, "sources/editorial/page.tsx"))).toBe(true);
  expect(existsSync(resolve(root, "sources/personal/page.tsx"))).toBe(true);
  expect(existsSync(resolve(root, "codex/resets/page.tsx"))).toBe(false);
  expect(existsSync(resolve(root, "codex-resets/page.tsx"))).toBe(false);
});
