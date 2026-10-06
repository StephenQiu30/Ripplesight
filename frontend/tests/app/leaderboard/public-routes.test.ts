import { NextRequest } from "next/server";
import { afterEach, expect, it, vi } from "vitest";
import { proxy } from "@/proxy";
import { boardTabs } from "@/components/leaderboard/board-navigation";

const { getIdentitySession } = vi.hoisted(() => ({
  getIdentitySession: vi.fn(),
}));
vi.mock("@/api/identity", () => ({ getIdentitySession }));
afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllEnvs();
});
const paths = [
  ...boardTabs.map(({ href }) => href),
  "/leaderboard/models/test-model",
  "/leaderboard/sources",
  "/leaderboard/sources/test-source",
  "/leaderboard/rules",
];

it.each(paths)(
  "keeps %s anonymously readable without a session lookup",
  async (path) => {
    const response = await proxy(new NextRequest(`https://hotkey.test${path}`));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(getIdentitySession).not.toHaveBeenCalled();
  },
);

it.each(paths)("keeps %s public during a session outage", async (path) => {
  getIdentitySession.mockRejectedValue(new Error("session unavailable"));
  const response = await proxy(
    new NextRequest(`https://hotkey.test${path}`, {
      headers: { Cookie: "hotkey_session=existing" },
    }),
  );
  expect(response.status).toBe(200);
  expect(response.headers.get("location")).toBeNull();
  expect(response.headers.get("set-cookie")).toBeNull();
});
