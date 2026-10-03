import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
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
    has_password: true,
    github_connected: false,
    email: null,
  },
  expires_at: "2026-10-03T00:00:00Z",
};

beforeEach(() => {
  getIdentitySession.mockReset();
});
afterEach(() => vi.unstubAllEnvs());

function pageRequest(url: string, method = "GET") {
  return new NextRequest(url, { method, headers: { Host: new URL(url).host } });
}

describe("authenticated navigation and CSP", () => {
  it.each(["GET", "HEAD"])(
    "canonicalizes a loopback alias before authentication for %s",
    async (method) => {
      vi.stubEnv("HOTKEY_WEB_ORIGIN", "http://127.0.0.1:8666");
      const response = await proxy(
        pageRequest(
          "http://localhost:8666/login?returnTo=%2Fjobs%3Fstate%3Dfailed",
          method,
        ),
      );
      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe(
        "http://127.0.0.1:8666/login?returnTo=%2Fjobs%3Fstate%3Dfailed",
      );
      expect(response.headers.get("cache-control")).toBe("private, no-store");
      expect(getIdentitySession).not.toHaveBeenCalled();
    },
  );

  it("uses the configured loopback hostname rather than a fixed redirect target", async () => {
    vi.stubEnv("HOTKEY_WEB_ORIGIN", "http://localhost:8666");
    const response = await proxy(pageRequest("http://127.0.0.1:8666/login"));
    expect(response.headers.get("location")).toBe(
      "http://localhost:8666/login",
    );
  });

  it("keeps a protocol-relative path on the fixed canonical host", async () => {
    vi.stubEnv("HOTKEY_WEB_ORIGIN", "http://127.0.0.1:8666");
    const response = await proxy(
      pageRequest(
        "http://localhost:8666//attacker.invalid/login?returnTo=%2Ftopics",
      ),
    );
    expect(response.headers.get("location")).toBe(
      "http://127.0.0.1:8666//attacker.invalid/login?returnTo=%2Ftopics",
    );
  });

  it("does not trust a forwarded hostname when deciding whether to redirect", async () => {
    vi.stubEnv("HOTKEY_WEB_ORIGIN", "http://127.0.0.1:8666");
    const response = await proxy(
      new NextRequest("http://127.0.0.1:8666/login", {
        headers: {
          Host: "127.0.0.1:8666",
          "x-forwarded-host": "localhost:8666",
        },
      }),
    );
    expect(response.status).toBe(200);
  });

  it.each([
    "http://127.0.0.1:8666/login",
    "http://localhost:9999/login",
    "https://localhost:8666/login",
    "http://127.0.0.1.attacker.example:8666/login",
    "https://hotkey.test/login",
  ])(
    "does not canonicalize a different origin or the canonical URL: %s",
    async (url) => {
      vi.stubEnv("HOTKEY_WEB_ORIGIN", "http://127.0.0.1:8666");
      expect((await proxy(pageRequest(url))).status).toBe(200);
    },
  );

  it("does not replay a mutation across loopback origins", async () => {
    vi.stubEnv("HOTKEY_WEB_ORIGIN", "http://127.0.0.1:8666");
    expect(
      (await proxy(pageRequest("http://localhost:8666/login", "POST"))).status,
    ).toBe(200);
  });

  it("does not apply local alias redirects to a deployed Web origin", async () => {
    vi.stubEnv("HOTKEY_WEB_ORIGIN", "https://hotkey.test");
    expect(
      (await proxy(pageRequest("http://localhost:8666/login"))).status,
    ).toBe(200);
  });

  it("clears an orphaned CSRF cookie before public email login", async () => {
    const response = await proxy(
      new NextRequest("https://hotkey.test/login", {
        headers: { Cookie: "hotkey_csrf=orphaned-token" },
      }),
    );
    expect(response.status).toBe(200);
    expect(response.cookies.get("hotkey_csrf")?.expires).toEqual(new Date(0));
    expect(getIdentitySession).not.toHaveBeenCalled();
  });

  it("allows exactly the installed Sonner stylesheet in production without allowing arbitrary inline styles", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const require = createRequire(import.meta.url);
    const dist = dirname(require.resolve("sonner"));
    const hashes = ["index.js", "index.mjs"].map((file) => {
      const source = readFileSync(join(dist, file), "utf8");
      const match = source.match(/__insertCSS\(("(?:[^"\\]|\\.)*")\);?/);
      expect(match).not.toBeNull();
      const css = JSON.parse(match![1]) as string;
      return createHash("sha256").update(css).digest("base64");
    });
    const response = await proxy(new NextRequest("https://hotkey.test/login"));
    const stylePolicy = response.headers
      .get("content-security-policy")!
      .split("; ")
      .find((directive) => directive.startsWith("style-src "))!;
    for (const hash of hashes)
      expect(stylePolicy).toContain(`'sha256-${hash}'`);
    expect(stylePolicy).toMatch(/'nonce-[^']+'/);
    expect(stylePolicy).not.toContain("'unsafe-inline'");
  });
  it.each([
    "/topics",
    "/events",
    "/reports",
    "/monitors/new",
    "/workspace",
    "/publication/manage",
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
    "/discover",
    "/discover/topics/ai",
    "/items/content-1",
    "/leaderboard",
    "/reports/weekly",
    "/reports/weekly/2026-W40",
  ])("keeps %s public", async (path) => {
    const response = await proxy(new NextRequest(`https://hotkey.test${path}`));
    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(getIdentitySession).not.toHaveBeenCalled();
  });

  it("keeps public reading available during a session outage without deleting the cookie", async () => {
    getIdentitySession.mockRejectedValue(new Error("upstream unavailable"));
    const response = await proxy(
      new NextRequest("https://hotkey.test/discover", {
        headers: { Cookie: "hotkey_session=existing" },
      }),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(
      response.headers.get("x-middleware-request-x-hotkey-session"),
    ).toBeNull();
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

  it.each([
    ["/content?state=unread", "/content?state=unread"],
    ["//attacker.invalid", "/topics"],
  ])(
    "routes an authenticated email-only account through password setup at login",
    async (returnTo, expected) => {
      getIdentitySession.mockResolvedValue({
        ...SESSION,
        user: {
          ...SESSION.user,
          email: "reader@example.com",
          has_password: false,
        },
      });
      const url = new URL("https://hotkey.test/login");
      url.searchParams.set("returnTo", returnTo);
      const response = await proxy(
        new NextRequest(url, { headers: { Cookie: "hotkey_session=token" } }),
      );
      const target = new URL(response.headers.get("location")!);
      expect(target.pathname).toBe("/account");
      expect(target.searchParams.get("setup")).toBe("1");
      expect(target.searchParams.get("returnTo")).toBe(expected);
      expect(response.headers.get("set-cookie")).toBeNull();
    },
  );

  it("continues to let an authenticated email-only account open existing workspace pages", async () => {
    getIdentitySession.mockResolvedValue({
      ...SESSION,
      user: { ...SESSION.user, has_password: false },
    });
    const response = await proxy(
      new NextRequest("https://hotkey.test/topics", {
        headers: { Cookie: "hotkey_session=token" },
      }),
    );
    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("preserves the original workspace target when a session expires during password setup", async () => {
    const url = new URL("https://hotkey.test/account?setup=1");
    url.searchParams.set("returnTo", "/jobs/job-1?state=failed");
    const response = await proxy(new NextRequest(url));
    const login = new URL(response.headers.get("location")!);
    expect(login.pathname).toBe("/login");
    expect(login.searchParams.get("returnTo")).toBe("/jobs/job-1?state=failed");
  });
});
