// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from "vitest";
import {
  SAVED_KEY,
  READ_KEY,
  savedIds,
  readIds,
  toggleSaved,
  importLocalBundle,
  exportLocalBundle,
  parseLocalImport,
} from "@/components/publication/local-state";
const id = (index: number) =>
  `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Object.defineProperty(navigator, "locks", {
    value: undefined,
    configurable: true,
  });
});
it("serializes fresh cross-tab merges using Web Locks and never exports copied text", async () => {
  let tail: Promise<unknown> = Promise.resolve();
  Object.defineProperty(navigator, "locks", {
    configurable: true,
    value: {
      request: (_name: string, callback: () => unknown) => {
        const result = tail.then(callback);
        tail = result.catch(() => undefined);
        return result;
      },
    },
  });
  await Promise.all([toggleSaved(id(1)), toggleSaved(id(2))]);
  expect(new Set(savedIds(localStorage))).toEqual(new Set([id(1), id(2)]));
  const report = await importLocalBundle(
    JSON.stringify({
      version: 1,
      starred: [
        { id: id(1), savedAt: "2026-10-01T00:00:00Z", title: "not copied" },
        { id: id(3), savedAt: "2026-10-01T00:00:00Z", summary: "not copied" },
      ],
      read: [id(3)],
      theme: null,
    }),
  );
  expect(report.savedAdded).toBe(1);
  expect(report.readAdded).toBe(1);
  expect(JSON.stringify(exportLocalBundle(localStorage))).not.toContain(
    "not copied",
  );
  expect(new Set(savedIds(localStorage))).toEqual(
    new Set([id(1), id(2), id(3)]),
  );
});
it("preserves unreadable data and rejects oversized or unsupported backup formats", async () => {
  localStorage.setItem(SAVED_KEY, "broken");
  await expect(toggleSaved(id(1))).rejects.toThrow("未覆盖");
  await expect(
    importLocalBundle(
      JSON.stringify({ version: 1, starred: [], read: [], theme: null }),
    ),
  ).rejects.toThrow("未覆盖");
  expect(localStorage.getItem(SAVED_KEY)).toBe("broken");
  expect(() => parseLocalImport("x".repeat(2_000_001))).toThrow("文件过大");
  expect(() => parseLocalImport('{"version":2}')).toThrow("version: 1");
});
it("keeps existing records at 500 stars/5000 read marks and reports invalid/capacity skips", async () => {
  localStorage.setItem(
    SAVED_KEY,
    JSON.stringify(Array.from({ length: 499 }, (_, index) => id(index + 1))),
  );
  localStorage.setItem(
    READ_KEY,
    JSON.stringify(Array.from({ length: 4999 }, (_, index) => id(index + 1))),
  );
  const result = await importLocalBundle(
    JSON.stringify({
      version: 1,
      starred: [
        { id: id(8000), savedAt: "2026-10-01" },
        { id: id(8001), savedAt: "2026-10-01" },
        { id: id(8002), savedAt: "bad" },
      ],
      read: [id(8000), id(8001), "bad"],
      theme: null,
    }),
  );
  expect(savedIds(localStorage)).toHaveLength(500);
  expect(readIds(localStorage)).toHaveLength(5000);
  expect(savedIds(localStorage)).toContain(id(1));
  expect(result.skipped).toBe(4);
});
it("reports partial read-mark storage failure after successful star merge", async () => {
  const actual = localStorage;
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => actual.getItem(key),
    clear: () => actual.clear(),
    setItem: (key: string, value: string) => {
      if (key === READ_KEY) throw new Error("quota");
      actual.setItem(key, value);
    },
  });
  const result = await importLocalBundle(
    JSON.stringify({
      version: 1,
      starred: [{ id: id(1), savedAt: "2026-10-01" }],
      read: [id(1)],
      theme: null,
    }),
  );
  expect(result.readFailed).toBe(true);
  expect(result.savedAdded).toBe(1);
  expect(result.readAdded).toBe(0);
  expect(savedIds(localStorage)).toEqual([id(1)]);
});
