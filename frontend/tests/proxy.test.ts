import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { proxy } from "@/proxy";
import { ApiRequestError } from "@/request";

const { getIdentitySession } = vi.hoisted(() => ({
  getIdentitySession: vi.fn(),
}));
vi.mock("@/api/identity", () => ({ getIdentitySession }));

const SESSION = {
  user: {
    id: "bd0ae74e-23c8-456a-8b60-0905031e39bc",
    username: "reader",
    email: null,
  },
  expires_at: "2026-10-03T00:00:00Z",
};

beforeEach(() => {
  getIdentitySession.mockReset();
});

describe("authenticated navigation and CSP", () => {
  it.each([
    "/topics",
    "/events",
    "/reports",
    "/monitors/new",
    "/leaderboard",
    "/feeds",
    "/operations",
  ])(
    "requires a session before opening %s, including prefetch",
    async (path) => {
      const response = await proxy(
        new NextRequest(`https://hotkey.test${path}?page=2`, {
          headers: {
            "next-router-prefetch": "1",
            "x-hotkey-session": "forged",
          },
        }),
      );
      expect(response.status).toBe(307);
      const destination = new URL(response.headers.get("location")!);
      expect(destination.pathname).toBe("/login");
      expect(destination.searchParams.get("returnTo")).toBe(`${path}?page=2`);
      expect(response.headers.get("content-security-policy")).toContain(
        "default-src 'self'",
      );
      expect(response.headers.get("cache-control")).toBe("private, no-store");
      expect(getIdentitySession).not.toHaveBeenCalled();
    },
  );

  it.each([
    "/",
    "/login",
    "/about",
    "/privacy",
    "/terms",
    "/contact",
    "/changelog",
  ])("keeps %s public", async (path) => {
    const response = await proxy(new NextRequest(`https://hotkey.test${path}`));
    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(getIdentitySession).not.toHaveBeenCalled();
  });

  it("verifies the real session and replaces caller-supplied identity headers", async () => {
    getIdentitySession.mockResolvedValue(SESSION);
    const response = await proxy(
      new NextRequest("https://hotkey.test/topics", {
        headers: {
          Cookie:
            "unrelated=private; hotkey_session=session-token; hotkey_csrf=csrf-token",
          "x-hotkey-session": "forged",
          "x-hotkey-session-error": "forged",
        },
      }),
    );
    expect(getIdentitySession).toHaveBeenCalledWith({
      headers: {
        Cookie: "hotkey_session=session-token; hotkey_csrf=csrf-token",
      },
    });
    expect(response.status).toBe(200);
    expect(
      decodeURIComponent(
        response.headers.get("x-middleware-request-x-hotkey-session")!,
      ),
    ).toBe(JSON.stringify(SESSION));
    expect(
      response.headers.get("x-middleware-request-x-hotkey-session-error"),
    ).toBeNull();
  });

  it.each(["/topics", "/login", "/"])(
    "clears a confirmed invalid session at %s so email login can recover",
    async (path) => {
      getIdentitySession.mockRejectedValue(
        new ApiRequestError({
          kind: "http",
          status: 401,
          code: "invalid_session",
          message: "expired",
        }),
      );
      const response = await proxy(
        new NextRequest(`https://hotkey.test${path}`, {
          headers: {
            Cookie: "hotkey_session=expired; hotkey_csrf=expired-csrf",
          },
        }),
      );
      expect(response.status).toBe(path === "/topics" ? 307 : 200);
      if (path === "/topics") {
        expect(new URL(response.headers.get("location")!).pathname).toBe(
          "/login",
        );
      }
      expect(response.cookies.get("hotkey_session")?.value).toBe("");
      expect(response.cookies.get("hotkey_csrf")?.value).toBe("");
      expect(response.cookies.get("hotkey_session")?.expires).toEqual(
        new Date(0),
      );
      expect(response.cookies.get("hotkey_csrf")?.expires).toEqual(new Date(0));
    },
  );

  it("preserves a recoverable 503 when the session service is unavailable", async () => {
    getIdentitySession.mockRejectedValue(
      new ApiRequestError({ kind: "network", message: "unavailable" }),
    );
    const response = await proxy(
      new NextRequest("https://hotkey.test/topics", {
        headers: { Cookie: "hotkey_session=token" },
      }),
    );
    expect(response.status).toBe(503);
    expect(
      new URL(response.headers.get("x-middleware-rewrite")!).pathname,
    ).toBe("/login");
    expect(
      response.headers.get("x-middleware-request-x-hotkey-session-error"),
    ).toBe("1");
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it.each([
    "//attacker.invalid",
    "/\\attacker.invalid",
    "/%2f%2fattacker.invalid",
    "/login",
    "/api/topics",
  ])(
    "uses the workspace default for an unsafe return target %s",
    async (target) => {
      getIdentitySession.mockResolvedValue(SESSION);
      const url = new URL("https://hotkey.test/login");
      url.searchParams.set("returnTo", target);
      const response = await proxy(
        new NextRequest(url, { headers: { Cookie: "hotkey_session=token" } }),
      );
      expect(response.headers.get("location")).toBe(
        "https://hotkey.test/topics",
      );
    },
  );

  it("uses a distinct CSP nonce for each public page request", async () => {
    const request = new NextRequest("https://hotkey.test/");
    const first = (await proxy(request)).headers.get("content-security-policy");
    const second = (await proxy(request)).headers.get(
      "content-security-policy",
    );

    expect(first).toMatch(/'nonce-[^']+'/);
    expect(second).toMatch(/'nonce-[^']+'/);
    expect(first).not.toBe(second);
  });
});
