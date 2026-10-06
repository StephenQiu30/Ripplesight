import { readFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";

const fingerprints = () =>
  Object.fromEntries(
    readdirSync("src/api")
      .sort()
      .map((file) => [
        file,
        createHash("sha256")
          .update(readFileSync(`src/api/${file}`))
          .digest("hex"),
      ]),
  );
const before = fingerprints();
const result = spawnSync("pnpm", ["openapi:generate"], { stdio: "inherit" });
if (result.status !== 0) process.exit(result.status ?? 1);
const after = fingerprints();
const changed = [
  ...new Set([...Object.keys(before), ...Object.keys(after)]),
].filter((file) => before[file] !== after[file]);
if (changed.length) {
  console.error(`OpenAPI 客户端需要更新：${changed.join("、")}`);
  process.exitCode = 1;
} else console.log("OpenAPI 客户端与当前运行 API 一致。");
