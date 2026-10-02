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

  it("streams payloads and business headers without forwarding credentials", async () => {
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
          "Set-Cookie": "session=renewed; HttpOnly",
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
            Cookie: "session=test-session",
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
      expect(response.headers.get("set-cookie")).toBeNull();
      expect(response.headers.get("x-request-id")).toBe(
        "b64c7bc5-cf50-47ad-aa7d-82e5951d537a",
      );
      expect(receivedBody).toBe("payload");
      expect(receivedAuthorization).toBe("");
      expect(receivedCookie).toBe("");
      expect(receivedForwarded).toBe("");
    } finally {
      await close(server);
    }
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
