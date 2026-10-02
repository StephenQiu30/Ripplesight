import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";
import { beforeAll, describe, expect, it } from "vitest";

const eslint = new ESLint({
  cwd: fileURLToPath(new URL("../..", import.meta.url)),
});
const boundaryRules = new Set([
  "no-restricted-imports",
  "no-restricted-globals",
  "no-restricted-syntax",
]);

async function violations(
  code: string,
  filePath = "src/components/example.ts",
) {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages.filter((message) =>
    boundaryRules.has(message.ruleId!),
  );
}

describe("generated API request boundary", () => {
  beforeAll(async () => {
    await eslint.calculateConfigForFile("src/components/example.ts");
  });

  it.each([
    'import axios from "axios"; axios.get("/api/topics");',
    'import { request } from "@/request"; request("/api/topics");',
    'import request from "../../request"; request("/api/topics");',
    'import * as transport from "@/request"; transport.request("/api/topics");',
    'export { request } from "@/request";',
    'import { get } from "node:https"; get("https://api.test");',
    'import("axios").then((client) => client.default.get("/api/topics"));',
    'import("@/request").then((client) => client.request("/api/topics"));',
    'fetch("/api/topics");',
    'globalThis.fetch("/api/topics");',
    'window.fetch("/api/topics");',
    "new XMLHttpRequest();",
    'new EventSource("/api/topics");',
    'new WebSocket("wss://api.test");',
    'navigator.sendBeacon("/api/topics", "data");',
  ])("rejects a handwritten request: %s", async (code) => {
    expect(await violations(code)).not.toHaveLength(0);
  });

  it.each([
    'import { listMonitorTopics } from "@/api/jiankongzhuti"; listMonitorTopics({});',
    'import { ApiRequestError, type RequestOptions } from "@/request";',
    'import type { RequestOptions } from "../../request";',
    'navigator.locks.request("local-state", () => {});',
  ])("allows generated APIs and local utilities: %s", async (code) => {
    expect(await violations(code)).toHaveLength(0);
  });

  it("keeps the unique transport and transparent proxy usable", async () => {
    expect(
      await violations('import axios from "axios";', "src/request.ts"),
    ).toHaveLength(0);
    expect(
      await violations(
        'fetch("http://upstream.test/api/topics");',
        "src/app/api/[[...path]]/route.ts",
      ),
    ).toHaveLength(0);
  });
});
