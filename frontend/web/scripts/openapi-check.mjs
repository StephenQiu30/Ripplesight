import { execSync } from "node:child_process";

execSync("npm run api:gen", { stdio: "inherit" });
execSync("git diff --exit-code -- src/openapi", { stdio: "inherit" });
