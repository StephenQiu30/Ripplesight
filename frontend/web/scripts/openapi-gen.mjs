import { generateService } from "@umijs/openapi";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import yaml from "js-yaml";

const projectRoot = path.resolve(process.cwd());
const contract = path.resolve(projectRoot, "..", "..", "contracts", "openapi", "openapi.yaml");
const generatedSchema = path.resolve(os.tmpdir(), "ai-hotspot-radar-openapi.generated.json");
const openapiOutputDir = path.resolve(projectRoot, "src", "openapi");

function stripDefaultErrorResponses(contractObj) {
  const next = structuredClone(contractObj);
Object.values(next.paths || {}).forEach((methodMap) => {
    ["get", "put", "post", "delete", "patch", "head", "options"].forEach((method) => {
      const operation = methodMap?.[method];
      if (!operation || !operation.responses) {
        return;
      }
      const hasSuccess = ["200", "201", "202", "203", "204", "205", "206"].some(
        (statusCode) => statusCode in operation.responses,
      );
      if (hasSuccess && operation.responses.default) {
        delete operation.responses.default;
      }
    });
  });
  return next;
}

function loadContract(filePath) {
  const rawText = fs.readFileSync(filePath, "utf8");
  const parsed = yaml.load(rawText);
  return stripDefaultErrorResponses(parsed);
}

fs.mkdirSync(openapiOutputDir, { recursive: true });
const normalized = loadContract(contract);
fs.writeFileSync(generatedSchema, JSON.stringify(normalized, null, 2));

await generateService({
  schemaPath: generatedSchema,
  serversPath: "./src",
  projectName: "openapi",
  namespace: "API",
  requestLibPath: "import { request } from \"@/lib/request\";",
  requestOptionsType: "import(\"@/lib/request\").RequestOptions",
});
