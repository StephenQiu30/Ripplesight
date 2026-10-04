import { createServer, type Server } from "node:http";

import { afterEach, describe, expect, it, vi } from "vitest";

import * as route from "@/app/api/[[...path]]/route";

const ORIGINAL_API_ORIGIN = process.env.HOTKEY_API_ORIGIN;

afterEach(() => {
  vi.unstubAllGlobals();
  if (ORIGINAL_API_ORIGIN === undefined) {
    delete process.env.HOTKEY_API_ORIGIN;
  } else {
    process.env.HOTKEY_API_ORIGIN = ORIGINAL_API_ORIGIN;
  }
});

async function listen(server: Server): Promise<number> {
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("test server did not expose a TCP port");
  }
  return address.port;
}

async function close(server: Server): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}

describe("API route proxy", () => {
  it.each([
    ["public", "feed.xml"],
    ["public", "feed", "full", "category", "ai-models.xml"],
    ["public", "items", "b765dc61-effa-4d55-a44a-f2e41bf8c146.md"],
    ["public", "selected.md"],
    ["public", "reports", "daily", "2026-10-04.md"],
    ["public", "agent.md"],
    ["public", "api", "items"],
    ["public", "api", "stories", "b765dc61-effa-4d55-a44a-f2e41bf8c146"],
    ["public", "api", "reports", "daily", "2026-10-04"],
    ["public", "mcp"],
  ])(
    "forwards the fixed-publisher distribution path and conditional headers: %s",
    async (...path) => {
      process.env.HOTKEY_API_ORIGIN = "http://127.0.0.1:8000";
      const upstream = vi.fn().mockResolvedValue(
        new Response(null, {
          status: 304,
          headers: { ETag: '"current"', "Cache-Control": "no-store" },
        }),
      );
      vi.stubGlobal("fetch", upstream);
      const response = await route.GET(
        new Request(`http://web.test/${path.join("/")}?limit=40`, {
          headers: {
            "If-None-Match": '"current"',
            "X-Forwarded-For": "attacker",
          },
        }),
        { params: Promise.resolve({ path: ["__exports", ...path] }) },
      );
      expect(upstream.mock.calls[0][0].toString()).toBe(
        `http://127.0.0.1:8000/${path.join("/")}?limit=40`,
      );
      expect(upstream.mock.calls[0][1].headers.get("if-none-match")).toBe(
        '"current"',
      );
      expect(
        upstream.mock.calls[0][1].headers.get("x-forwarded-for"),
      ).toBeNull();
      expect(response.status).toBe(304);
      expect(response.headers.get("etag")).toBe('"current"');
      expect(await response.text()).toBe("");
    },
  );

  it.each([
    ["public", "api", "operations"],
    ["public", "api", "contents"],
    ["public", "items", "private.jsonld"],
    ["public", "feed", "..", "health"],
  ])(
    "rejects an unpublished or private public-prefixed path without HTTP: %s",
    async (...path) => {
      const upstream = vi.fn();
      vi.stubGlobal("fetch", upstream);
      const response = await route.GET(
        new Request("http://web.test/public/private"),
        { params: Promise.resolve({ path: ["__exports", ...path] }) },
      );
      expect(response.status).toBe(404);
      expect(upstream).not.toHaveBeenCalled();
    },
  );

  it("preserves the anonymous Redis window error and retry delay", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: "publication_rate_limited" }), {
          status: 429,
          headers: {
            "Retry-After": "59",
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
          },
        }),
      ),
    );
    const response = await route.GET(
      new Request("http://web.test/public/feed.xml"),
      {
        params: Promise.resolve({ path: ["__exports", "public", "feed.xml"] }),
      },
    );
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("59");
    expect((await response.json()).code).toBe("publication_rate_limited");
  });

  it("maps allowed public exports to root resources and preserves MCP headers", async () => {
    process.env.HOTKEY_API_ORIGIN = "http://127.0.0.1:8000";
    const upstream = vi.fn().mockResolvedValue(
      new Response("feed", {
        headers: { "Content-Type": "application/xml" },
      }),
    );
    vi.stubGlobal("fetch", upstream);
    await route.GET(
      new Request("http://web.test/feed/full/category/ai-models.xml?limit=5", {
        headers: {
          Cookie: "private=1",
          Authorization: "Bearer private",
          Accept: "application/xml",
        },
      }),
      {
        params: Promise.resolve({
          path: ["__exports", "feed", "full", "category", "ai-models.xml"],
        }),
      },
    );
    const [url, options] = upstream.mock.calls[0];
    expect(String(url)).toBe(
      "http://127.0.0.1:8000/feed/full/category/ai-models.xml?limit=5",
    );
    expect(options.headers.get("cookie")).toBeNull();
    expect(options.headers.get("authorization")).toBeNull();
    await route.POST(
      new Request("http://web.test/mcp", {
        method: "POST",
        body: '{"jsonrpc":"2.0"}',
        headers: {
          "MCP-Protocol-Version": "2025-06-18",
          Origin: "http://web.test",
          "Content-Type": "application/json",
        },
      }),
      { params: Promise.resolve({ path: ["__exports", "mcp"] }) },
    );
    expect(upstream.mock.calls[1][1].headers.get("mcp-protocol-version")).toBe(
      "2025-06-18",
    );
    expect(upstream.mock.calls[1][1].headers.get("origin")).toBe(
      "http://web.test",
    );
  });

  it.each([
    ["__exports", "admin"],
    ["__exports", "api", "operations"],
    ["__exports", "feed", "..", "health"],
    ["__exports", "sitemaps", "items-1000000.xml"],
    ["__exports", "sitemaps", "items-00.xml"],
    ["__exports", "sitemaps", "items--1.xml"],
  ])(
    "rejects an unrecognized root export without contacting the backend: %s",
    async (...path) => {
      const upstream = vi.fn();
      vi.stubGlobal("fetch", upstream);
      const response = await route.GET(
        new Request("http://web.test/api/__exports/admin"),
        { params: Promise.resolve({ path }) },
      );
      expect(response.status).toBe(404);
      expect(upstream).not.toHaveBeenCalled();
    },
  );

  it.each([
    ["items", 0],
    ["items", 7],
    ["items", 999999],
    ["stories", 0],
    ["reports", 1],
    ["topics", 0],
  ])(
    "proxies bounded %s sitemap shard %s without credentials",
    async (collection, shard) => {
      process.env.HOTKEY_API_ORIGIN = "http://127.0.0.1:8000";
      const upstream = vi.fn().mockResolvedValue(new Response("<urlset/>"));
      vi.stubGlobal("fetch", upstream);
      const response = await route.GET(
        new Request(`http://web.test/sitemaps/${collection}-${shard}.xml`, {
          headers: { Cookie: "private=1", Authorization: "Bearer private" },
        }),
        {
          params: Promise.resolve({
            path: ["__exports", "sitemaps", `${collection}-${shard}.xml`],
          }),
        },
      );
      expect(response.status).toBe(200);
      expect(String(upstream.mock.calls[0][0])).toBe(
        `http://127.0.0.1:8000/sitemaps/${collection}-${shard}.xml`,
      );
      expect(upstream.mock.calls[0][1].headers.get("cookie")).toBeNull();
      expect(upstream.mock.calls[0][1].headers.get("authorization")).toBeNull();
    },
  );
  it("exports only supported HTTP handlers", () => {
    expect(Object.keys(route).sort()).toEqual([
      "DELETE",
      "GET",
      "HEAD",
      "OPTIONS",
      "PATCH",
      "POST",
      "PUT",
    ]);
  });

  it("streams payloads and only forwards identity cookies and allowed business headers", async () => {
    let receivedBody = "";
    let receivedAuthorization = "";
    let receivedCookie = "";
    let receivedForwarded = "";
    const server = createServer((request, response) => {
      receivedAuthorization = request.headers.authorization ?? "";
      receivedCookie = request.headers.cookie ?? "";
      receivedForwarded = request.headers["x-forwarded-host"]?.toString() ?? "";
      request.setEncoding("utf8");
      request.on("data", (chunk: string) => {
        receivedBody += chunk;
      });
      request.on("end", () => {
        response.writeHead(206, {
          "Content-Disposition": 'attachment; filename="hotkey.bin"',
          "Content-Type": "application/octet-stream",
          "Set-Cookie": [
            "session=discarded; HttpOnly",
            "hotkey_session=renewed; HttpOnly; SameSite=Lax",
            "hotkey_csrf=csrf-renewed; SameSite=Lax",
          ],
          "X-Request-ID": "b64c7bc5-cf50-47ad-aa7d-82e5951d537a",
        });
        response.end(Buffer.from([0, 1, 2, 3]));
      });
    });
    const port = await listen(server);
    process.env.HOTKEY_API_ORIGIN = `http://127.0.0.1:${port}`;

    try {
      const response = await route.POST(
        new Request("http://web.test/api/files/example?download=1", {
          body: "payload",
          headers: {
            Authorization: "Bearer test-token",
            Cookie:
              "session=discarded; hotkey_session=test-session; hotkey_csrf=test-csrf; hotkey_oauth=browser-binding",
            "Content-Type": "text/plain",
            "X-Forwarded-Host": "attacker.invalid",
          },
          method: "POST",
        }),
        { params: Promise.resolve({ path: ["files", "example"] }) },
      );

      expect(response.status).toBe(206);
      expect(new Uint8Array(await response.arrayBuffer())).toEqual(
        new Uint8Array([0, 1, 2, 3]),
      );
      expect(response.headers.get("content-type")).toBe(
        "application/octet-stream",
      );
      expect(response.headers.get("content-disposition")).toContain(
        "hotkey.bin",
      );
      expect(response.headers.getSetCookie()).toEqual([
        "hotkey_session=renewed; HttpOnly; SameSite=Lax",
        "hotkey_csrf=csrf-renewed; SameSite=Lax",
      ]);
      expect(response.headers.get("x-request-id")).toBe(
        "b64c7bc5-cf50-47ad-aa7d-82e5951d537a",
      );
      expect(receivedBody).toBe("payload");
      expect(receivedAuthorization).toBe("");
      expect(receivedCookie).toBe(
        "hotkey_session=test-session; hotkey_csrf=test-csrf; hotkey_oauth=browser-binding",
      );
      expect(receivedForwarded).toBe("");
    } finally {
      await close(server);
    }
  });

  it("preserves a GitHub callback redirect and every allowed Set-Cookie", async () => {
    const headers = new Headers({
      Location: "/topics",
      "Cache-Control": "no-store",
    });
    headers.append("Set-Cookie", "hotkey_session=session; HttpOnly");
    headers.append("Set-Cookie", "hotkey_csrf=csrf");
    headers.append("Set-Cookie", "hotkey_oauth=; Max-Age=0");
    headers.append("Set-Cookie", "unrelated=discarded");
    const upstream = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 303, headers }));
    vi.stubGlobal("fetch", upstream);
    const response = await route.GET(
      new Request(
        "http://web.test/api/identity/github/callback?state=state&code=code",
        { headers: { Cookie: "hotkey_oauth=binding" } },
      ),
      { params: Promise.resolve({ path: ["identity", "github", "callback"] }) },
    );
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("/topics");
    expect(response.headers.getSetCookie()).toEqual([
      "hotkey_session=session; HttpOnly",
      "hotkey_csrf=csrf",
      "hotkey_oauth=; Max-Age=0",
    ]);
    expect(upstream.mock.calls[0][1].redirect).toBe("manual");
    expect(upstream.mock.calls[0][1].headers.get("cookie")).toBe(
      "hotkey_oauth=binding",
    );
  });

  it("returns a safe 502 with a proxy-owned request id when upstream is unavailable", async () => {
    const server = createServer();
    const port = await listen(server);
    await close(server);
    process.env.HOTKEY_API_ORIGIN = `http://127.0.0.1:${port}`;

    const response = await route.GET(
      new Request("http://web.test/api/health", {
        headers: {
          "X-Request-ID": "0125d835-4eab-4e6b-86fe-f5aa94fd9e50",
        },
      }),
      { params: Promise.resolve({ path: ["health"] }) },
    );
    const body = (await response.json()) as HotKeyAPI.ErrorView;

    expect(response.status).toBe(502);
    expect(body.code).toBe("upstream_error");
    expect(body.request_id).toBe(response.headers.get("x-request-id"));
    expect(body.request_id).not.toBe("0125d835-4eab-4e6b-86fe-f5aa94fd9e50");
  });

  it("distinguishes an upstream timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("secret", "TimeoutError")),
    );

    const response = await route.GET(
      new Request("http://web.test/api/health"),
      { params: Promise.resolve({ path: ["health"] }) },
    );
    const body = (await response.json()) as HotKeyAPI.ErrorView;

    expect(response.status).toBe(504);
    expect(body.code).toBe("upstream_timeout");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(JSON.stringify(body)).not.toContain("secret");
  });
});
