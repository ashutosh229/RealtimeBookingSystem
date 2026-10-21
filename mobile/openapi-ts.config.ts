import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../docs/openapi.yaml",
  output: "src/api/generated",
  // Types only. Our hand-written src/api/client.ts handles requests,
  // idempotency keys, and error mapping.
  plugins: ["@hey-api/typescript"],
});
