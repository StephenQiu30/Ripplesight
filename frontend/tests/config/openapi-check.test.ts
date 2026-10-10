import { execFileSync, spawnSync } from "node:child_process";
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, expect, it } from "vitest";

const command: string = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../package.json", import.meta.url)),
    "utf8",
  ),
).scripts["openapi:check"];
const temporary: string[] = [];

afterEach(() => {
  for (const directory of temporary.splice(0))
    rmSync(directory, { recursive: true, force: true });
});

function fixture() {
  const repo = mkdtempSync(path.join(tmpdir(), "ripplesight-openapi-test-"));
  temporary.push(repo);
  const cwd = path.join(repo, "frontend");
  const api = path.join(cwd, "src/api");
  const bin = path.join(repo, "bin");
  mkdirSync(api, { recursive: true });
  mkdirSync(bin);
  const file = path.join(api, "client.ts");
  writeFileSync(file, "export const version = 1;\n");
  const pnpm = path.join(bin, "pnpm");
  writeFileSync(
    pnpm,
    '#!/bin/sh\n[ "$1" = openapi:generate ] || exit 97\nexit "${OPENAPI_TEST_STATUS:-0}"\n',
  );
  chmodSync(pnpm, 0o755);
  const git = (...args: string[]) =>
    execFileSync("git", args, { cwd: repo, stdio: "pipe" });
  git("init", "--quiet");
  git("add", "frontend");
  git(
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.invalid",
    "commit",
    "--quiet",
    "-m",
    "fixture",
  );
  const run = (status = "0") =>
    spawnSync("sh", ["-c", command], {
      cwd,
      env: {
        ...process.env,
        PATH: `${bin}${path.delimiter}${process.env.PATH}`,
        OPENAPI_TEST_STATUS: status,
      },
      encoding: "utf8",
    }).status;
  return { api, file, git, run };
}

it("accepts an unchanged generated client", () => {
  expect(fixture().run()).toBe(0);
});

it.each([false, true])(
  "rejects changed generated clients, staged=%s",
  (staged) => {
    const { file, git, run } = fixture();
    writeFileSync(file, "export const version = 2;\n");
    if (staged) git("add", "frontend/src/api/client.ts");
    expect(run()).not.toBe(0);
  },
);

it("rejects new untracked generated files", () => {
  const { api, run } = fixture();
  writeFileSync(path.join(api, "new-client.ts"), "export {};\n");
  expect(run()).not.toBe(0);
});

it("preserves the generator failure exit status", () => {
  expect(fixture().run("42")).toBe(42);
});
